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


def test_setup_cannot_reset_a_completed_or_existing_workspace(client):
    first = client.post('/api/onboarding', json={'name': 'Customer', 'currency': 'EUR',
        'skills': ['Illustration'], 'services': ['design'], 'sources': ['remotive']})
    assert first.status_code == 200
    before = client.get('/api/onboarding').json()
    assert client.post('/api/onboarding', json={}).status_code == 409
    assert client.get('/api/onboarding').json() == before


def test_stale_first_run_form_cannot_overwrite_settings_saved_elsewhere(client):
    assert client.get('/api/onboarding').json()['needs_setup']
    client.put('/api/owner', json={'name': 'Saved elsewhere', 'share': True})
    assert client.post('/api/onboarding', json={'name': 'Stale form'}).status_code == 409
    assert client.get('/api/owner').json()['name'] == 'Saved elsewhere'


def test_feature_opt_ins_start_only_their_workers_and_preserve_manual_pauses(client):
    def jobs():
        return {item['id']: item for item in client.get('/api/chief').json()['jobs']}
    assert not jobs()['auto_apply']['enabled']
    assert client.put('/api/freelance/auto', json={'enabled': True, 'ahead': True}).status_code == 200
    assert jobs()['auto_apply']['enabled'] and jobs()['draft_ahead']['enabled']
    assert not jobs()['win_watch']['enabled'] and not jobs()['won_work']['enabled']
    ran = []
    for key in ('auto_apply', 'draft_ahead'):
        client.app.state.registry.workers[key].run = lambda key=key: ran.append(key) or {'fixture': True}
    assert client.app.state.chief.tick(datetime.now(timezone.utc) + timedelta(hours=2)) == 2
    assert set(ran) == {'auto_apply', 'draft_ahead'}
    client.patch('/api/chief/jobs/auto_apply', json={'enabled': False})
    client.put('/api/freelance/auto', json={'per_day': 3})
    assert not jobs()['auto_apply']['enabled']
    assert not client.get('/api/freelance/auto').json()['schedules']['auto_apply']
    client.put('/api/freelance/auto', json={'enabled': False, 'ahead': False})
    assert not jobs()['draft_ahead']['enabled']
    client.put('/api/chief/settings', json={'brief': True})
    assert jobs()['morning_brief']['enabled']
    client.put('/api/chief/settings', json={'brief': False})
    assert not jobs()['morning_brief']['enabled']


def test_strings_cannot_silently_enable_automation(client):
    for path, fields in [('/api/freelance/auto', {'enabled': 'false'}),
                         ('/api/freelance/auto', {'ahead': 'false'}),
                         ('/api/freelance/auto', {'accept_awards': 'false'}),
                         ('/api/freelance/auto', {'committee': 'false'}),
                         ('/api/freelance/auto', {'alert': 'false'}),
                         ('/api/chief/settings', {'brief': 'false'}),
                         ('/api/outreach', {'enabled': 'true', 'mode': 'send'})]:
        assert client.put(path, json=fields).status_code in (400, 422)
    assert not client.get('/api/freelance/auto').json()['settings']['enabled']
    assert not client.get('/api/chief').json()['settings']['brief']
    assert client.patch('/api/chief/jobs/auto_apply', json={'enabled': 'false'}).status_code == 400
