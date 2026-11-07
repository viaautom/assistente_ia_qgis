# -*- coding: utf-8 -*-
"""
Preferências do plugin (QgsSettings) e chave de API (QgsAuthManager).

A chave NUNCA é salva em texto puro: fica no banco de autenticação do QGIS,
criptografada com a senha mestra do usuário.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

from qgis.core import QgsApplication, QgsSettings

SETTINGS_PREFIX = "assistente_ia/"
AUTH_ENTRY_NAME = "assistente_ia/anthropic_api_key"  # pragma: allowlist secret (entry name, not a secret)

# (id do modelo, rótulo exibido)
MODELS = [
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (recomendado, ~R$ 0,09 por pedido)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (rápido e econômico, ~R$ 0,005 por pedido)"),
    ("claude-opus-5-5", "Claude Opus 5.5 (mais capaz, ~2x o custo do Sonnet)"),
]
DEFAULT_MODEL = "claude-sonnet-5-5"

LANGUAGE_OPTIONS = [("pt", "Português"), ("en", "English"), ("es", "Español")]
DEFAULT_LANGUAGE = "pt"

CONSOLE_URL = "https://platform.claude.com/settings/keys"
BILLING_URL = "https://platform.claude.com/settings/billing"


def _settings():
    return QgsSettings()


def get_model():
    model = _settings().value(SETTINGS_PREFIX + "model", DEFAULT_MODEL)
    return model if model in {m for m, _ in MODELS} else DEFAULT_MODEL


def set_model(model):
    _settings().setValue(SETTINGS_PREFIX + "model", model)


def get_language():
    return _settings().value(SETTINGS_PREFIX + "language", DEFAULT_LANGUAGE)


def set_language(code):
    _settings().setValue(SETTINGS_PREFIX + "language", code)


# ----------------------------------------------------------------------
# Chave de API (QgsAuthManager)
# ----------------------------------------------------------------------
def _auth_manager():
    return QgsApplication.authManager()


def has_api_key():
    try:
        return bool(_auth_manager().existsAuthSetting(AUTH_ENTRY_NAME))
    except Exception:  # noqa: BLE001
        return False


def get_api_key():
    """Lê a chave (pode pedir a senha mestra do QGIS). Retorna '' se ausente."""
    if not has_api_key():
        return ""
    value = _auth_manager().authSetting(AUTH_ENTRY_NAME, "", True)
    return (value or "").strip()


def set_api_key(key):
    """Salva a chave criptografada. Retorna True se deu certo."""
    am = _auth_manager()
    key = (key or "").strip()
    if not key:
        if am.existsAuthSetting(AUTH_ENTRY_NAME):
            am.removeAuthSetting(AUTH_ENTRY_NAME)
        return True
    return bool(am.storeAuthSetting(AUTH_ENTRY_NAME, key, True))


def mask_key(key):
    if not key:
        return ""
    return key[:10] + "…" + key[-4:] if len(key) > 16 else "…"
