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
from qgis.PyQt.QtWidgets import QAction, QApplication, QFileDialog, QMessageBox

from .core import config
from .core.context import collect_context, context_to_text
from .core.executor import analyze, execute, extract_code_blocks
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
MAX_FIX_ATTEMPTS = 2


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
        # Blocos de código exibidos: id -> {"code": str, "attempt": int}
        self.codes = {}
        self._next_code_id = 1
        # Resultado da última execução, enviado junto da próxima mensagem.
        self.last_exec_note = None

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
            self.dock.code_action.connect(self.on_code_action)
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
        self.codes = {}
        self.last_exec_note = None
        self.dock.clear()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def on_message(self, text):
        self._send(text)

    def _send(self, text, fix_attempt=0):
        """Envia uma mensagem ao Claude. fix_attempt > 0 = pedido de correção."""
        if self.task is not None:
            self.dock.add_info("Aguarde a resposta anterior terminar.")
            return
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
        if self.last_exec_note and not fix_attempt:
            context_text += f"\n\nResultado da última execução de código: {self.last_exec_note}"
        self.last_exec_note = None
        conversation.add_user(text, context_text)
        log(f"Enviando pedido ao {model}:\n{text}\n--- Contexto ---\n{context_text}")

        def on_done(response, error):
            self.task = None
            if self.dock is None:
                return
            self.dock.set_busy(False)
            if conversation is not self.conversation:
                return  # a conversa foi limpa enquanto aguardava
            self._handle_response(conversation, model, response, error, fix_attempt)

        busy_msg = (f"Pedindo correção ao Claude (tentativa {fix_attempt} de "
                    f"{MAX_FIX_ATTEMPTS})…" if fix_attempt else f"Consultando o Claude ({model})…")
        self.dock.set_busy(True, busy_msg)
        self.task = ChatTask(client, conversation, on_done)
        QgsApplication.taskManager().addTask(self.task)

    def _handle_response(self, conversation, model, response, error, fix_attempt):
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
        code_ids = []
        for code in extract_code_blocks(text):
            code_id = self._next_code_id
            self._next_code_id += 1
            self.codes[code_id] = {"code": code, "attempt": fix_attempt}
            code_ids.append(code_id)
        self.dock.add_assistant_message(text or "(sem texto na resposta)", code_ids)
        if stop == "max_tokens":
            self.dock.add_info("A resposta foi cortada por tamanho. Peça para continuar "
                               "ou divida o pedido em partes menores.")

    # ------------------------------------------------------------------
    # Código: executar, copiar, salvar
    # ------------------------------------------------------------------
    def on_code_action(self, action, code_id):
        item = self.codes.get(code_id)
        if item is None:
            self.dock.add_info("Este código é de uma conversa anterior e não está mais disponível.")
            return
        if action == "run":
            self._run_code(item)
        elif action == "copy":
            QApplication.clipboard().setText(item["code"])
            self.iface.messageBar().pushMessage(PLUGIN_NAME, "Código copiado.",
                                                level=Qgis.Success, duration=3)
        elif action == "save":
            self._save_code(item["code"])

    def _run_code(self, item):
        code, attempt = item["code"], item["attempt"]
        analysis = analyze(code)

        if analysis.blocked:
            self.dock.add_error(
                "Execução bloqueada por segurança. O código:\n- "
                + "\n- ".join(analysis.blocked)
                + "\nPeça ao assistente uma alternativa sem essas operações.")
            log("Execução bloqueada: " + "; ".join(analysis.blocked), Qgis.Warning)
            return

        if analysis.syntax_error:
            self._on_exec_error(code, attempt, analysis.syntax_error, "")
            return

        message = "Executar este código no projeto atual?"
        if analysis.warnings:
            message += "\n\nAtenção, o código:\n• " + "\n• ".join(analysis.warnings)
            message += "\n\nRecomenda-se salvar o projeto antes."
        box = QMessageBox(self.iface.mainWindow())
        box.setWindowTitle("Assistente IA: confirmar execução")
        box.setIcon(QMessageBox.Icon.Warning if analysis.warnings else QMessageBox.Icon.Question)
        box.setText(message)
        box.setDetailedText(code)
        btn_run = box.addButton("Executar", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not btn_run:
            return

        log("Executando código:\n" + code)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = execute(code, self.iface)
        finally:
            QApplication.restoreOverrideCursor()
        self.iface.mapCanvas().refreshAllLayers()

        if result.ok:
            self.dock.add_success("Código executado com sucesso.", result.output)
            log("Execução OK. Saída:\n" + result.output, Qgis.Success)
            out = result.output.strip()[-500:]
            self.last_exec_note = "sucesso." + (f" Saída: {out}" if out else "")
        else:
            self._on_exec_error(code, attempt, result.error, result.output)

    def _on_exec_error(self, code, attempt, error, output):
        self.dock.add_error(f"O código deu erro:\n{error}")
        log(f"Erro na execução:\n{error}\nSaída:\n{output}", Qgis.Warning)
        if attempt >= MAX_FIX_ATTEMPTS:
            self.last_exec_note = f"erro: {error[-500:]}"
            self.dock.add_info(
                f"A correção automática já foi tentada {MAX_FIX_ATTEMPTS} vezes. "
                "Descreva o problema com outras palavras ou simplifique o pedido.")
            return
        next_attempt = attempt + 1
        self.dock.add_info(f"Enviando o erro ao assistente para correção automática "
                           f"(tentativa {next_attempt} de {MAX_FIX_ATTEMPTS})…")
        fix_request = (
            "O código que você gerou deu erro ao ser executado no QGIS:\n"
            f"```\n{error}\n```\n"
            + (f"Saída antes do erro:\n```\n{output.strip()[-1500:]}\n```\n" if output.strip() else "")
            + "Corrija o problema e envie o código completo novamente, em um único bloco. "
              "Considere que a parte que rodou antes do erro pode já ter alterado o projeto."
        )
        self._send(fix_request, fix_attempt=next_attempt)

    def _save_code(self, code):
        path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), "Salvar como script",
            os.path.join(os.path.expanduser("~"), "script_assistente_ia.py"),
            "Script Python (*.py)")
        if not path:
            return
        if not path.lower().endswith(".py"):
            path += ".py"
        header = ("# Gerado pelo Assistente IA para QGIS (Ibexdev)\n"
                  "# Para usar: abra o Console Python do QGIS > Editor > Abrir script.\n\n")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(header + code + "\n")
        except OSError as e:
            self.dock.add_error(f"Não foi possível salvar o script: {e}")
            return
        self.iface.messageBar().pushMessage(PLUGIN_NAME, f"Script salvo em {path}",
                                            level=Qgis.Success, duration=5)

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
