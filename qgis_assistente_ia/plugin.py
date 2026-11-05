# -*- coding: utf-8 -*-
"""
Registro do plugin: menu, barra de ferramentas, painel e fluxo do chat.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import os

from qgis.core import Qgis, QgsApplication, QgsMessageLog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .core import config
from .core.context import collect_context, context_to_text
from .core.llm_client import (
    AnthropicClient,
    ChatTask,
    Conversation,
    LLMError,
    response_text,
    usage_summary,
)
from .core.prompts import build_system_prompt
from .ui.dock import ChatDock
from .ui.settings import SettingsDialog

PLUGIN_NAME = "Assistente IA"
MENU_NAME = "&Assistente IA"
LOG_TAG = "Assistente IA"
PLUGIN_DIR = os.path.dirname(__file__)


def log(message, level=Qgis.Info):
    """Escreve no painel Mensagens de log, aba 'Assistente IA'."""
    QgsMessageLog.logMessage(message, LOG_TAG, level)


class AssistenteIAPlugin:
    """Classe principal do plugin, instanciada pelo QGIS via classFactory."""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = None
        self.dock = None
        self.conversation = None  # criada na primeira mensagem
        self.task = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def initGui(self):  # noqa: N802
        icon = QIcon(os.path.join(PLUGIN_DIR, "icon.png"))

        self.toolbar = self.iface.addToolBar(PLUGIN_NAME)
        self.toolbar.setObjectName("AssistenteIAToolbar")

        self.action_chat = self._add_action(
            icon,
            "Abrir Assistente IA",
            self.open_chat,
            status_tip="Abre o painel de chat do Assistente IA",
            add_to_toolbar=True,
        )
        self.action_chat.setCheckable(True)
        self.action_settings = self._add_action(
            QIcon(),
            "Configurações…",
            self.open_settings,
            status_tip="Chave de API, modelo e idioma",
        )
        self.action_about = self._add_action(QIcon(), "Sobre", self.show_about)

        log("Plugin carregado.")

    def unload(self):
        if self.task is not None:
            try:
                self.task.cancel()
            except RuntimeError:
                pass
            self.task = None

        for action in self.actions:
            self.iface.removePluginMenu(MENU_NAME, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None

        if self.dock is not None:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None

        log("Plugin descarregado.")

    # ------------------------------------------------------------------
    # Painel
    # ------------------------------------------------------------------
    def open_chat(self, checked=None):
        """Mostra/oculta o painel de chat (cria na primeira vez)."""
        if self.dock is None:
            self.dock = ChatDock(self.iface.mainWindow())
            self.dock.message_submitted.connect(self.on_message)
            self.dock.context_requested.connect(self.show_context)
            self.dock.clear_requested.connect(self.clear_conversation)
            self.dock.settings_requested.connect(self.open_settings)
            self.dock.visibilityChanged.connect(self.action_chat.setChecked)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
            self.dock.show()
            if not config.has_api_key():
                self.dock.add_info(
                    "Para começar, configure sua chave de API da Anthropic no botão ⚙.")
        else:
            self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self.dock.raise_()
            self.dock.input.setFocus()

    def show_context(self):
        text = context_to_text(collect_context(self.iface))
        log("Contexto do projeto:\n" + text)
        self.dock.add_info("Contexto que será enviado ao assistente:\n\n" + text, preformatted=True)

    def clear_conversation(self):
        self.conversation = None  # a próxima mensagem inicia uma conversa nova
        self.dock.clear()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def on_message(self, text):
        if not config.has_api_key():
            self.dock.add_error("Nenhuma chave de API configurada. Abrindo Configurações…")
            self.open_settings()
            if not config.has_api_key():
                return

        api_key = config.get_api_key()  # pode pedir a senha mestra do QGIS
        if not api_key:
            self.dock.add_error("Não foi possível ler a chave de API (senha mestra cancelada?).")
            return

        model = config.get_model()
        try:
            client = AnthropicClient(api_key, model)
        except LLMError as e:
            self.dock.add_error(str(e))
            return

        if self.conversation is None:
            self.conversation = Conversation(build_system_prompt(config.get_language()))
        conversation = self.conversation

        context_text = context_to_text(collect_context(self.iface))
        conversation.add_user(text, context_text)
        log(f"Enviando pedido ao {model}:\n{text}\n--- Contexto ---\n{context_text}")

        def on_done(response, error):
            self.task = None
            if self.dock is None:
                return
            self.dock.set_busy(False)
            if conversation is not self.conversation:
                return  # a conversa foi limpa enquanto aguardava
            self._handle_response(conversation, model, response, error)

        self.dock.set_busy(True, f"Consultando o Claude ({model})…")
        self.task = ChatTask(client, conversation, on_done)
        QgsApplication.taskManager().addTask(self.task)

    def _handle_response(self, conversation, model, response, error):
        if error is not None:
            conversation.discard_last_user()
            self.dock.add_error(str(error))
            log(f"Erro na chamada: {error}", Qgis.Warning)
            return

        log(f"Resposta de {response.get('model', model)} "
            f"(stop_reason={response.get('stop_reason')}) | {usage_summary(response, model)}")

        stop = response.get("stop_reason")
        text = response_text(response)

        if stop == "refusal":
            if response.get("content"):
                conversation.add_assistant(response)
            else:
                conversation.discard_last_user()
            self.dock.add_error(
                "O modelo recusou este pedido pelos filtros de segurança. "
                "Reformule a solicitação.")
            return

        if not response.get("content"):
            conversation.discard_last_user()
            self.dock.add_error("A API devolveu uma resposta vazia. Tente novamente.")
            return

        conversation.add_assistant(response)
        self.dock.add_assistant_message(text or "(sem texto na resposta)")
        if stop == "max_tokens":
            self.dock.add_info("A resposta foi cortada por tamanho. Peça para continuar "
                               "ou divida o pedido em partes menores.")

    # ------------------------------------------------------------------
    # Configurações e Sobre
    # ------------------------------------------------------------------
    def open_settings(self, checked=None):
        dialog = SettingsDialog(self.iface.mainWindow())
        if dialog.exec():
            log(f"Configurações salvas (modelo: {config.get_model()}, "
                f"idioma: {config.get_language()}).")
            if dialog.language_changed and self.conversation is not None:
                if self.conversation.messages:
                    if self.dock is not None:
                        self.dock.add_info(
                            "O novo idioma vale a partir da próxima conversa (clique em Limpar).")
                else:
                    self.conversation = None

    def show_about(self):
        QMessageBox.about(
            self.iface.mainWindow(),
            "Sobre o Assistente IA para QGIS",
            "<b>Assistente IA para QGIS</b> v0.1.0<br><br>"
            "Descreva em português o que deseja fazer e o assistente "
            "gera código PyQGIS, sempre com sua confirmação antes de executar.<br><br>"
            "Desenvolvido pela <b>Ibexdev</b>.<br>"
            "Licença GNU GPL v2 ou superior.",
        )

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------
    def _add_action(self, icon, text, callback, status_tip=None, add_to_toolbar=False):
        action = QAction(icon, text, self.iface.mainWindow())
        action.triggered.connect(callback)
        if status_tip:
            action.setStatusTip(status_tip)
        self.iface.addPluginToMenu(MENU_NAME, action)
        if add_to_toolbar:
            self.toolbar.addAction(action)
        self.actions.append(action)
        return action
