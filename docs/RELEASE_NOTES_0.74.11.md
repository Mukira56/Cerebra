# Cerebra 0.74.11

Prospects now has a Writing model panel. Choose Default, Claude, or ChatGPT (Codex), then Save writing model. If Claude reaches its usage limit, select ChatGPT and retry the draft using your existing OpenAI/Codex sign-in.

This saved Prospects preference applies to first emails, offers, follow-ups and reply drafts. An explicit choice overrides the default writing route for Prospects only. Default preserves the existing routing. Changing the writing model does not switch on automatic outreach, send a message or change the models for other app features.

Includes the 0.74.10 updater fix: a verified local update stays installable when GitHub checks are rate-limited or unavailable. All earlier customer privacy, setup and any-time outreach improvements remain.

Validation uses fixture providers and mailboxes, including a Claude usage-limit failure followed by successful drafting through the selected OpenAI adapter. No real messages are sent and no live provider usage is claimed.

89 regression tests passed across outreach, prospects, model routing, updates, customer defaults and package privacy. The browser test verified saving the ChatGPT choice, persistence after reload and successful retry after the simulated Claude limit, while automatic outreach stayed off.

The actual installer passed isolated installation, private customer defaults, native authenticated desktop startup, a stand-in-agent Git/pytest workflow, upgrade/uninstall and retention of user data. The privacy audit passed for all 2,735 packaged files.

Windows 10/11 x64. The installer is unsigned. Verify it against its SHA-256 file. Existing installation data is retained on upgrade.
