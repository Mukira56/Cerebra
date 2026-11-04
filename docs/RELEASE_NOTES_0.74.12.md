# Cerebra 0.74.12

Prospects now offers individual OpenAI API and Anthropic API models alongside individual Codex and Claude Code models. The earlier provider-only switch has been replaced with a searchable, grouped model picker. Model labels identify the API or CLI connection, and there is a custom model-ID option for new models or account-specific IDs.

Use Prospects > Writing model > Connect / refresh API models to save each provider's API key in the OS-protected vault and refresh the model list from that account. Anthropic keys can also specify a workspace ID when required. Refresh reads the model catalog without generating content. Non-text models appear unavailable for email drafting. Codex uses the existing CLI model catalog; Claude Code includes its known model choices and accepts an explicit custom model ID.

Select the exact model and Save writing model. This applies to first emails, offers, follow-ups and reply drafts, preserves the default routing when Default is selected, and does not enable outreach or send a message. A provider quota/authentication failure is shown without silently switching providers or automatically retrying a paid generation request.

API connections have provider API billing and require provider API keys. CLI choices use the existing Codex/Claude Code sign-ins. API-only drafting does not require giving CLI agents filesystem execution permissions. Keys are not returned to the browser; model catalogs are cached locally. Recorded API token usage has unknown monetary cost rather than being labelled free. Fresh customers inherit no connections or catalogs.

Validation: 123 relevant regression tests, plus a browser workflow connecting both fixture API providers, refreshing their model lists, switching from a simulated Claude API quota failure to an OpenAI API draft, saving/reloading the exact model, searching models and selecting a custom model ID. Individual CLI model routing, pagination, incomplete-output handling, CSRF, key redaction, disconnection and non-text guards are covered. All provider calls in verification are fixtures; no live generation or real mail is claimed.

The actual installer passed isolated installation, private fresh-customer defaults, native authenticated desktop startup, a stand-in-agent Git/pytest workflow, upgrade cleanup, uninstall and retention of user data. All 2,737 payload files passed the privacy audit.

Includes the earlier updater, privacy, setup and any-time outreach fixes. Windows 10/11 x64; installer unsigned. Verify against the accompanying SHA-256 file. Existing installation data is retained on upgrade.

Provider references checked 4 November 2026: [OpenAI model listing](https://developers.openai.com/api/reference/resources/models/methods/list), [OpenAI text generation](https://developers.openai.com/api/docs/guides/text), [Anthropic model listing](https://platform.claude.com/docs/en/api/models/list), [Anthropic Messages](https://platform.claude.com/docs/en/api/messages/create). Availability is determined by the connected account; listing a model is not a claim of independent live generation verification.
