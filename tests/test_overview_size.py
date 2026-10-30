"""The overview is polled every few seconds: answered approvals come without their payloads (whole diffs and plans)."""
from ai_hq.models import Approval, Project, Task
from test_freelance import client  # noqa: F401  (client is a fixture)


def test_answered_approvals_drop_their_payload_and_waiting_ones_keep_it(client, tmp_path):  # noqa: F811
    big = {"diff": "+ line\n" * 20000}
    with client.app.state.db.Session.begin() as session:
        session.add(Project(id="p", name="Site", path=str(tmp_path / "site"), default_branch="main"))
        session.flush()
        session.add(Task(id="t", project_id="p", description="Build the site"))
        session.flush()
        session.add(Approval(id="old", task_id="t", kind="merge", status="approved", payload=big))
        session.add(Approval(id="new", task_id="t", kind="merge", status="PENDING", payload=big))
    approvals = {row["id"]: row for row in client.get("/api/overview").json()["approvals"]}
    assert approvals["old"]["payload"] == {} and approvals["old"]["status"] == "approved"
    assert approvals["new"]["payload"] == big  # the Decide dialog shows the changes


def test_the_overview_says_what_freelance_work_needs_the_owner(client):  # noqa: F811
    from ai_hq.models import FreelanceLead
    with client.app.state.db.Session.begin() as session:
        for number, (status, score) in enumerate([("new", 70), ("new", 45), ("new", 20), ("applied", 60), ("awarded", 60), ("hidden", 90)]):
            session.add(FreelanceLead(id=f"freelancer:{number}", source="freelancer", title=f"Job {number}", status=status, score=score))
    work = client.get("/api/overview").json()["freelance"]
    assert work["strong"] == 1 and work["good"] == 50 and work["min_score"] == 40  # strong is 50+, as on the Freelance page and work["applied"] == 1 and work["awarded"] == 1 and work["auto"] is False
