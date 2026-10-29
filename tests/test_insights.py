"""Phase 5: what works. Wins and earnings by source, service and way of applying, from the owner's own records only."""
from ai_hq.models import BusinessJob, BusinessRecord, FreelanceLead, MoneyDocument
from ai_hq import insights
from test_freelance import client  # noqa: F401  (client is a fixture)


def lead(session, number, source, title, status, auto=False, job_id=None, company=""):
    session.add(FreelanceLead(id=f"lead-{number}", source=source, title=title, description=title, url="",
                              status=status, proposal={"text": "Hi", "auto": True} if auto else {"text": "Hi"},
                              extra={"job_id": job_id, "company": company} if job_id or company else {}))


def test_nothing_is_suggested_before_there_is_enough_to_go_on(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        lead(session, 1, "freelancer", "React landing page", "applied", auto=True)
    result = client.get("/api/freelance/insights").json()
    assert result["totals"]["applied"] == 1 and result["totals"]["won"] == 0
    assert result["advice"] == ["Not enough results yet to see a pattern: after a few more applications, this shows where you win and earn most."]


def test_wins_and_money_are_counted_where_they_came_from(client, tmp_path):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        session.add(BusinessJob(id="job-1", title="Website", kind="website", output_dir=str(tmp_path / "job-1")))
        for number in range(10):
            lead(session, number, "freelancer", "WordPress website build", "won" if number < 3 else "lost", auto=True,
                 job_id="job-1" if number == 0 else None)
        for number in range(10, 20):
            lead(session, number, "remoteok", "Logo design for a brand", "applied")
        lead(session, 30, "pasted", "Fiverr order: logo", "won", company="Fiverr")
        lead(session, 31, "himalayas", "Data entry in Excel", "new")
        session.add(BusinessRecord(job_id="job-1", ledger=[
            {"kind": "payment", "amount": 200.0, "note": "Deposit"},
            {"kind": "payment", "amount": 300.0, "note": "Invoice INV-1", "invoice": True}]))  # a copy of the invoice payment below
        session.add(MoneyDocument(id="doc-1", kind="invoice", number="INV-1", client="Ann", job_id="job-1", currency="USD",
                                  items=[], payments=[{"amount": 300.0, "date": "2026-10-20"}]))
    result = client.get("/api/freelance/insights").json()
    freelancer = next(row for row in result["sources"] if row["name"] == "Freelancer.com")
    assert freelancer["applied"] == 10 and freelancer["won"] == 3 and freelancer["win_rate"] == 30
    assert freelancer["earned"] == {"USD": 500.0}  # 300 invoice + 200 by hand; the ledger copy of the invoice once
    assert next(row for row in result["sources"] if row["name"] == "Fiverr")["won"] == 1
    assert next(row for row in result["sources"] if row["name"] == "Himalayas")["applied"] == 0
    web = next(row for row in result["services"] if row["name"] == "Websites & web apps")
    assert web["won"] == 3 and next(row for row in result["services"] if row["name"] == "Design & content")["applied"] == 11
    ways = {row["name"]: row for row in result["ways"]}
    assert ways["automatic"]["applied"] == 10 and ways["by you"]["applied"] == 11
    assert result["totals"]["earned"] == {"USD": 500.0} and result["totals"]["found"] == 22
    tips = " ".join(result["advice"])
    assert "Freelancer.com is where you win most: 3 of 10" in tips and "Remote OK: 10 applications and no wins yet" in tips


def test_advice_points_at_weak_automatic_bids():
    rows = {"sources": [], "services": [], "currency": "USD",
            "ways": [{"name": "automatic", "applied": 40, "won": 1, "win_rate": 2, "earned": {}},
                     {"name": "by you", "applied": 10, "won": 3, "win_rate": 30, "earned": {}}]}
    tips = " ".join(insights.advice(rows))
    assert "Raise the lowest score" in tips and "Proposals you send yourself win more (30% against 2% automatic)" in tips
