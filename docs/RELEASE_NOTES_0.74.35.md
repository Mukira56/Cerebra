# Cerebra 0.74.35

- **Tell Cerebra what you want, on Home.** Type a request ("Build a booking website", "Find Python jobs I qualify for", "Write a proposal for this client"). Cerebra works out which workflow it belongs to, says why, and opens it with your words filled in. It uses its own rules first, and asks a free model only when the rules can't tell. Nothing starts until you confirm it there.
- **Do Prompt Architect specs help?** Tasks now remember which model wrote their spec. Model intelligence compares finished tasks with and without a spec: how many completed, how many completed first time with no repairs, and repairs per task.
- **When Claude's plan is used up, writing carries on.** Emails, plans and write-ups routed to your Claude account move to a free model until Claude is back. Coding tasks still wait for Claude.
- **Rate finished work.** Each task's report asks "Was this result good?" Your ratings appear per coder in Model intelligence.
- **Fixed:** Company pitches didn't recognise translator, interpreter and "become a…" pages as places to apply. A hidden character in its page finder, there since the page was added, is gone, and a new check keeps such characters out.

**Gemini and Qwen, signed in like Claude and ChatGPT (no OpenRouter needed)**
- **Gemini** (Google's Gemini CLI, signed in with your Google account) and **Qwen** (Qwen Code, signed in with a free Qwen account) now work inside Cerebra:
  - **Gemini:** research, long documents, the Prompt Architect and checking facts.
  - **Qwen:** reasoning, code questions and second checks.

  Both run read-only, within each company's free daily allowance. Coding tasks stay with Claude.
- Install them from **Install tools**, then press **Sign in** on **AI accounts**. Sign-in happens in each tool's own window; Cerebra never sees your password.
- They are the new defaults. OpenRouter is optional, and **Use my signed-in accounts (no OpenRouter)** in Model intelligence switches everything back to Claude, Gemini and Qwen in one click.
- If Gemini or Qwen isn't signed in, or has used today's allowance, your Claude account answers instead.
- DeepSeek has no sign-in tool, only a paid API, so it isn't offered. Small DeepSeek models still run on this computer through Ollama if you install them.
