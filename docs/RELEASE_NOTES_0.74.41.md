# Cerebra 0.74.41

**Run Cerebra from Telegram**
- **Yes and No for everything waiting for your OK.** Each item on Waiting for my OK comes to your phone with **YES** and **NO** buttons: plans, merges, starting tasks, approved posts, accepting a client, Freelancer.com bids and Cerebra's own plans. Anything new is sent as soon as it appears. Items that can only be done in Cerebra say so. Type "what's waiting for my OK?" any time.
- **Where are my tasks?** Ask "where is my task?" or "why is it blocked?" (or type /tasks). Cerebra answers straight from its own records, without spending AI usage: what each task is doing, why it waits, who is working on it, and what to do next.
- **Task alerts that say why.** Instead of "Open Cerebra for details", a task alert now says what happened and why, with buttons: **YES/NO** for a decision, **Resume** for a paused task, **Try again** for a failed one, **Start** for a ready one.
- **"Run it" works.** Tasks can be started, resumed, tried again, paused, cancelled or have their plan approved from the chat. Cancelling asks first.
- **Full control.** Anything in Cerebra can be changed from the phone, including deleting, which always asks first. Connecting accounts, keys and passwords stay on the laptop, because Telegram keeps messages on its servers.
- **Faster and lighter.** Plain requests and task questions are answered by Cerebra's own rules. Other messages go to a free model first, and your Claude account answers only when that doesn't work. The bot can now look a few more things up before answering.

**When a model is down, the other takes over**
- If Claude or Codex is down, overloaded or out of usage, the other company's model takes the step at once and the task keeps going; it no longer waits. Turn this off in Model intelligence if you want coding to wait for Claude.

**Join the AI discussion**
- Council meetings have a box to type in. While the models are talking, your note reaches both before their next turn, and your words decide. After a meeting, your note starts a follow-up meeting from where the last one ended.
- If one model can't answer its turn, the other takes it, instead of the meeting stopping.

**Why tasks were stopping**
- Your laptop's drive was full: Cerebra couldn't write its database, and work failed. Keep a few GB free.
- A finished task waits to merge while the project folder has uncommitted changes, such as package-lock.json. Commit or set aside those changes, then say "resume it".
