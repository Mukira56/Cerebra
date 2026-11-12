# Cerebra 0.74.42

**Faster**
- **Home and every page refresh much faster.** Your log showed the main screen's data taking 10–28 seconds while background work ran. Two causes are fixed:
  - Cerebra used to read every saved freelance lead, about 5,800 of them, on each refresh, just to find the few that need you. The database now finds those itself, using a new index.
  - On your data, one refresh went from 1.3 seconds to 0.4 seconds of work.
- **The page backs off when Cerebra is busy.** It refreshes every 3 seconds, but waits longer when the last answer was slow, so the screens never add to the load.
- **Stale job posts are set aside.** Freelance posts nobody acted on for 3 weeks are hidden and marked expired. They're kept, never deleted, and anything with a proposal or that you saved stays. Every list that shows leads stays quick, and the hourly rescoring has less to do.
- **Long buttons don't freeze the page.** **Run once now** on Company pitches and Apply for jobs, and **Write the next 10 letters**, now run in the background. They used to keep you waiting for up to 6 minutes. The page's status line shows how each run ended.
- **Checking for updates is quicker the second time.** The newest release is remembered for 5 minutes.

**Polish**
- **Counts read properly everywhere:** "1 email", "3 emails" and "0 replies" replace "email(s)" and "repl(ies)", in about 90 messages across the app and Telegram.
- **The five numbers on Home sit in one row** instead of leaving a gap.
