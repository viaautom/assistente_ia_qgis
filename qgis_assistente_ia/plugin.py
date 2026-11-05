# -*- coding: utf-8 -*-
"""
Registro do plugin: menu, barra de ferramentas e ícone.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import os

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .core.context import collect_context, context_to_text
from .ui.dock import ChatDock

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
        self.dock = None  # painel de chat (etapa 2)

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
        self.action_about = self._add_action(
            QIcon(),
            "Sobre",
            self.show_about,
        )

        log("Plugin carregado.")

    def unload(self):
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
    # Ações
    # ------------------------------------------------------------------
    def open_chat(self, checked=None):
        """Mostra/oculta o painel de chat (cria na primeira vez)."""
        if self.dock is None:
            self.dock = ChatDock(self.iface.mainWindow())
            self.dock.message_submitted.connect(self.on_message)
            self.dock.context_requested.connect(self.show_context)
            self.dock.visibilityChanged.connect(self.action_chat.setChecked)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
            self.dock.show()
        else:
            self.dock.setVisible(not self.dock.isVisible())
        if self.dock.isVisible():
            self.dock.raise_()
            self.dock.input.setFocus()

    def show_context(self):
        text = context_to_text(collect_context(self.iface))
        log("Contexto do projeto:\n" + text)
        self.dock.add_info("Contexto que será enviado ao assistente:\n\n" + text, preformatted=True)

    def on_message(self, text):
        # Etapa 3: aqui a mensagem e o contexto serão enviados ao Claude (QgsTask).
        ctx = collect_context(self.iface)
        log(f"Mensagem do usuário: {text}\n--- Contexto ---\n{context_to_text(ctx)}")
        self.dock.add_info(
            f"(A conexão com o Claude chega na etapa 3.) Contexto coletado com "
            f"{ctx['total_camadas']} camada(s); detalhes em Mensagens de log > {LOG_TAG}."
        )

    def open_settings(self):
        # Etapa 3 substituirá este aviso pela tela de configurações.
        log("Ação 'Configurações' acionada.")
        self.iface.messageBar().pushMessage(
            PLUGIN_NAME,
            "Tela de configurações em construção (etapa 3).",
            level=Qgis.Info,
            duration=4,
        )

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
