# Cerebra 0.74.10

Fixes an update-screen bug where a GitHub rate-limit or connection error hid the Install and restart button even though an installer was already downloaded and verified.

Settings now checks the local download first and shows its install button immediately. A download that finishes during a failed release lookup also remains installable. The backend offers a verified local update without another GitHub request and still rejects modified installers. Installation keeps its checksum verification and existing task/data handling.

All 0.74.9 improvements remain, including any-day/any-time prospect outreach, customer privacy defaults and setup/scheduling fixes.

Verified with updater regression tests and browser cases for a ready local update, a download finishing during a failed GitHub check, and no local update. Browser tests simulate installation; no real accounts or messages are used.

Validation: 50 relevant regression tests passed. All three browser cases also passed with the repaired older frontend. The actual installer passed isolated fresh install, private runtime/customer defaults, native startup and authenticated desktop, a stand-in-agent workflow with real Git/pytest, upgrade cleanup, uninstall and retained user data. All 2,735 packaged files passed the privacy audit.

Windows 10/11 x64. This installer is unsigned; check its SHA-256 file. If an older update screen cannot show its controls, download the installer directly from this release. Your existing data location is retained on upgrade.
