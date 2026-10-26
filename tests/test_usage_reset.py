"""Out-of-usage waits follow the provider's own reset time instead of a fixed 15 minutes."""
from datetime import datetime, timezone

import pytest

from ai_hq.agents import AgentResult
from ai_hq.models import Agent
from ai_hq.usage import reset_in
from fakes import FixtureRegistry
from test_supervisor import hq, ready  # noqa: F401  (hq is a fixture)

NOW = datetime(2026, 10, 26, 22, 13)


@pytest.mark.parametrize("text,seconds", [
    ("You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro) or try again at 10:31 PM.", 18 * 60 + 60),  # Codex, today
    ("Claude AI usage limit reached ∙ resets 3pm", (16 * 60 + 47) * 60 + 60),  # Claude, tomorrow afternoon
    ("5-hour limit reached - resets at 1:30am", (3 * 60 + 17) * 60 + 60),
    ("Rate limited. Try again in 2 hours 5 minutes", 2 * 3600 + 5 * 60 + 60),
    ("retry in 45m", 45 * 60 + 60),
    ("usage limit reached", None),
    ("try again at 25:99", None),
])
def test_reset_times_are_read_from_the_providers_messages(text, seconds):
    assert reset_in(text, NOW) == seconds


class OutOfUsage(FixtureRegistry):
    def execute(self, name, request, cancel_event=None):
        self.requests.append((name, request))
        return AgentResult(False, "", error="rate_limited: agent exited with code 1: You've hit your usage limit. Try again in 40 minutes.")


def test_a_provider_rests_until_its_reset_and_the_task_waits_that_long(hq):
    supervisor, _, _, db, _ = hq
    supervisor.registry = OutOfUsage()
    task_id = ready(hq)
    supervisor.run_until_idle()
    task = supervisor.get(task_id)
    assert task.state == "BLOCKED" and task.results["blocked_reason"] == "waiting_for_usage"
    wait = (datetime.fromisoformat(task.results["retry_after"]) - datetime.now(timezone.utc)).total_seconds()
    assert 38 * 60 < wait <= 41 * 60, wait  # about 40 minutes, not the old fixed 15
    with db.Session() as session:
        statuses = {agent.id: agent.status for agent in session.query(Agent).all()}
    assert all(statuses[name].get("usage_until") for name in ("codex", "claude"))  # shown on the dashboard
