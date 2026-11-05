"""AI providers for the Provider Portal feedback channel.

Only anonymized feedback text reaches this module. The default DEV backend is
the local OpenCode server: replies use the configured chat context through the
transient ``/api/session/{id}/generate`` endpoint, which does not append the
message to the conversation history. The DeepSeek chat-completions backend
remains available, and a new provider only needs to implement ``generate`` and
register itself in ``PROVIDERS``.

A feedback record is never lost when AI is disabled, unconfigured or
unavailable: the caller receives a stable contract with ``status`` and ``erro``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

LOG = logging.getLogger('autoseg.feedback.ai')

MAX_AI_REPLY = 3000
MAX_IMPROVEMENT = 1500
MAX_ANONYMIZED_MESSAGE = 4000

LOCAL_CONFIG = Path(__file__).with_name('feedback_ia.local.json')
DEFAULT_OPENCODE_URL = 'http://127.0.0.1:49374'
DEFAULT_OPENCODE_TIMEOUT = 60.0
DEFAULT_DEEPSEEK_URL = 'https://api.deepseek.com/chat/completions'
DEFAULT_DEEPSEEK_MODEL = 'deepseek-chat'
DEFAULT_DEEPSEEK_TIMEOUT = 25.0
DEFAULT_OPENCODE_SERVICE = Path.home() / '.config' / 'opencode' / 'service.json'


class AIUnavailable(Exception):
    """Missing configuration or an unusable provider response."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class AIProvider(Protocol):
    name: str

    def generate(self, prompt: str) -> str:
        """Return the raw model text for the given prompt."""


def _read_config() -> dict:
    """Read the optional local configuration without logging its contents."""
    try:
        data = json.loads(LOCAL_CONFIG.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        LOG.warning('Invalid local AI configuration; using environment variables.')
        return {}
    return data if isinstance(data, dict) else {}


def _section(name: str) -> dict:
    section = _read_config().get(name)
    return section if isinstance(section, dict) else {}


def _env(name: str, default: Any = '') -> str:
    """Environment wins over the local file, including when it is empty."""
    if name in os.environ:
        return str(os.environ.get(name) or '').strip()
    return str(default or '').strip()


def _timeout(env_name: str, value: Any, default: float) -> float:
    raw = _env(env_name, value if value is not None else default)
    try:
        return max(5.0, min(120.0, float(raw)))
    except (TypeError, ValueError):
        return default


def _disabled() -> bool:
    return _env('AUTOSEG_FEEDBACK_AI', '1').lower() in (
        '0', 'off', 'false', 'nao', 'não'
    )


def current_provider() -> str:
    name = _env(
        'AUTOSEG_FEEDBACK_AI_PROVIDER',
        _read_config().get('provider') or 'opencode',
    )
    return name.lower()


def _failure(status: str, message: str) -> dict:
    return {
        'status': status,
        'resposta': '',
        'categoria': 'Não classificada',
        'urgencia': 'Não classificada',
        'possivel_melhoria': '',
        'confianca': 0.0,
        'erro': message,
    }


def _build_prompt(system_prompt: str, anonymized_message: str) -> str:
    return (
        str(system_prompt or '')
        + '\n\nFeedback anonimizado do usuário:\n"""\n'
        + str(anonymized_message or '')[:MAX_ANONYMIZED_MESSAGE]
        + '\n"""\n\nResponda somente com o objeto JSON pedido.'
    )


def _post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(200_000)
    data = json.loads(raw.decode('utf-8', 'replace'))
    if not isinstance(data, dict):
        raise ValueError('JSON response is not an object.')
    return data


def _opencode_password() -> str:
    password = _env('AUTOSEG_FEEDBACK_OPENCODE_PASSWORD')
    if password:
        return password
    path = Path(_env(
        'AUTOSEG_FEEDBACK_OPENCODE_SERVICE_FILE',
        str(DEFAULT_OPENCODE_SERVICE),
    )).expanduser()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    if not isinstance(data, dict):
        return ''
    return str(data.get('password') or '').strip()


class OpenCodeProvider:
    """Transient reply from the context of an OpenCode chat.

    The endpoint used here does not persist the question or the answer in the
    session history. Authentication is the local service HTTP Basic credential,
    read from ``~/.config/opencode/service.json`` or environment variables.
    """

    name = 'opencode'

    def generate(self, prompt: str) -> str:
        config = _section('opencode')
        base_url = _env(
            'AUTOSEG_FEEDBACK_OPENCODE_URL',
            config.get('base_url') or DEFAULT_OPENCODE_URL,
        ).rstrip('/')
        session_id = _env(
            'AUTOSEG_FEEDBACK_OPENCODE_SESSION',
            config.get('session_id') or '',
        )
        if not base_url.startswith(('http://', 'https://')):
            raise AIUnavailable(
                'sem_configuracao',
                'A URL do OpenCode configurada para a IA não é válida. '
                'O feedback foi registrado para análise humana.',
            )
        if not session_id:
            raise AIUnavailable(
                'sem_configuracao',
                'A resposta automática por IA ainda não foi configurada neste '
                'servidor. O feedback foi registrado para análise humana.',
            )
        password = _opencode_password()
        if not password:
            raise AIUnavailable(
                'sem_configuracao',
                'Não foi possível autenticar no serviço de IA local. '
                'O feedback foi registrado para análise humana.',
            )
        url = (
            base_url
            + '/api/session/'
            + urllib.parse.quote(session_id, safe='')
            + '/generate'
        )
        authorization = base64.b64encode(
            f'opencode:{password}'.encode('utf-8')
        ).decode('ascii')
        timeout = _timeout(
            'AUTOSEG_FEEDBACK_OPENCODE_TIMEOUT',
            config.get('timeout'),
            DEFAULT_OPENCODE_TIMEOUT,
        )
        try:
            data = _post_json(
                url,
                {
                    'Content-Type': 'application/json',
                    'Authorization': 'Basic ' + authorization,
                    'User-Agent': 'AUTOSEG-Feedback/1',
                },
                {'prompt': prompt},
                timeout,
            )
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 404):
                LOG.warning(
                    'OpenCode rejected the session or authentication (HTTP %s).',
                    error.code,
                )
                raise AIUnavailable(
                    'sem_configuracao',
                    'O chat configurado para a IA não está disponível. '
                    'O feedback foi registrado para análise humana.',
                ) from None
            raise
        inner = data.get('data')
        text = ''
        if isinstance(inner, dict):
            text = str(inner.get('text') or '').strip()
        if not text:
            raise AIUnavailable(
                'erro',
                'A IA não devolveu uma resposta. '
                'O feedback foi registrado para análise humana.',
            )
        return text


class DeepSeekProvider:
    """Alternative chat-completions backend compatible with DeepSeek."""

    name = 'deepseek'

    def generate(self, prompt: str) -> str:
        config = _section('deepseek')
        api_key = _env('DEEPSEEK_API_KEY')
        if not api_key:
            raise AIUnavailable(
                'sem_chave',
                'A resposta automática por IA ainda não foi configurada neste '
                'servidor. O feedback foi registrado para análise humana.',
            )
        url = _env(
            'DEEPSEEK_API_URL',
            config.get('base_url') or DEFAULT_DEEPSEEK_URL,
        )
        model = _env(
            'DEEPSEEK_MODEL',
            config.get('model') or DEFAULT_DEEPSEEK_MODEL,
        )
        timeout = _timeout(
            'DEEPSEEK_TIMEOUT',
            config.get('timeout'),
            DEFAULT_DEEPSEEK_TIMEOUT,
        )
        body = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': prompt},
            ],
            'temperature': 0.2,
            'max_tokens': 900,
            'stream': False,
            'response_format': {'type': 'json_object'},
        }
        data = _post_json(
            url,
            {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + api_key,
                'User-Agent': 'AUTOSEG-Feedback/1',
            },
            body,
            timeout,
        )
        choices = data.get('choices') or []
        content = ''
        if choices:
            content = str(
                (choices[0].get('message') or {}).get('content') or ''
            )
        if not content.strip():
            raise AIUnavailable(
                'erro',
                'A IA não devolveu uma resposta. '
                'O feedback foi registrado para análise humana.',
            )
        return content


PROVIDERS: dict[str, AIProvider] = {
    OpenCodeProvider.name: OpenCodeProvider(),
    DeepSeekProvider.name: DeepSeekProvider(),
}


def _extract_json(content: str) -> dict:
    text = str(content or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}


def _normalize_category(value: Any) -> str:
    text = str(value or '').strip().casefold()
    mapping = {
        'duvida': 'Dúvida', 'dúvida': 'Dúvida',
        'bug': 'Bug', 'erro': 'Bug', 'defeito': 'Bug',
        'melhoria': 'Melhoria', 'sugestao': 'Melhoria', 'sugestão': 'Melhoria',
        'elogio': 'Elogio', 'outro': 'Outro',
    }
    return mapping.get(text, 'Outro')


def _normalize_urgency(value: Any) -> str:
    text = str(value or '').strip().casefold()
    mapping = {
        'baixa': 'Baixa', 'baixo': 'Baixa',
        'media': 'Média', 'média': 'Média', 'medio': 'Média', 'médio': 'Média',
        'alta': 'Alta', 'alto': 'Alta', 'critica': 'Alta', 'crítica': 'Alta',
    }
    return mapping.get(text, 'Não classificada')


def _analyze_text(content: str) -> dict:
    text = str(content or '').strip()
    analysis = _extract_json(text)
    if not analysis:
        return {
            'status': 'ok',
            'resposta': text[:MAX_AI_REPLY],
            'categoria': 'Não classificada',
            'urgencia': 'Não classificada',
            'possivel_melhoria': '',
            'confianca': 0.0,
            'erro': '',
        }
    try:
        confidence = max(0.0, min(1.0, float(analysis.get('confianca', 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    reply = str(analysis.get('resposta') or '').strip()[:MAX_AI_REPLY]
    if not reply:
        reply = 'O feedback foi recebido e será analisado pela equipe.'
    improvement = str(
        analysis.get('possivel_melhoria') or ''
    ).strip()[:MAX_IMPROVEMENT]
    if improvement.casefold() in ('null', 'none', 'nenhuma'):
        improvement = ''
    return {
        'status': 'ok',
        'resposta': reply,
        'categoria': _normalize_category(analysis.get('categoria')),
        'urgencia': _normalize_urgency(analysis.get('urgencia')),
        'possivel_melhoria': improvement,
        'confianca': confidence,
        'erro': '',
    }


def consult(anonymized_message: str, system_prompt: str) -> dict:
    """Query the configured provider and return the stable UI contract."""
    if _disabled():
        return _failure(
            'desativada',
            'A resposta automática por IA está desativada neste servidor.',
        )
    name = current_provider()
    provider = PROVIDERS.get(name)
    if not provider:
        LOG.warning('Unknown AI provider: %s', name[:40])
        return _failure(
            'configuracao_invalida',
            'O provedor de IA configurado não é reconhecido. '
            'O feedback foi registrado para análise humana.',
        )
    prompt = _build_prompt(system_prompt, anonymized_message)
    try:
        text = provider.generate(prompt)
    except AIUnavailable as error:
        return _failure(error.status, str(error))
    except urllib.error.HTTPError as error:
        LOG.warning('AI provider %s returned HTTP %s', name, error.code)
        return _failure(
            'erro',
            f'A IA recusou a consulta (HTTP {error.code}). '
            'O feedback foi registrado para análise humana.',
        )
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        LOG.warning(
            'AI provider %s unavailable: %s',
            name,
            type(error).__name__,
        )
        return _failure(
            'erro',
            'A IA está indisponível no momento. '
            'O feedback foi registrado para análise humana.',
        )
    except (ValueError, KeyError, TypeError):
        LOG.warning(
            'Invalid response from AI provider %s',
            name,
            exc_info=True,
        )
        return _failure(
            'erro',
            'A IA devolveu uma resposta inválida. '
            'O feedback foi registrado para análise humana.',
        )
    return _analyze_text(text)
