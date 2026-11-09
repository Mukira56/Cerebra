# Cerebra 0.74.28

**Company pitches: every email tailored to its company**
- Cerebra keeps what each company says about itself on its own website, and your writing model (the one Prospects uses) adds a short paragraph on that company's work and how you help it. It goes where your pitch has `{personal}`, or after your greeting.
- Only the website's own words are used; nothing is invented. A site that says too little is left for you to write to yourself, rather than getting a generic email.
- **Big tech and AI labs** (Google, Microsoft, Meta, Amazon, Apple, OpenAI, Anthropic, NVIDIA, xAI and others) are added to your list and can get their own pitch, written on the page next to your main one.
- Each company's paragraph can be read, rewritten or edited before sending.

**Reliability and safety**
- Calls to outside services retry dropped connections with growing waits. A busy service is retried for reads only, so a send is never repeated, and a service that keeps failing is paused for 30 seconds.
- Cerebra keeps a log of problems in its data folder (logs\cerebra.log). Secrets are removed and the file is kept small.
- Unexpected errors answer with a short reference instead of internal details.
- Changes are limited to 300 a minute per session.
- New database indexes speed up the busiest pages, and older databases are upgraded automatically.
