# Cerebra 0.74.13

Prospects now leads with individual GPT and Claude model names using existing subscriptions, without requiring API keys. Select a model in Prospects > Writing model, save, and retry a draft that stopped because the previous model hit its usage limit. The preference covers first emails, offers, follow-ups and replies.

Subscription-only selections bypass global API routing, including when choosing the default subscription model. Before drafting, Cerebra checks the official client's sign-in status and refuses API-key or unknown authentication. It never copies subscription tokens. Saving a choice does not enable outreach or send email. Existing API settings remain available under an optional Advanced control for customers who deliberately use separately billed APIs.

The connection uses the user's installed, signed-in official Codex or Claude Code client. OpenAI model names come from the client's catalog, with known choices when no catalog exists; Claude families are known choices. Account entitlement and successful generation remain subject to the provider. Custom IDs support newer client-accessible models. This release does not expose ChatGPT website-only modes or guarantee every listed model is included in a plan. No automatic API fallback or automatic provider switching occurs.

Validation uses isolated records, fixture providers and browser automation. Genuine subscription inference is not part of routine testing. The Windows installer is validated separately before publication. The customer build contains no owner records or credentials; installation does not import an existing development database.

Provider guidance: [OpenAI subscription access in Codex](https://developers.openai.com/codex/auth), [Anthropic authentication and credential use](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use).
