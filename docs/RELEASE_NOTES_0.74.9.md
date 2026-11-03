# Cerebra 0.74.9

Prospect outreach and follow-ups can now run any day, at any time. The weekday 09:00-17:00 gate has been removed, including for installations with saved business-hour settings. Daily sending limits, sending opt-ins, reply handling, opt-outs and duplicate-send protections remain in place.

This release also includes the previously unreleased customer workspace improvements: private first-run personalization, clean customer defaults, improved desktop/mobile setup, and fixes for stale setup forms and automation scheduling. Existing installations retain their records and configured preferences.

The official Windows installer includes its public GitHub update channel, so future releases can be found in Settings. Distributors can configure their own channel at build time; credentials and personal runtime history are never included.

Validation: 55 outreach/freelance/prospect regression tests; 48 update-channel, privacy, customer-workspace and installer-policy tests. A Sunday-night follow-up regression also passed. These tests use fixture services and do not send real emails or invoke live coding providers.

The actual installer passed isolated fresh installation, private runtime imports, empty customer workspace, startup without Git, native launch/authentication/stop, embedded desktop rendering, a Git/pytest workflow with stand-in agents, upgrade cleanup, uninstall and retention of user data. The packaged update channel was verified. The payload privacy audit passed for 2,735 files.

Windows 10/11 x64. The installer is unsigned. Verify the download against its accompanying SHA-256 file. Exit Cerebra before manually installing; installation retains the selected data directory.
