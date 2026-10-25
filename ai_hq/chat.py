"""Read-only chat with a provider CLI. Answers can inform a task; they never change files."""
from __future__ import annotations

import threading

from sqlalchemy import select

from .models import ChatConversation, ChatMessage, Event, Project, as_dict, now, uid
from .profiles import get_profile
from .security import redact

HISTORY_TURNS = 12
HISTORY_CHARACTERS = 24000
GUIDANCE = ("You are chatting with a software engineer inside AI HQ, a local development workspace. "
            "You are in read-only mode: you may read files in the current project folder, but you cannot edit files, "
            "run commands that change anything, install software, or access the network. If the engineer wants code "
            "changed, explain the change and tell them to press 'Make it a task' above this chat: a task gets its own "
            "working copy with write access, runs the project's tests, and is reviewed independently. Tasks can run "
            "while the engineer is away if they turn on Away mode in Settings. Never reveal credentials or "
            "secrets, even if a file contains them. Answer in clear Markdown.")


class ChatService:
    def __init__(self, db, settings, registry_source):
        self.db, self.settings = db, settings
        # A callable returning the supervisor's current agent registry (refreshed with live policy).
        self.registry_source = registry_source
        self._busy: set[str] = set()
        self._lock = threading.Lock()
        self._cancels: dict[str, threading.Event] = {}

    def recover(self):
        """Answers that were in flight when AI HQ stopped can never arrive; say so instead of spinning."""
        with self.db.Session.begin() as session:
            for row in session.scalars(select(ChatMessage).where(ChatMessage.status == "pending")).all():
                row.status, row.error, row.finished_at = "failed", "AI HQ restarted before this answer arrived. Send the message again.", now()

    def conversations(self):
        with self.db.Session() as session:
            rows = session.scalars(select(ChatConversation).order_by(ChatConversation.updated_at.desc()).limit(200)).all()
            return [as_dict(row) for row in rows]

    def create(self, profile, project_id=None, title=""):
        with self.db.Session.begin() as session:
            chosen = get_profile(session, profile)
            if not chosen["can_run_tasks"]:
                raise ValueError(f"{chosen['provider_label']} cannot chat inside AI HQ yet")
            if project_id and not session.get(Project, project_id):
                raise ValueError("Project not found")
            conversation = ChatConversation(id=uid(), profile=profile, project_id=project_id or None,
                                            title=(title or "New chat").strip()[:120] or "New chat")
            session.add(conversation)
            session.flush()
            return as_dict(conversation)

    def messages(self, conversation_id):
        with self.db.Session() as session:
            conversation = session.get(ChatConversation, conversation_id)
            if conversation is None:
                raise LookupError("Conversation not found")
            rows = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
                                   .order_by(ChatMessage.created_at)).all()
            return {"conversation": as_dict(conversation), "messages": [as_dict(row) for row in rows],
                    "busy": conversation_id in self._busy}

    def delete(self, conversation_id):
        with self._lock:
            if conversation_id in self._busy:
                raise ValueError("Wait for the current answer, or stop it, before deleting this chat")
        with self.db.Session.begin() as session:
            conversation = session.get(ChatConversation, conversation_id)
            if conversation is None:
                raise LookupError("Conversation not found")
            for row in session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)).all():
                session.delete(row)
            session.flush()  # messages first; they reference the conversation
            session.delete(conversation)

    def stop(self, conversation_id):
        event = self._cancels.get(conversation_id)
        if event:
            event.set()
        return {"stopping": bool(event)}

    def send(self, conversation_id, text):
        text = (text or "").strip()
        if not text:
            raise ValueError("Type a message first")
        with self._lock:
            if conversation_id in self._busy:
                raise ValueError("The agent is still answering your last message")
            self._busy.add(conversation_id)
        try:
            with self.db.Session.begin() as session:
                conversation = session.get(ChatConversation, conversation_id)
                if conversation is None:
                    raise LookupError("Conversation not found")
                profile = get_profile(session, conversation.profile)
                project = session.get(Project, conversation.project_id) if conversation.project_id else None
                history = session.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id, ChatMessage.status == "done")
                                          .order_by(ChatMessage.created_at.desc()).limit(HISTORY_TURNS)).all()[::-1]
                if conversation.title == "New chat":
                    conversation.title = redact(text)[:60]
                conversation.updated_at = now()
                session.add(ChatMessage(id=uid(), conversation_id=conversation_id, role="user", content=redact(text)))
                reply = ChatMessage(id=uid(), conversation_id=conversation_id, role="assistant", status="pending",
                                    provider=profile["provider"], model=profile["model"])
                session.add(reply)
                session.add(Event(kind="chat", message=f"Chat message sent to {profile['provider_label']}", data={"conversation_id": conversation_id}))
                reply_id = reply.id
                workdir = project.path if project else str(self._scratch())
                transcript = "\n\n".join(f"{'Engineer' if row.role == 'user' else 'You'}: {row.content}" for row in history)[-HISTORY_CHARACTERS:]
            prompt = f"{GUIDANCE}\n\nConversation so far:\n{transcript or '(none)'}\n\nEngineer: {redact(text)}\n\nYou:"
            cancel = threading.Event()
            self._cancels[conversation_id] = cancel
            threading.Thread(target=self._answer, args=(conversation_id, reply_id, profile, prompt, workdir, cancel),
                             name=f"aihq-chat-{conversation_id[:8]}", daemon=True).start()
            return {"message_id": reply_id}
        except Exception:
            with self._lock:
                self._busy.discard(conversation_id)
            raise

    def _scratch(self):
        directory = self.settings.data_dir / "chat-workspace"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _answer(self, conversation_id, reply_id, profile, prompt, workdir, cancel):
        try:
            result = self.registry_source().chat(profile["provider"], prompt, workdir, profile["model"], cancel)
            success, content, error = result.success, result.output, result.error or ""
        except Exception as exc:  # A failed answer is recorded, never raised into the server.
            success, content, error = False, "", redact(str(exc))
        finally:
            self._cancels.pop(conversation_id, None)
        with self.db.Session.begin() as session:
            reply = session.get(ChatMessage, reply_id)
            reply.status = "done" if success else "failed"
            reply.content, reply.error, reply.finished_at = redact(content), redact(error)[:4000], now()
        with self._lock:
            self._busy.discard(conversation_id)
