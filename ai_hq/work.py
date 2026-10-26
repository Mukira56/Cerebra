"""Plans and the one place that turns plan items into tasks.

A plan (from the Council, Support or the owner) is stored data: items with stable IDs, their requirements,
acceptance criteria, dependencies and roles. Every path that creates work for an item (the owner's
"Create task" button, Support's create_plan_task action, an automatic handoff, a retry) goes through
`WorkService.item_task`, which is idempotent: an item has at most one task. Before creating a task it
reconciles with tasks that already carry the item's id, so a crash between creating the task and linking it
can't produce a duplicate after a restart.
"""
from __future__ import annotations

import threading

from sqlalchemy import select

from .models import Event, Plan, PlanItem, Task, as_dict, now, uid


class WorkService:
    def __init__(self, db, supervisor):
        self.db, self.supervisor = db, supervisor
        self._lock = threading.RLock()  # one creator at a time in this process; the stored links make it durable

    # ---- plans ------------------------------------------------------------------------------
    def council_plan(self, meeting):
        """The plan for a finished Council meeting, created on first use (idempotent per meeting)."""
        with self._lock, self.db.Session.begin() as session:
            existing = session.scalars(select(Plan).where(Plan.source == "council", Plan.source_id == meeting["id"])).first()
            if existing is not None:
                return existing.id
            plan = Plan(id=uid(), project_id=meeting["project_id"], source="council", source_id=meeting["id"], objective=meeting["topic"],
                        summary=meeting.get("summary") or "", solution=meeting.get("solution"))
            session.add(plan)
            session.flush()
            ids = []
            for position, proposal in enumerate(meeting["proposals"]):
                item = PlanItem(id=uid(), plan_id=plan.id, position=position, title=proposal["title"], description=proposal["description"],
                                why=proposal.get("why", ""), requirements=list(proposal.get("requirements", [])),
                                acceptance_criteria=list(proposal.get("acceptance_criteria", [])),
                                implementer=_profile_for(session, meeting, proposal["executor"]),
                                reviewer=_profile_for(session, meeting, proposal.get("reviewer") or ""), task_id=proposal.get("task_id"),
                                status="task_created" if proposal.get("task_id") else "proposed")
                session.add(item)
                ids.append(item.id)
            for position, proposal in enumerate(meeting["proposals"]):  # "depends_on": 1-based numbers of earlier tasks
                wanted = [number - 1 for number in proposal.get("depends_on", []) if isinstance(number, int) and 0 < number <= position]
                if wanted:
                    session.get(PlanItem, ids[position]).depends_on = [ids[index] for index in wanted]
            session.add(Event(kind="plan", message=f"Plan created from the Council meeting ({len(ids)} items)", data={"plan_id": plan.id, "council": meeting["id"]}))
            return plan.id

    def plan(self, plan_id):
        with self.db.Session() as session:
            plan = session.get(Plan, plan_id)
            if plan is None:
                raise LookupError("Plan not found")
            items = session.scalars(select(PlanItem).where(PlanItem.plan_id == plan_id).order_by(PlanItem.position)).all()
            return {**as_dict(plan), "items": [as_dict(item) for item in items]}

    def find_item(self, reference):
        """A plan item by full id or a unique id prefix (Support refers to items by prefix)."""
        reference = str(reference or "").strip().lower()
        with self.db.Session() as session:
            item = session.get(PlanItem, reference)
            if item is not None:
                return item.id
            matches = [row.id for row in session.scalars(select(PlanItem).where(PlanItem.id.like(f"{reference}%"))).all()] if len(reference) >= 6 else []
        if len(matches) != 1:
            raise LookupError(f"No single plan item has an id starting with {reference}")
        return matches[0]

    # ---- tasks from plan items --------------------------------------------------------------
    def item_task(self, item_id, origin="user"):
        """The task for a plan item: the existing one if it has one, otherwise a new one. Returns (task_id, created)."""
        with self._lock:
            with self.db.Session() as session:
                item = session.get(PlanItem, item_id)
                if item is None:
                    raise LookupError("Plan item not found")
                plan = session.get(Plan, item.plan_id)
                if item.status == "dropped":
                    raise ValueError("This plan item was dropped from the plan")
                linked = item.task_id if item.task_id and session.get(Task, item.task_id) else self._reconcile(session, plan.project_id, item.id)
                snapshot = as_dict(item)
                project_id, plan_id, version = plan.project_id, plan.id, plan.version
            if linked:
                self._link(item_id, linked)
                return linked, False
            dependencies = [self.item_task(other, origin)[0] for other in snapshot["depends_on"]]
            task = self.supervisor.propose(project_id, f"{snapshot['title']}: {snapshot['description']}",
                                           requirements=snapshot["requirements"] or None, acceptance_criteria=snapshot["acceptance_criteria"] or None,
                                           dependencies=dependencies or None, allowed_paths=snapshot["allowed_paths"] or None,
                                           implementer=snapshot["implementer"] or None, reviewer=snapshot["reviewer"] or None, origin=origin)
            with self.db.Session.begin() as session:
                stored = session.get(Task, task.id)
                stored.results = {**stored.results, "plan": {"plan_id": plan_id, "item_id": item_id, "version": version, "why": snapshot["why"]}}
                session.add(Event(task_id=task.id, kind="plan", message=f"Task created from plan item “{snapshot['title'][:80]}” ({origin})",
                                  data={"plan_id": plan_id, "item_id": item_id}))
            self._link(item_id, task.id)
            return task.id, True

    def _reconcile(self, session, project_id, item_id):
        """A task that already carries this item's id (created before a crash, not yet linked)."""
        for task in session.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.created_at)).all():
            if (task.results or {}).get("plan", {}).get("item_id") == item_id:
                return task.id
        return None

    def _link(self, item_id, task_id):
        with self.db.Session.begin() as session:
            item = session.get(PlanItem, item_id)
            if item.task_id != task_id or item.status != "task_created":
                item.task_id, item.status = task_id, "task_created"
                session.get(Plan, item.plan_id).updated_at = now()


def _profile_for(session, meeting, provider):
    """The meeting's model profile for a provider name (the Council speaks in providers; tasks need profiles)."""
    from .profiles import get_profile
    for key in ("first", "second"):
        try:
            if get_profile(session, meeting[key])["provider"] == provider:
                return meeting[key]
        except (KeyError, ValueError):
            continue
    return ""
