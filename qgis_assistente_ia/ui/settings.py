# -*- coding: utf-8 -*-
"""
Tela de configurações: chave de API, modelo, idioma e onboarding.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core import config
from ..core.llm_client import AnthropicClient, LLMError

ONBOARDING_HTML = f"""
<b>Como obter sua chave de API (uma vez só):</b>
<ol style="margin-left:-20px;">
<li>Clique em <b>Abrir console da Anthropic</b> e crie sua conta (pode usar o Gmail).</li>
<li>Em <a href="{config.BILLING_URL}">Billing</a>, adicione créditos (ex.: US$ 5).
O uso da API é cobrado à parte da assinatura do Claude.</li>
<li>Em <a href="{config.CONSOLE_URL}">API Keys</a>, clique em <i>Create Key</i>,
copie a chave (começa com <code>sk-ant-</code>) e cole abaixo.</li>
</ol>
A chave fica guardada <b>criptografada</b> no gerenciador de autenticação do QGIS
(senha mestra). Nunca compartilhe sua chave.
"""


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assistente IA: Configurações")
        self.setMinimumWidth(520)
        self.language_changed = False

        layout = QVBoxLayout(self)

        # Onboarding --------------------------------------------------------
        help_label = QLabel(ONBOARDING_HTML, self)
        help_label.setWordWrap(True)
        help_label.setOpenExternalLinks(True)
        help_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(help_label)

        btn_console = QPushButton("Abrir console da Anthropic", self)
        btn_console.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(config.CONSOLE_URL))
        )
        layout.addWidget(btn_console)

        # Chave --------------------------------------------------------------
        key_box = QGroupBox("Chave de API", self)
        key_layout = QVBoxLayout(key_box)
        row = QHBoxLayout()
        self.key_edit = QLineEdit(key_box)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(
            "Chave já salva: deixe em branco para manter" if config.has_api_key()
            else "Cole aqui sua chave sk-ant-…"
        )
        self.btn_show = QPushButton("Mostrar", key_box)
        self.btn_show.setCheckable(True)
        self.btn_show.toggled.connect(self._toggle_echo)
        row.addWidget(self.key_edit, 1)
        row.addWidget(self.btn_show)
        key_layout.addLayout(row)

        row2 = QHBoxLayout()
        self.key_status = QLabel(key_box)
        self._refresh_status()
        btn_test = QPushButton("Testar chave", key_box)
        btn_test.setToolTip("Verifica a chave sem consumir créditos")
        btn_test.clicked.connect(self._test_key)
        btn_remove = QPushButton("Remover chave", key_box)
        btn_remove.clicked.connect(self._remove_key)
        row2.addWidget(self.key_status, 1)
        row2.addWidget(btn_test)
        row2.addWidget(btn_remove)
        key_layout.addLayout(row2)
        layout.addWidget(key_box)

        # Preferências -------------------------------------------------------
        form = QFormLayout()
        self.model_combo = QComboBox(self)
        for model_id, label in config.MODELS:
            self.model_combo.addItem(label, model_id)
        self.model_combo.setCurrentIndex(
            max(0, self.model_combo.findData(config.get_model()))
        )
        form.addRow("Modelo:", self.model_combo)

        self.lang_combo = QComboBox(self)
        for code, label in config.LANGUAGE_OPTIONS:
            self.lang_combo.addItem(label, code)
        self.lang_combo.setCurrentIndex(
            max(0, self.lang_combo.findData(config.get_language()))
        )
        form.addRow("Idioma das respostas:", self.lang_combo)
        layout.addLayout(form)

        tip = QLabel(
            "<small>Dica: use o Haiku para tarefas simples (filtros, expressões) e o "
            "Sonnet para análises encadeadas e layouts.</small>", self)
        tip.setWordWrap(True)
        layout.addWidget(tip)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _toggle_echo(self, show):
        self.key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        )
        self.btn_show.setText("Ocultar" if show else "Mostrar")

    def _refresh_status(self):
        if config.has_api_key():
            self.key_status.setText("✔ Chave salva")
        else:
            self.key_status.setText("Nenhuma chave salva")

    def _typed_or_saved_key(self):
        typed = self.key_edit.text().strip()
        return typed or config.get_api_key()

    def _test_key(self):
        key = self._typed_or_saved_key()
        if not key:
            QMessageBox.warning(self, "Testar chave", "Digite ou salve uma chave primeiro.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            AnthropicClient(key, config.get_model()).check_key()
        except LLMError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Testar chave", str(e))
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Testar chave", "Chave válida! Conexão com a Anthropic OK.")

    def _remove_key(self):
        if not config.has_api_key():
            return
        answer = QMessageBox.question(self, "Remover chave",
                                      "Remover a chave de API salva neste QGIS?")
        if answer == QMessageBox.StandardButton.Yes:
            config.set_api_key("")
            self.key_edit.clear()
            self._refresh_status()

    def _save(self):
        typed = self.key_edit.text().strip()
        if typed:
            if not typed.startswith("sk-ant-"):
                answer = QMessageBox.question(
                    self, "Chave de API",
                    "A chave normalmente começa com 'sk-ant-'. Salvar mesmo assim?")
                if answer != QMessageBox.StandardButton.Yes:
                    return
            if not config.set_api_key(typed):
                QMessageBox.critical(
                    self, "Chave de API",
                    "Não foi possível salvar a chave no gerenciador de autenticação do QGIS. "
                    "Verifique a senha mestra.")
                return
        config.set_model(self.model_combo.currentData())
        new_lang = self.lang_combo.currentData()
        self.language_changed = new_lang != config.get_language()
        config.set_language(new_lang)
        self.accept()
