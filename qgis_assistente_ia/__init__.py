# -*- coding: utf-8 -*-
"""
Assistente IA para QGIS - Ibexdev

Copyright (C) 2026 Ibexdev

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
"""


def classFactory(iface):  # noqa: N802 (nome exigido pelo QGIS)
    """Ponto de entrada chamado pelo QGIS ao carregar o plugin."""
    from .plugin import AssistenteIAPlugin

    return AssistenteIAPlugin(iface)
