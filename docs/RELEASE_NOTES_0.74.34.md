# Cerebra 0.74.34

**An AI workforce, with Claude as the lead engineer**
- **Claude writes the code** for new tasks, and Codex reviews it independently. When Claude runs out of usage, a task waits for Claude instead of moving to another model; you can switch a task yourself, or change this under AI accounts › Model intelligence.
- **Prompt Architect:** in New task, **Ask the Prompt Architect** turns your request into requirements and acceptance criteria for you to check. Its open questions and the assumptions it made are listed separately, never added to the requirements. Small, plain requests use a template, with no model call. It runs on a free model by default.
- **New specialist kinds of work:** Reasoning and maths, and Large documents. Choose a free model for each, such as a DeepSeek or Gemini one, from the live free list.
- **Model intelligence** (AI accounts page):
  - who does each kind of work
  - how each model measured up over the last 30 days: how often it gave a usable answer, how fast, how many calls
  - suggestions backed by evidence
  - coding results per model
  - why recent tasks went where they did
- **Daily limits** per kind of work, as a hard stop.
- **Optional performance-based routing:** switches a free-model route to the model that has clearly done better, only after enough calls. Your own account choices are never changed.
- **Local models that are too big for this computer's memory are never loaded,** so it stays responsive.
- Calls through your Claude account are now measured too. How much of a subscription is left isn't shown, because Claude doesn't report it.
