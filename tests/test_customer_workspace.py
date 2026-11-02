"""Customer installation contracts, using empty temporary databases and no external services."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ai_hq import chief, freelance, onboarding, owner, updater
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq.models import Book, BusinessJob, FreelanceLead, Metadata, MoneyDocument, Project, Prospect, Task
from test_product_api import KEY, client  # noqa: F401


def test_fresh_customer_has_no_records_permissions_or_assumed_identity(client):
    status = client.get('/api/onboarding').json()
    assert status['needs_setup'] and not status['existing_workspace']
    assert not status['profile']['name'] and not status['profile']['github'] and not status['profile']['share']
    assert status['freelance']['skills'] == status['freelance']['services'] == []
    assert not any(status['freelance']['sources'].values())
    state = client.app.state
    assert not state.settings.live_enabled and not state.settings.full_access and not state.settings.cli_confinement_accepted
    with state.db.Session() as session:
        for model in (Project, Task, FreelanceLead, Book, Prospect, BusinessJob, MoneyDocument):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert not chief.chief_settings(session)['brief']
        assert not any(freelance.auto_settings(session)[key] for key in ('enabled', 'ahead', 'alert', 'accept_awards'))
        assert owner.brief(session) == ''
    jobs = client.get('/api/chief').json()['jobs']
    assert jobs and not any(job['enabled'] for job in jobs)


def test_fresh_discovery_and_scheduler_never_contact_providers(client):
    def forbidden(*args, **kwargs):
        raise AssertionError('A fresh customer workspace must not contact a provider')
    state = client.app.state
    state.finder.client.get = forbidden
    for worker in state.registry.workers.values():
        worker.run = forbidden
    assert state.finder.check() == {}
    assert state.chief.tick(datetime.now(timezone.utc) + timedelta(days=8)) == 0


def test_setup_rejects_invalid_choices_atomically_and_does_not_grant_execution(client):
    for fields in ({'services': ['invented']}, {'sources': ['freelancer']}, {'currency': 'bad'}, {'live_enabled': True}):
        response = client.post('/api/onboarding', json={'name': 'New customer', **fields})
        assert response.status_code in (400, 422)
        assert client.get('/api/onboarding').json()['needs_setup']
        assert not client.get('/api/owner').json()['name']
    result = client.post('/api/onboarding', json={'name': 'Alex Taylor', 'headline': 'Designer', 'currency': 'EUR',
        'services': ['design'], 'skills': ['Illustration'], 'sources': ['remotive']})
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved['complete'] and not saved['needs_setup'] and not saved['profile']['share']
    assert saved['profile']['name'] == 'Alex Taylor' and saved['currency'] == 'EUR'
    assert saved['freelance']['sources'] == {key: key == 'remotive' for key in freelance.SOURCES}
    assert not client.app.state.settings.live_enabled
    assert not any(job['enabled'] for job in client.get('/api/chief').json()['jobs'])
    with client.app.state.db.Session() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 0


def test_setup_requires_local_session_and_csrf(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'empty'), bootstrap_key=KEY, start_worker=False)
    with TestClient(app) as c:
        assert c.get('/api/onboarding').status_code == 401
        assert c.post('/api/onboarding', json={}).status_code in (401, 403)
        assert c.post('/api/session', json={'key': KEY}).status_code == 200
        assert c.post('/api/onboarding', json={}).status_code == 403


def test_legacy_workspace_preferences_survive_and_other_workspaces_stay_empty(tmp_path):
    settings = Settings(data_dir=tmp_path / 'existing')
    app = create_app(settings, bootstrap_key=KEY, start_worker=False)
    with app.state.db.Session.begin() as session:
        owner.save(session, {'name': 'Existing customer', 'share': True})
        freelance.save_profile(session, {'services': ['web'], 'sources': {'freelancer': True}})
    app.state.db.close()
    app = create_app(settings, bootstrap_key=KEY, start_worker=False)
    with TestClient(app) as c:
        c.headers['X-CSRF-Token'] = c.post('/api/session', json={'key': KEY}).json()['csrf_token']
        saved = c.get('/api/onboarding').json()
        assert saved['existing_workspace'] and not saved['needs_setup']
        assert saved['profile']['name'] == 'Existing customer' and saved['profile']['share']
        assert saved['freelance']['sources']['freelancer']
    other = create_app(Settings(data_dir=tmp_path / 'other'), bootstrap_key=KEY, start_worker=False)
    with other.state.db.Session() as session:
        assert onboarding.status(session)['needs_setup']
        assert session.get(Metadata, owner.KEY) is None
    other.state.db.close()


def test_customer_updates_have_no_implicit_developer_channel(client, monkeypatch):
    monkeypatch.setattr(updater, 'REPOSITORY', '')
    def forbidden(*args):
        raise AssertionError('No update channel was configured')
    client.app.state.updater.github.release = forbidden
    response = client.get('/api/updates')
    assert response.status_code == 200
    assert not response.json()['available'] and response.json()['repository'] == ''
