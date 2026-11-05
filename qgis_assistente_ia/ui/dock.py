# -*- coding: utf-8 -*-
"""
Painel lateral de chat (QDockWidget).

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import html

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QPalette, QTextCursor
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#14b8a6"  # verde-azulado legível nos temas claro e escuro
ERROR = "#ef4444"


class ChatInput(QPlainTextEdit):
    """Campo de texto: Enter envia, Shift+Enter quebra linha."""

    submitted = pyqtSignal()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ChatDock(QDockWidget):
    """Painel de chat com histórico da sessão."""

    message_submitted = pyqtSignal(str)
    context_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Assistente IA", parent)
        self.setObjectName("AssistenteIADock")
        # Histórico da sessão no formato da Messages API: [{role, content}]
        self.history = []
        self._busy = False

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.view = QTextBrowser(container)
        self.view.setOpenExternalLinks(True)
        layout.addWidget(self.view, 1)

        self.status = QLabel("", container)
        self.status.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status)

        self.input = ChatInput(container)
        self.input.setPlaceholderText(
            "Descreva o que deseja fazer… (Enter envia, Shift+Enter quebra linha)"
        )
        self.input.setFixedHeight(80)
        self.input.submitted.connect(self._submit)
        layout.addWidget(self.input)

        buttons = QHBoxLayout()
        self.btn_context = QPushButton("Ver contexto", container)
        self.btn_context.setToolTip("Mostra o resumo do projeto que será enviado ao assistente")
        self.btn_context.clicked.connect(self.context_requested.emit)
        self.btn_clear = QPushButton("Limpar", container)
        self.btn_clear.setToolTip("Apaga o histórico desta conversa")
        self.btn_clear.clicked.connect(self.clear)
        self.btn_send = QPushButton("Enviar", container)
        self.btn_send.setDefault(True)
        self.btn_send.clicked.connect(self._submit)
        buttons.addWidget(self.btn_context)
        buttons.addWidget(self.btn_clear)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_send)
        layout.addLayout(buttons)

        self.setWidget(container)
        self._welcome()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def add_user_message(self, text):
        self.history.append({"role": "user", "content": text})
        self._append_block("Você", text, self._palette_color(QPalette.ColorRole.Highlight))

    def add_assistant_message(self, text):
        self.history.append({"role": "assistant", "content": text})
        self._append_block("Assistente", text, ACCENT)

    def add_info(self, text, preformatted=False):
        """Mensagem informativa (não entra no histórico enviado ao modelo)."""
        body = html.escape(text)
        if preformatted:
            body = f"<pre style='white-space: pre-wrap;'>{body}</pre>"
        else:
            body = body.replace("\n", "<br>")
        self._append_html(f"<p style='color: gray;'><i>{body}</i></p>")

    def add_error(self, text):
        self._append_block("Erro", text, ERROR)

    def set_busy(self, busy, message=""):
        self._busy = busy
        self.btn_send.setEnabled(not busy)
        self.input.setReadOnly(busy)
        self.status.setText(message if busy else "")

    def clear(self):
        self.history = []
        self.view.clear()
        self._welcome()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------
    def _submit(self):
        if self._busy:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.add_user_message(text)
        self.message_submitted.emit(text)

    def _welcome(self):
        self._append_html(
            f"<p><b style='color:{ACCENT};'>Assistente IA para QGIS</b><br>"
            "Descreva em português o que deseja fazer com seu projeto. "
            "O código gerado sempre será mostrado antes de executar.</p>"
        )

    def _palette_color(self, role):
        return self.palette().color(role).name()

    def _append_block(self, author, text, color):
        body = html.escape(text).replace("\n", "<br>")
        self._append_html(
            f"<p style='margin-top:8px;'><b style='color:{color};'>{author}</b><br>{body}</p>"
        )

    def _append_html(self, fragment):
        self.view.append(fragment)
        self.view.moveCursor(QTextCursor.MoveOperation.End)
        self.view.ensureCursorVisible()
