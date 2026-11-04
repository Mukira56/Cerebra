"""Direct provider catalogs and writing, with synthetic keys and HTTP fixtures only."""
import json

import httpx
import pytest

from ai_hq import modelconnections as direct, vault
from ai_hq.agents import AgentResult
from ai_hq.models import Event, Metadata, Prospect
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401


def connect(client, provider, key=None, **extra):
    key = key or f'fixture-{provider}-key'
    response = client.put(f'/api/prospects/models/connections/{provider}', json={'api_key': key, **extra})
    assert response.status_code == 200, response.text
    assert key not in response.text and 'api_key' not in response.text
    return key


def seed(client):
    with client.app.state.db.Session.begin() as session:
        session.add(Prospect(id='p-api', name='Fixture Dental', kind='dentists', city='Austin', state='Texas', status='kept',
                             facts=[{'key': 'no_booking', 'text': 'No booking form', 'seen': 'https://fixture.example'}]))


def transport(client, handler):
    client.app.state.model_connections.client = httpx.Client(transport=httpx.MockTransport(handler))


def test_catalogs_include_individual_cli_and_paginated_api_models_without_exposing_keys(client, monkeypatch):
    from ai_hq import catalog
    monkeypatch.setattr(catalog, 'catalog', lambda: {'codex': [{'model': 'codex-fixture', 'label': 'Codex fixture'}],
                                                   'claude': [{'model': 'sonnet', 'label': 'Sonnet fixture'}]})
    key = connect(client, 'openai')
    connect(client, 'anthropic', workspace_id='wrkspc_fixture')
    with client.app.state.db.Session() as session:
        stored = direct.load(session)['openai']['api_key']
        assert stored != key and vault.unprotect(stored) == key
    seen = []
    def handler(request):
        assert request.method == 'GET'
        seen.append(str(request.url))
        if request.url.host == 'api.openai.com':
            assert request.headers['authorization'] == 'Bearer ' + key
            return httpx.Response(200, json={'data': [{'id': 'gpt-future-text'}, {'id': 'gpt-image-fixture'}, {'id': 'ft:gpt-4o:audio-team:custom'}]})
        assert request.headers['anthropic-version'] == '2026-10-21'
        assert request.headers['anthropic-workspace-id'] == 'wrkspc_fixture'
        if request.url.params.get('after_id'):
            return httpx.Response(200, json={'data': [{'id': 'claude-newer', 'display_name': 'New Claude'}], 'has_more': False})
        return httpx.Response(200, json={'data': [{'id': 'claude-first'}], 'has_more': True, 'last_id': 'claude-first'})
    transport(client, handler)
    for provider in ('openai', 'anthropic'):
        assert client.post(f'/api/prospects/models/connections/{provider}/refresh').status_code == 200
    state = client.get('/api/prospects/models').json()
    choices = {item['id']: item for item in state['options']}
    assert {'catalog:codex:codex-fixture', 'catalog:claude:sonnet', 'api:openai:gpt-future-text', 'api:anthropic:claude-newer'} <= choices.keys()
    assert choices['api:openai:gpt-image-fixture']['disabled']
    assert not choices['api:openai:ft:gpt-4o:audio-team:custom']['disabled']
    assert len(seen) == 3 and key not in json.dumps(state)


@pytest.mark.parametrize('provider,model,path', [('openai', 'gpt-future-text', '/v1/responses'),
                                                ('openai', 'gpt-4o-fixture', '/v1/chat/completions'),
                                                ('openai', 'ft:gpt-3.5-turbo:fixture:custom', '/v1/chat/completions'),
                                                ('openai', 'davinci-002', '/v1/completions'),
                                                ('anthropic', 'claude-future', '/v1/messages')])
def test_api_only_drafting_uses_exact_model_without_cli_permissions_or_global_route_override(client, provider, model, path):
    seed(client)
    connect(client, provider)
    calls = []
    body = json.dumps({'subject': 'API draft', 'body': 'A useful booking page for your customers.'})
    def handler(request):
        assert request.url.path == path and request.method == 'POST'
        values = json.loads(request.content)
        assert values['model'] == model
        assert 'fixture-' + provider + '-key' not in request.content.decode()
        calls.append(values)
        if provider == 'anthropic':
            return httpx.Response(200, json={'content': [{'type': 'thinking', 'thinking': 'hidden'}, {'type': 'text', 'text': body}],
                                            'stop_reason': 'end_turn', 'usage': {'input_tokens': 10, 'output_tokens': 20}})
        if path.endswith('chat/completions'):
            return httpx.Response(200, json={'choices': [{'message': {'content': body}, 'finish_reason': 'stop'}]})
        if path.endswith('/completions'):
            return httpx.Response(200, json={'choices': [{'text': body, 'finish_reason': 'stop'}]})
        assert values['store'] is False
        return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': body}]}]})
    transport(client, handler)
    selected = f'api:{provider}:{model}'
    saved = client.put('/api/outreach', json={'writing_model': selected})
    assert saved.status_code == 200 and not saved.json()['enabled']
    assert client.get('/api/prospects/models').json()['selected'] == selected
    assert client.app.state.prospect_writer.settings.live_enabled is False
    draft = client.post('/api/prospects/p-api/opener')
    assert draft.status_code == 200, draft.text
    assert 'API draft' in draft.json()['opener'] and len(calls) == 1
    with client.app.state.db.Session() as session:
        event = session.query(Event).filter_by(kind='model').one()
        assert event.data['cost'] is None and event.data['model'] == model


@pytest.mark.parametrize('provider,model', [('claude', 'sonnet'), ('codex', 'gpt-fixture')])
def test_individual_cli_model_choice_is_sent_to_cli_not_api(client, provider, model):
    from test_product_api import enable_agents
    enable_agents(client)
    seed(client)
    calls = []
    class CLI(FixtureRegistry):
        def chat(self, name, prompt, workdir, model='', cancel_event=None):
            calls.append((name, model))
            return AgentResult(True, json.dumps({'subject': 'CLI draft', 'body': 'Helpful content'}))
    client.app.state.supervisor.registry = CLI()
    client.put('/api/outreach', json={'writing_model': f'catalog:{provider}:{model}'}).raise_for_status()
    assert client.post('/api/prospects/p-api/opener').status_code == 200
    assert calls == [(provider, model)]


def test_catalog_errors_preserve_cache_redact_key_and_do_not_fall_back_or_retry(client):
    key = connect(client, 'openai')
    transport(client, lambda request: httpx.Response(200, json={'data': [{'id': 'gpt-cached'}]}))
    client.post('/api/prospects/models/connections/openai/refresh').raise_for_status()
    calls = []
    def limited(request):
        calls.append(request)
        return httpx.Response(429, json={'error': {'message': 'Quota exceeded for ' + key}})
    transport(client, limited)
    response = client.post('/api/prospects/models/connections/openai/refresh')
    assert response.status_code == 400 and key not in response.text
    catalog = client.get('/api/prospects/models').json()
    assert key not in json.dumps(catalog) and catalog['connections']['openai']['models'][0]['id'] == 'gpt-cached'
    seed(client)
    client.put('/api/outreach', json={'writing_model': 'api:openai:gpt-cached'}).raise_for_status()
    response = client.post('/api/prospects/p-api/opener')
    assert response.status_code == 400 and '429' in response.text and key not in response.text
    assert len(calls) == 2  # one catalog request, one generation request; no retries
    assert client.get('/api/prospects/models').json()['selected'] == 'api:openai:gpt-cached'


def test_disconnect_and_non_text_models_never_send_a_generation_request(client):
    connect(client, 'openai')
    seed(client)
    client.put('/api/outreach', json={'writing_model': 'api:openai:gpt-custom'}).raise_for_status()
    client.delete('/api/prospects/models/connections/openai').raise_for_status()
    transport(client, lambda request: (_ for _ in ()).throw(AssertionError('No network expected')))
    response = client.post('/api/prospects/p-api/opener')
    assert response.status_code == 400 and 'Connect OpenAI' in response.text
    assert client.put('/api/outreach', json={'writing_model': 'api:openai:text-embedding-3-large'}).status_code == 400
    assert not client.get('/api/prospects/models').json()['connections']['openai']['configured']


def test_repeated_pagination_is_bounded_and_incomplete_drafts_are_not_saved(client):
    connect(client, 'anthropic')
    transport(client, lambda request: httpx.Response(200, json={'data': [{'id': 'claude-fixture'}], 'has_more': True, 'last_id': 'claude-fixture'}))
    assert client.post('/api/prospects/models/connections/anthropic/refresh').status_code == 400
    assert not client.get('/api/prospects/models').json()['connections']['anthropic']['models']
    seed(client)
    transport(client, lambda request: httpx.Response(200, json={'content': [{'type': 'text', 'text': '{"subject":"partial"'}], 'stop_reason': 'max_tokens'}))
    client.put('/api/outreach', json={'writing_model': 'api:anthropic:claude-fixture'}).raise_for_status()
    assert client.post('/api/prospects/p-api/opener').status_code == 400
    with client.app.state.db.Session() as session:
        assert not session.get(Prospect, 'p-api').opener


@pytest.mark.parametrize('choice', [None, [], 'api:other:model', 'api:openai:', 'api:openai:bad model', 'catalog:other:model'])
def test_invalid_model_choices_are_refused(client, choice):
    assert client.put('/api/outreach', json={'writing_model': choice}).status_code == 400


def test_api_key_mutation_requires_csrf_and_empty_keys_do_not_erase_a_saved_connection(client):
    refused = client.put('/api/prospects/models/connections/openai', json={'api_key': 'fixture-key'}, headers={'X-CSRF-Token': 'wrong'})
    assert refused.status_code == 403
    key = connect(client, 'openai')
    client.put('/api/prospects/models/connections/openai', json={'api_key': ''}).raise_for_status()
    state = client.get('/api/prospects/models').json()
    assert state['connections']['openai']['configured'] and key not in json.dumps(state)


@pytest.mark.parametrize('data', [{'status': 'completed', 'output': ['invalid']}, {'status': 'incomplete', 'output': []}])
def test_malformed_or_incomplete_openai_output_does_not_replace_an_existing_draft(client, data):
    connect(client, 'openai')
    seed(client)
    with client.app.state.db.Session.begin() as session:
        session.get(Prospect, 'p-api').opener = 'Existing owner draft'
    client.put('/api/outreach', json={'writing_model': 'api:openai:gpt-future'}).raise_for_status()
    transport(client, lambda request: httpx.Response(200, json=data))
    assert client.post('/api/prospects/p-api/opener').status_code == 400
    with client.app.state.db.Session() as session:
        assert session.get(Prospect, 'p-api').opener == 'Existing owner draft'
