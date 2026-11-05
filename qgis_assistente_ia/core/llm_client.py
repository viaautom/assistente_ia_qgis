# -*- coding: utf-8 -*-
"""
Cliente da API Anthropic (Messages API) via HTTP, só com a biblioteca padrão.

- BaseLLMClient: interface abstrata (chave própria hoje; proxy Ibexdev na fase 3).
- AnthropicClient: chamada direta a api.anthropic.com com a chave do usuário.
- Conversation: histórico da sessão, apenas com acréscimos (append-only).
- ChatTask: QgsTask que faz a chamada fora da thread da interface.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import json
import socket
import ssl
import time
import urllib.error
import urllib.request

from qgis.core import QgsTask

from .prompts import build_user_content

API_URL = "https://api.anthropic.com/v1/messages"
MODELS_URL = "https://api.anthropic.com/v1/models"
API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
USER_AGENT = "qgis-assistente-ia/0.1.0"

MAX_TOKENS = 16000
TIMEOUT_S = 300
MAX_RETRIES = 2

# Modelos com fallback no servidor quando o classificador de segurança recusa.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}

# Preço por milhão de tokens (US$) para estimar custo no log.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


class LLMError(Exception):
    """Erro com mensagem amigável, em português, para mostrar no chat."""

    def __init__(self, message, status=None, retryable=False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def _ssl_context():
    try:
        import certifi  # incluído no Python do QGIS na maioria das instalações

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def _friendly_error(status, body):
    """Converte a resposta de erro da API em mensagem para o usuário."""
    api_type, api_msg = "", ""
    try:
        err = json.loads(body).get("error", {})
        api_type, api_msg = err.get("type", ""), err.get("message", "")
    except Exception:  # noqa: BLE001
        api_msg = (body or "")[:300]

    lower = api_msg.lower()
    if status == 401:
        msg = "Chave de API inválida. Confira a chave em Configurações."
    elif status == 403:
        msg = "Sua chave não tem permissão para este recurso ou modelo."
    elif status == 400 and ("credit" in lower or "billing" in lower):
        msg = ("Saldo de créditos insuficiente na conta Anthropic. "
               "Adicione créditos em console.anthropic.com > Billing.")
    elif status == 404:
        msg = "Modelo não encontrado. Escolha outro modelo em Configurações."
    elif status == 413:
        msg = "A conversa ficou grande demais. Clique em Limpar e recomece."
    elif status == 429:
        msg = "Limite de uso da API atingido. Aguarde alguns segundos e tente de novo."
    elif status in (500, 502, 503, 504, 529):
        msg = "A API da Anthropic está sobrecarregada ou instável. Tente novamente em instantes."
    else:
        msg = f"Erro da API (HTTP {status})."
    detail = f" [{api_type}: {api_msg}]" if api_msg else ""
    retryable = status in (408, 409, 429, 500, 502, 503, 504, 529)
    return LLMError(msg + detail, status=status, retryable=retryable)


class BaseLLMClient:
    """Interface comum aos provedores (chave própria, proxy Ibexdev...)."""

    model = None

    def send(self, system, messages):
        """Envia a conversa e retorna o dicionário de resposta da Messages API."""
        raise NotImplementedError


class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key, model, timeout=TIMEOUT_S):
        if not api_key:
            raise LLMError("Nenhuma chave de API configurada. Abra Configurações.")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._ctx = _ssl_context()

    # --------------------------------------------------------------
    def _headers(self, beta=None):
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "user-agent": USER_AGENT,
        }
        if beta:
            headers["anthropic-beta"] = beta
        return headers

    def _request(self, url, data=None, headers=None, timeout=None):
        req = urllib.request.Request(url, data=data, headers=headers or self._headers(),
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout,
                                        context=self._ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            err = _friendly_error(e.code, body)
            err.retry_after = e.headers.get("retry-after")
            raise err from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            reason = getattr(e, "reason", e)
            raise LLMError(
                f"Falha de conexão com a API da Anthropic ({reason}). "
                "Verifique a internet, o proxy ou o firewall.",
                retryable=True,
            ) from None

    # --------------------------------------------------------------
    def send(self, system, messages, is_canceled=None):
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": messages,
            # Cache automático do prefixo (sistema + histórico): reduz custo.
            "cache_control": {"type": "ephemeral"},
            "output_config": {"effort": "medium"},
        }
        beta = None
        if self.model in FALLBACK_MODELS:
            body["fallbacks"] = "default"
            beta = FALLBACK_BETA

        data = json.dumps(body).encode("utf-8")
        attempt = 0
        while True:
            try:
                return self._request(API_URL, data=data, headers=self._headers(beta))
            except LLMError as e:
                if not e.retryable or attempt >= MAX_RETRIES or (is_canceled and is_canceled()):
                    raise
                attempt += 1
                wait = 2 ** attempt
                try:
                    wait = max(wait, min(30, float(getattr(e, "retry_after", None) or 0)))
                except ValueError:
                    pass
                time.sleep(wait)

    def check_key(self):
        """Valida a chave listando modelos (não consome créditos)."""
        self._request(MODELS_URL + "?limit=1", timeout=20)
        return True


# ----------------------------------------------------------------------
def response_text(response):
    """Junta os blocos de texto da resposta (ignora blocos de raciocínio)."""
    parts = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def usage_summary(response, model):
    u = response.get("usage", {}) or {}
    inp = u.get("input_tokens", 0) or 0
    out = u.get("output_tokens", 0) or 0
    cw = u.get("cache_creation_input_tokens", 0) or 0
    cr = u.get("cache_read_input_tokens", 0) or 0
    pin, pout = PRICES.get(model, (0, 0))
    cost = (inp * pin + cw * pin * 1.25 + cr * pin * 0.1 + out * pout) / 1_000_000
    return (f"tokens: entrada {inp}, cache gravado {cw}, cache lido {cr}, saída {out} "
            f"| custo estimado US$ {cost:.4f}")


class Conversation:
    """Histórico da sessão no formato da Messages API.

    Regra: apenas acrescentar. Respostas do assistente são guardadas com
    TODOS os blocos devolvidos pela API (inclusive raciocínio) e reenviadas
    sem alteração; o prompt de sistema é fixo durante a conversa.
    """

    def __init__(self, system_prompt):
        self.system = system_prompt
        self.messages = []

    def add_user(self, text, context_text):
        self.messages.append({
            "role": "user",
            "content": [{"type": "text", "text": build_user_content(text, context_text)}],
        })

    def add_assistant(self, response):
        self.messages.append({"role": "assistant", "content": response.get("content", [])})

    def discard_last_user(self):
        """Remove a última mensagem do usuário quando a chamada falhou (fim da lista)."""
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()


class ChatTask(QgsTask):
    """Faz a chamada à API em segundo plano e devolve o resultado na thread principal."""

    def __init__(self, client, conversation, on_done):
        super().__init__("Assistente IA: consultando o Claude", QgsTask.CanCancel)
        self.client = client
        self.system = conversation.system
        self.messages = [dict(m) for m in conversation.messages]  # cópia rasa
        self.on_done = on_done
        self.response = None
        self.error = None

    def run(self):
        try:
            self.response = self.client.send(self.system, self.messages, self.isCanceled)
            return True
        except LLMError as e:
            self.error = e
        except Exception as e:  # noqa: BLE001
            self.error = LLMError(f"Erro inesperado: {e!r}")
        return False

    def finished(self, result):  # roda na thread principal
        if self.isCanceled() and self.error is None and self.response is None:
            self.error = LLMError("Pedido cancelado.")
        self.on_done(self.response, self.error)
