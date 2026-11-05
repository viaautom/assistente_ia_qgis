# -*- coding: utf-8 -*-
"""
Validação e execução do código PyQGIS gerado pelo assistente.

- extract_code_blocks: separa os blocos ```python da resposta.
- analyze: análise estática simples (AST) que BLOQUEIA operações perigosas
  (apagar arquivos, os.system, subprocess, rede, eval/exec...) e AVISA
  sobre operações que alteram dados.
- execute: roda o código na thread principal (exigência do PyQGIS),
  capturando a saída (print) e os erros.

A análise é uma camada de proteção, não uma sandbox: o código só roda
depois da confirmação explícita do usuário.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import ast
import contextlib
import io
import re
import traceback

CODE_FILENAME = "<assistente_ia>"

_FENCE = re.compile(r"```[ \t]*([\w+-]*)[ \t]*\n(.*?)(?:```|\Z)", re.DOTALL)
PYTHON_LANGS = {"python", "py", "pyqgis", "python3", ""}

# Módulos cuja importação é bloqueada.
BLOCKED_MODULES = {
    "subprocess", "shutil", "ctypes", "socket", "urllib", "requests", "http",
    "ftplib", "smtplib", "telnetlib", "multiprocessing", "pty", "winreg",
    "webbrowser", "paramiko", "asyncio",
}

# Chamadas bloqueadas (nome completo).
BLOCKED_CALLS = {
    "eval", "exec", "compile", "__import__",
    "os.system", "os.popen", "os.remove", "os.unlink", "os.rmdir", "os.removedirs",
    "os.rename", "os.renames", "os.replace", "os.kill", "os.killpg", "os.fork",
    "os.startfile", "os._exit", "os.chmod", "os.chown", "os.truncate",
    "sys.exit", "exit", "quit",
    "QFile.remove", "QDir.remove", "QDir.rmdir", "QDir.rmpath",
    "QgsApplication.exitQgis", "QProcess",
}
BLOCKED_PREFIXES = ("os.exec", "os.spawn", "os.posix_spawn", "subprocess.", "shutil.")

# Métodos bloqueados qualquer que seja o objeto.
BLOCKED_METHODS = {
    "unlink", "rmdir", "rmtree", "removeRecursively", "exitQgis", "actionExit",
    "deleteShapeFile",
}

# Métodos que alteram ou removem dados: permitidos, mas com aviso.
WARN_METHODS = {
    "deleteFeature": "apaga feições",
    "deleteFeatures": "apaga feições",
    "deleteSelectedFeatures": "apaga feições selecionadas",
    "deleteAttribute": "remove campos",
    "deleteAttributes": "remove campos",
    "truncate": "apaga todas as feições de uma camada",
    "removeMapLayer": "remove camadas do projeto",
    "removeMapLayers": "remove camadas do projeto",
    "removeAllMapLayers": "remove todas as camadas do projeto",
    "commitChanges": "grava alterações na fonte de dados",
    "writeAsVectorFormat": "grava arquivos no disco",
    "writeAsVectorFormatV2": "grava arquivos no disco",
    "writeAsVectorFormatV3": "grava arquivos no disco",
    "changeAttributeValue": "altera valores de atributos",
    "changeAttributeValues": "altera valores de atributos",
    "changeGeometry": "altera geometrias",
    "clear": None,  # muito genérico; tratado em _check_call
}


class AnalysisResult:
    def __init__(self):
        self.blocked = []   # motivos que impedem a execução
        self.warnings = []  # avisos mostrados na confirmação
        self.syntax_error = None

    @property
    def can_run(self):
        return not self.blocked and self.syntax_error is None


class ExecResult:
    def __init__(self, ok, output="", error=""):
        self.ok = ok
        self.output = output
        self.error = error


# ----------------------------------------------------------------------
def extract_code_blocks(text):
    """Retorna a lista de blocos de código Python da resposta."""
    blocks = []
    for m in _FENCE.finditer(text or ""):
        lang = (m.group(1) or "").lower()
        code = m.group(2).strip("\n")
        if lang in PYTHON_LANGS and code.strip():
            blocks.append(code)
    return blocks


def _dotted(node):
    """Converte a.b.c em 'a.b.c' (ou None se não for um nome simples)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _uniq_add(lst, item):
    if item not in lst:
        lst.append(item)


def analyze(code):
    """Análise estática do código. Não executa nada."""
    result = AnalysisResult()
    try:
        tree = ast.parse(code, CODE_FILENAME)
    except SyntaxError as e:
        result.syntax_error = f"Erro de sintaxe na linha {e.lineno}: {e.msg}"
        return result

    aliases = {}  # import shutil as sh -> {'sh': 'shutil'}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                aliases[alias.asname or root] = alias.name
                if root in BLOCKED_MODULES:
                    _uniq_add(result.blocked, f"importa o módulo '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                _uniq_add(result.blocked, f"importa de '{node.module}'")
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                aliases[alias.asname or alias.name] = full
                if full in BLOCKED_CALLS or full.startswith(BLOCKED_PREFIXES):
                    _uniq_add(result.blocked, f"importa '{full}'")
        elif isinstance(node, ast.Call):
            _check_call(node, aliases, result)
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") \
                and node.attr not in ("__init__", "__name__", "__class__", "__doc__"):
            _uniq_add(result.blocked, f"acessa atributo interno '{node.attr}'")
    return result


def _check_call(node, aliases, result):
    name = _dotted(node.func)
    if name:
        first, _, rest = name.partition(".")
        if first in aliases:  # resolve apelidos de import
            name = aliases[first] + ("." + rest if rest else "")
        if name in BLOCKED_CALLS or name.startswith(BLOCKED_PREFIXES):
            _uniq_add(result.blocked, f"chama '{name}()'")
            return
        if name == "getattr" and node.args:
            target = _dotted(node.args[0]) or ""
            if target.split(".")[0] in ("os", "sys", "shutil", "subprocess", "builtins"):
                _uniq_add(result.blocked, f"usa getattr em '{target}'")
        if name == "open":
            mode = ""
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = str(kw.value.value)
            if any(c in mode for c in "wax+"):
                _uniq_add(result.warnings, "grava ou sobrescreve arquivos no disco (open)")

    if isinstance(node.func, ast.Attribute):
        method = node.func.attr
        if method in BLOCKED_METHODS:
            _uniq_add(result.blocked, f"chama '.{method}()'")
        elif method == "clear" and name and "QgsProject" in name:
            _uniq_add(result.warnings, "limpa o projeto inteiro")
        elif WARN_METHODS.get(method):
            _uniq_add(result.warnings, f"{WARN_METHODS[method]} (.{method})")


# ----------------------------------------------------------------------
def _namespace(iface):
    """Ambiente semelhante ao do console Python do QGIS."""
    ns = {"__name__": "__assistente_ia__", "iface": iface}
    exec(  # noqa: S102 (código fixo, não vem do modelo)
        "from qgis.core import *\n"
        "from qgis.gui import *\n"
        "from qgis.PyQt.QtCore import *\n"
        "from qgis.PyQt.QtGui import *\n"
        "from qgis.PyQt.QtWidgets import *\n"
        "from qgis import processing\n",
        ns,
    )
    return ns


def _short_traceback(exc, code):
    """Traceback só com as linhas do código do assistente."""
    src = code.splitlines()
    tb = traceback.extract_tb(exc.__traceback__)
    lines = []
    for f in tb:
        if f.filename == CODE_FILENAME and f.lineno:
            text = src[f.lineno - 1].strip() if 0 < f.lineno <= len(src) else ""
            lines.append(f"Linha {f.lineno}: {text}")
    detail = "\n".join(lines[-3:])
    head = f"{type(exc).__name__}: {exc}"
    return f"{head}\n{detail}".strip()


def execute(code, iface):
    """Executa o código (já validado e confirmado) e captura saída e erros."""
    analysis = analyze(code)
    if not analysis.can_run:  # dupla checagem
        reason = analysis.syntax_error or "; ".join(analysis.blocked)
        return ExecResult(False, error=f"Execução bloqueada: {reason}")

    out = io.StringIO()
    try:
        compiled = compile(code, CODE_FILENAME, "exec")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            exec(compiled, _namespace(iface))  # noqa: S102 (confirmado pelo usuário)
    except SystemExit:
        return ExecResult(False, out.getvalue(), "O código tentou encerrar o programa.")
    except Exception as e:  # noqa: BLE001
        return ExecResult(False, out.getvalue(), _short_traceback(e, code))
    return ExecResult(True, out.getvalue())
