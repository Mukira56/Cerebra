"""Direct, owner-selected OpenAI/Anthropic text models. Keys stay in the OS vault.

Catalog refreshes are read-only. Generation occurs only through the selected writer;
there are no automatic paid retries or switches to another provider.
"""
from __future__ import annotations

import re
import time

import httpx

from . import vault
from .agents import AgentResult
from .models import Event, Metadata, now
from .network import LazyClient
from .security import redact

KEY = 'direct_model_connections'
PROVIDERS = {'openai': ('OpenAI API', 'https://api.openai.com/v1'),
             'anthropic': ('Anthropic API', 'https://api.anthropic.com/v1')}
MODEL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,199}$')
NON_TEXT = ('embedding', 'moderation', 'realtime', 'transcri', 'whisper', 'tts', 'dall-e', 'sora', 'image')


def base_model(identifier):
    return identifier.split(':')[1] if identifier.startswith('ft:') and len(identifier.split(':')) > 1 else identifier


def text_model(provider, identifier):
    base = base_model(identifier)
    return provider == 'anthropic' or not any(part in base.lower() for part in NON_TEXT)


def parse_choice(choice):
    if not isinstance(choice, str):
        raise ValueError('Choose a writing model')
    parts = choice.split(':', 2)
    if len(parts) != 3 or parts[0] != 'api' or parts[1] not in PROVIDERS or not MODEL_ID.fullmatch(parts[2]):
        raise ValueError('Choose an OpenAI or Anthropic API model with a valid model ID')
    return parts[1], parts[2]


def validate_choice(session, choice):
    if choice in ('auto', 'claude', 'codex'):
        return choice
    if isinstance(choice, str) and choice.startswith('api:'):
        provider, model = parse_choice(choice)
        if not text_model(provider, model):
            raise ValueError('Choose a text-drafting model for Prospects')
        return choice
    from .profiles import get_profile
    if not isinstance(choice, str):
        raise ValueError('Choose a writing model')
    profile = get_profile(session, choice)
    if profile['provider'] not in ('claude', 'codex'):
        raise ValueError('Choose an OpenAI, Anthropic, Codex or Claude Code model')
    return choice


def load(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {}


def store(session, value):
    row = session.get(Metadata, KEY)
    if row:
        row.value = value
    else:
        session.add(Metadata(key=KEY, value=value))


def save(session, provider, payload):
    if provider not in PROVIDERS:
        raise ValueError('Unknown model connection')
    value = load(session)
    connection = dict(value.get(provider) or {})
    if 'api_key' in payload:
        key = payload['api_key']
        if not isinstance(key, str) or len(key) > 4096 or any(c.isspace() for c in key):
            raise ValueError('Enter a valid API key without spaces')
        if key:
            connection = {'api_key': vault.protect(key), 'models': [], 'refreshed_at': '', 'error': ''}
    if 'workspace_id' in payload:
        workspace = payload['workspace_id']
        if not isinstance(workspace, str) or (workspace and not re.fullmatch(r'[A-Za-z0-9_-]{1,150}', workspace)):
            raise ValueError('Enter a valid workspace ID')
        connection['workspace_id'] = workspace
    value[provider] = connection
    store(session, value)


def public(session):
    value = load(session)
    return {provider: {'label': label, 'configured': bool(value.get(provider, {}).get('api_key')),
                       'models': value.get(provider, {}).get('models', []),
                       'refreshed_at': value.get(provider, {}).get('refreshed_at', ''),
                       'workspace_id': value.get(provider, {}).get('workspace_id', ''),
                       'error': value.get(provider, {}).get('error', '')}
            for provider, (label, _) in PROVIDERS.items()}


def options(session):
    from .catalog import catalog
    from .profiles import list_profiles
    result = [{'id': 'auto', 'label': 'Use my default writing model', 'group': 'Default'}]
    groups = {'codex': 'OpenAI Codex - CLI sign-in', 'claude': 'Claude Code - CLI sign-in'}
    for profile in list_profiles(session):
        if profile['provider'] in groups:
            result.append({'id': profile['id'], 'label': profile['label'], 'group': groups[profile['provider']]})
    for provider, entries in catalog().items():
        for item in entries:
            if item['model']:
                connection_name = 'Codex' if provider == 'codex' else 'Claude Code'
                result.append({'id': f"catalog:{provider}:{item['model']}", 'label': f"{connection_name} - {item['label']}", 'group': groups[provider]})
    connections = public(session)
    for provider, connection in connections.items():
        if not connection['models']:
            result.append({'id': f'connect:{provider}', 'label': 'Refresh models' if connection['configured'] else 'Connect an API key to list models',
                           'group': connection['label'] + ' - API key', 'disabled': True})
        for item in connection['models']:
            result.append({'id': f"api:{provider}:{item['id']}", 'label': f"{connection['label']} - {item['label']}",
                           'group': connection['label'] + ' - API key', 'disabled': not item['text'],
                           'reason': '' if item['text'] else 'Not a text-drafting model'})
    return result


def subscription_options(session):
    """Model names via official clients, without offering API connections as sign-ins."""
    from .catalog import catalog
    from .profiles import list_profiles
    groups = {'codex': 'ChatGPT / OpenAI subscription', 'claude': 'Claude subscription'}
    result = [{'id': 'auto', 'label': 'My default subscription model', 'group': 'Default'}]
    for profile in list_profiles(session):
        provider = profile['provider']
        if provider in groups:
            label = profile['label']
            if profile['id'] in groups:
                label = 'ChatGPT plan default' if provider == 'codex' else 'Claude plan default'
            result.append({'id': profile['id'], 'label': label, 'group': groups[provider]})
    for provider, entries in catalog().items():
        if provider == 'codex' and not any(item['model'] for item in entries):
            # Known choices before the official client populates its catalog; access is unverified.
            entries = [{'model': model, 'label': label} for model, label in (
                ('gpt-6.1-sol', 'GPT-6.1-Sol'), ('gpt-6-astra', 'GPT-6-Astra'),
                ('gpt-6.1-terra', 'GPT-6.1 Terra'), ('gpt-6-sol', 'GPT-6-Sol'),
                ('gpt-6-luna', 'GPT-6-Luna'), ('gpt-5.6-sol', 'GPT-5.6-Sol'),
                ('gpt-5.6-terra', 'GPT-5.6-Terra'), ('gpt-5.6-luna', 'GPT-5.6-Luna'))]
        for item in entries:
            if item['model']:
                result.append({'id': f"catalog:{provider}:{item['model']}", 'label': item['label'],
                               'group': groups[provider]})
    return result


class Connections:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or LazyClient(timeout=90)

    def credentials(self, provider):
        if provider not in PROVIDERS:
            raise ValueError('Unknown model connection')
        with self.db.Session() as session:
            connection = dict(load(session).get(provider) or {})
        if not connection.get('api_key'):
            raise ValueError(f'Connect {PROVIDERS[provider][0]} in Prospects > Writing model first')
        key = vault.unprotect(connection['api_key'])
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
        if provider == 'anthropic':
            headers['anthropic-version'] = '2026-10-21'
            if connection.get('workspace_id'):
                headers['anthropic-workspace-id'] = connection['workspace_id']
        return connection, key, headers

    def request(self, provider, method, path, key, headers, **kwargs):
        try:
            response = self.client.request(method, PROVIDERS[provider][1] + path, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise ValueError(f'{PROVIDERS[provider][0]} could not be reached. No automatic paid retry was made.') from None
        if response.status_code >= 300:
            try:
                detail = response.json().get('error', {}).get('message', '')
            except (ValueError, AttributeError):
                detail = ''
            detail = redact(str(detail).replace(key, '[redacted]'))[:300]
            raise ValueError(f'{PROVIDERS[provider][0]} refused ({response.status_code}). {detail or "Check the key, model access, usage limit and API balance."}')
        try:
            data = response.json()
        except ValueError:
            raise ValueError(f'{PROVIDERS[provider][0]} returned an invalid response') from None
        if not isinstance(data, dict):
            raise ValueError('The provider returned an invalid response')
        return data

    def refresh(self, provider):
        connection, key, headers = self.credentials(provider)
        models, cursor, seen = {}, '', set()
        deadline = time.monotonic() + 60
        try:
            for _ in range(100):
                if time.monotonic() >= deadline:
                    raise ValueError('Model catalog refresh timed out; previous catalog was retained')
                params = {'limit': 1000} if provider == 'anthropic' else {}
                if cursor:
                    params['after_id' if provider == 'anthropic' else 'after'] = cursor
                data = self.request(provider, 'GET', '/models', key, headers, params=params, timeout=30)
                if not isinstance(data.get('data'), list):
                    raise ValueError('The provider returned an invalid model list')
                for model in data['data']:
                    identifier = model.get('id', '') if isinstance(model, dict) else ''
                    if not isinstance(identifier, str) or not MODEL_ID.fullmatch(identifier):
                        continue
                    if key in identifier or key in str(model.get('display_name') or ''):
                        continue
                    text = text_model(provider, identifier)
                    models[identifier] = {'id': identifier, 'label': str(model.get('display_name') or identifier)[:200], 'text': text}
                if not data.get('has_more'):
                    break
                last = data['data'][-1] if data['data'] else None
                cursor = data.get('last_id') or (last.get('id') if isinstance(last, dict) else '')
                if not isinstance(cursor, str) or not MODEL_ID.fullmatch(cursor) or cursor in seen:
                    raise ValueError('Model catalog pagination did not advance')
                seen.add(cursor)
            else:
                raise ValueError('Model catalog exceeded the refresh limit; previous catalog was retained')
            with self.db.Session.begin() as session:
                value = load(session)
                current = dict(value.get(provider) or {})
                if current.get('api_key') != connection['api_key'] or current.get('workspace_id') != connection.get('workspace_id'):
                    raise ValueError('The connection changed during refresh. Refresh again.')
                value[provider] = {**current, 'models': sorted(models.values(), key=lambda m: m['label'].lower()), 'refreshed_at': now(), 'error': ''}
                store(session, value)
        except ValueError as exc:
            with self.db.Session.begin() as session:
                value = load(session)
                current = dict(value.get(provider) or {})
                if current.get('api_key') == connection['api_key']:
                    value[provider] = {**current, 'error': str(exc)}
                    store(session, value)
            raise
        return {'count': len(models), 'message': f"Loaded {len(models)} models from {PROVIDERS[provider][0]}"}

    def chat(self, choice, prompt):
        provider, model = parse_choice(choice)
        if not text_model(provider, model):
            return AgentResult(False, '', error='This is not a text-drafting model. Choose a text model for Prospects.')
        try:
            _, key, headers = self.credentials(provider)
            base = base_model(model)
            if provider == 'anthropic':
                data = self.request(provider, 'POST', '/messages', key, headers,
                                    json={'model': model, 'max_tokens': 4096, 'messages': [{'role': 'user', 'content': prompt}]})
                text = '\n'.join(item.get('text', '') for item in data.get('content', []) if item.get('type') == 'text')
                incomplete = data.get('stop_reason') in ('max_tokens', 'refusal', 'model_context_window_exceeded')
            elif base.startswith(('davinci', 'babbage', 'text-davinci', 'text-curie', 'text-babbage', 'text-ada')):
                data = self.request(provider, 'POST', '/completions', key, headers,
                                    json={'model': model, 'prompt': prompt, 'max_tokens': 4096})
                first = (data.get('choices') or [{}])[0]
                text = first.get('text') or ''
                incomplete = first.get('finish_reason') in ('length', 'content_filter')
            elif base.startswith(('gpt-3.5', 'gpt-4', 'gpt-audio', 'chatgpt-', 'o1-mini', 'o1-preview')):
                token_field = 'max_completion_tokens' if base.startswith('o1') else 'max_tokens'
                data = self.request(provider, 'POST', '/chat/completions', key, headers,
                                    json={'model': model, 'messages': [{'role': 'user', 'content': prompt}], token_field: 4096, 'store': False})
                first = (data.get('choices') or [{}])[0]
                text = first.get('message', {}).get('content') or ''
                incomplete = first.get('finish_reason') in ('length', 'content_filter')
            else:
                data = self.request(provider, 'POST', '/responses', key, headers,
                                    json={'model': model, 'input': prompt, 'max_output_tokens': 4096, 'store': False})
                text = '\n'.join(part.get('text', '') for item in data.get('output', []) if item.get('type') == 'message'
                                 for part in item.get('content', []) if part.get('type') == 'output_text')
                incomplete = data.get('status') in ('incomplete', 'failed', 'cancelled', 'in_progress', 'queued')
            if incomplete or not isinstance(text, str) or not text.strip():
                raise ValueError('The model returned no complete text draft. No automatic paid retry was made.')
            usage = data.get('usage') or {}
            with self.db.Session.begin() as session:
                session.add(Event(kind='model', message=f'{PROVIDERS[provider][0]} draft: {model}',
                                  data={'provider': provider, 'model': model, 'input_tokens': usage.get('input_tokens', usage.get('prompt_tokens')),
                                        'output_tokens': usage.get('output_tokens', usage.get('completion_tokens')), 'cost': None}))
            return AgentResult(True, text.strip())
        except (ValueError, vault.VaultError) as exc:
            return AgentResult(False, '', error=str(exc))
        except (TypeError, AttributeError, KeyError):
            return AgentResult(False, '', error='The provider returned an invalid draft response. No automatic paid retry was made.')
