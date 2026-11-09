# Cerebra 0.74.26

Fixes for updates and for sending email:

- **Update button:** the "Update ready · install" button in the top bar now opens Settings › Updates and scrolls to it. Before, it did nothing when Settings was already open, and otherwise left the Updates panel far down the page.
- **Checking for updates on an unreliable connection:** when GitHub's API can't be reached but GitHub itself can, the update is still found from GitHub's release pages instead of failing.
- **Cerebra comes back after updating:** after an update, Cerebra's window opens in front instead of behind your other windows.
- **Gmail sign-in that Google ended:** when Google ends your Gmail sign-in (Google Cloud apps in Testing end it after 7 days), Cerebra remembers it. Business connections, Company pitches and Automatic outreach then say "connect Gmail again" straight away, instead of failing at each send.
