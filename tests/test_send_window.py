from datetime import datetime

import pytest

from ai_hq import jobs, partners, sendwindow
from test_freelance import client  # noqa: F401  (client is a fixture)

pytestmark = pytest.mark.real_send_window
TUESDAY_10, TUESDAY_7, TUESDAY_18, FRIDAY_18, SATURDAY_11 = (datetime(2026, 11, 10, 10), datetime(2026, 11, 10, 7), datetime(2026, 11, 10, 18),
                                                            datetime(2026, 11, 13, 18), datetime(2026, 11, 14, 11))


def test_automatic_emails_go_out_on_weekdays_during_working_hours():
    rules = sendwindow.rules({})
    assert sendwindow.closed(rules, TUESDAY_10) == ""
    assert "8 am" in sendwindow.closed(rules, TUESDAY_7)
    assert "tomorrow morning." in sendwindow.closed(rules, TUESDAY_18) and "(Monday)" in sendwindow.closed(rules, FRIDAY_18)
    assert "Saturday" in sendwindow.closed(rules, SATURDAY_11)
    assert sendwindow.closed({"business_hours": False}, SATURDAY_11) == ""
    assert sendwindow.describe({}) == "Automatic emails go out Monday to Friday, 8 am to 5 pm on this computer's clock."


def test_the_window_is_checked_when_saved():
    for bad in ({"start_hour": 17, "end_hour": 8}, {"start_hour": 9, "end_hour": 10}, {"end_hour": 30}, {"start_hour": "soon"}, {"business_hours": "yes"}):
        with pytest.raises(ValueError):
            sendwindow.validate(bad, dict(sendwindow.DEFAULT))
    assert sendwindow.validate({"start_hour": 9, "end_hour": 18}, dict(sendwindow.DEFAULT))["end_hour"] == 18


def test_pitch_and_job_settings_keep_the_window(client):  # noqa: F811
    with client.app.state.db.Session.begin() as session:
        assert partners.settings(session)["business_hours"] is True and jobs.settings(session)["start_hour"] == 8
        assert partners.save_settings(session, {"start_hour": 9, "end_hour": 16})["start_hour"] == 9
        assert jobs.save_settings(session, {"business_hours": False})["business_hours"] is False
        with pytest.raises(ValueError):
            partners.save_settings(session, {"start_hour": 20})


def test_outside_working_hours_pitches_wait_but_research_carries_on(client):  # noqa: F811
    from test_partners import prepared
    _, robot = prepared(client)
    client.put("/api/partners", json={"enabled": True, "per_day": 5}).raise_for_status()
    robot.clock = lambda: SATURDAY_11
    waiting = robot.tick()
    assert waiting["sent"] == 0 and robot.gmail.sent == [] and "Saturday" in waiting["message"]
    robot.clock = lambda: TUESDAY_10
    assert robot.tick()["sent"] == 1
