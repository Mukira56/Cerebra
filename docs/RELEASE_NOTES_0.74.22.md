# Cerebra 0.74.22

Fixes automatic outreach stopping. A website whose robots.txt redirected to itself could crash an outreach run, and because that business was tried again each time, every later run failed too. These sites are now handled, and a problem during business research can no longer stop your emails or the reading of replies.
