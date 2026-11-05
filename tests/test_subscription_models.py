"""Subscription routing fixtures. Never invokes an installed provider or reads credentials."""
import json
import pytest

from ai_hq.agents import AgentResult
from ai_hq.integrations import Integrations
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401
from test_modelconnections import seed
from test_product_api import enable_agents


@pytest.mark.parametrize('choice,provider,model', [
    ('auto', 'claude', ''), ('catalog:codex:gpt-fixture', 'codex', 'gpt-fixture'),
    ('catalog:claude:sonnet', 'claude', 'sonnet')])
def test_subscription_choices_bypass_api_hub_and_keep_exact_model(client, choice, provider, model):
    enable_agents(client)
    seed(client)
    writer = client.app.state.prospect_writer
    calls, checks = [], []
    class Registry(FixtureRegistry):
        def chat(self, name, prompt, workdir, model='', cancel_event=None):
            calls.append((name, model))
            return AgentResult(True, json.dumps({'subject': 'Subscription draft', 'body': 'Useful content'}))
    client.app.state.supervisor.registry = Registry()
    writer.subscription_status = lambda name: checks.append(name)
    class NoAPI:
        def chat(self, *args, **kwargs):
            pytest.fail('Subscription-only must not reach an API')
    writer.connections = writer.hub = NoAPI()
    response = client.put('/api/outreach', json={'writing_model': choice, 'subscription_only': True})
    assert response.status_code == 200, response.text
    assert not response.json()['enabled']
    result = client.post('/api/prospects/p-api/opener')
    assert result.status_code == 200, result.text
    assert calls == [(provider, model)] and checks == [provider]
    state = client.get('/api/prospects/models').json()
    assert state['subscription_only'] is True
    assert all(not item['id'].startswith('api:') for item in state['subscription_options'])


def test_subscription_mode_rejects_api_and_non_boolean_flags(client):
    assert client.put('/api/outreach', json={'subscription_only': 'false'}).status_code == 400
    assert client.put('/api/outreach', json={'subscription_only': True, 'writing_model': 'api:openai:gpt-fixture'}).status_code == 400
    state = client.get('/api/outreach').json()['settings']
    assert state['subscription_only'] is False and state['writing_model'] == 'auto'


def test_subscription_failure_preserves_draft_without_fallback(client):
    enable_agents(client)
    seed(client)
    writer = client.app.state.prospect_writer
    def refused(name):
        raise ValueError('Sign in with your subscription')
    writer.subscription_status = refused
    client.put('/api/outreach', json={'writing_model': 'codex', 'subscription_only': True}).raise_for_status()
    result = client.post('/api/prospects/p-api/opener')
    assert result.status_code == 400 and 'Sign in with your subscription' in result.text


@pytest.mark.parametrize('provider,method,signed_in,allowed', [
    ('codex', 'Logged in using ChatGPT', True, True),
    ('codex', 'Logged in using API key', True, False),
    ('codex', 'Unknown authentication', True, False),
    ('claude', 'claude.ai', True, True),
    ('claude', 'api_key', True, False),
    ('claude', 'claude.ai', False, False)])
def test_official_client_must_confirm_subscription(provider, method, signed_in, allowed):
    connection = object.__new__(Integrations)
    connection.sign_in_status = lambda name: {'signed_in': signed_in, 'method': method}
    if allowed:
        assert connection.require_subscription(provider)
    else:
        with pytest.raises(ValueError, match='No API request'):
            connection.require_subscription(provider)
