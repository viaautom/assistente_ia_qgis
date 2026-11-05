# -*- coding: utf-8 -*-
"""
Extrai o contexto do projeto QGIS para enviar ao modelo.

Coleta apenas metadados (camadas, tipo de geometria, SRC, campos e contagem
de feições). NUNCA coleta valores de atributos nem geometrias das feições.
Também não envia a fonte completa das camadas, pois URIs de banco de dados
podem conter usuário e senha.

Copyright (C) 2026 Ibexdev
Licença: GNU GPL v2 ou superior.
"""

import os

from qgis.core import (
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)

MAX_FIELDS_PER_LAYER = 60
MAX_LAYERS = 80


def _crs_info(crs):
    if crs is None or not crs.isValid():
        return None
    return {"authid": crs.authid() or "personalizado", "descricao": crs.description()}


def _safe_source(layer):
    """Retorna só o nome do arquivo (para camadas em arquivo) ou None."""
    try:
        parts = QgsProviderRegistry.instance().decodeUri(
            layer.providerType(), layer.source()
        )
        path = parts.get("path")
        if path:
            name = os.path.basename(path)
            layer_name = parts.get("layerName")
            return f"{name}|{layer_name}" if layer_name else name
    except Exception:  # noqa: BLE001
        pass
    return None


def _vector_info(layer):
    fields = layer.fields()
    field_list = [
        {"nome": f.name(), "tipo": f.typeName() or f.friendlyTypeString()}
        for f in list(fields)[:MAX_FIELDS_PER_LAYER]
    ]
    return {
        "tipo": "vetorial",
        "geometria": QgsWkbTypes.displayString(layer.wkbType()),
        "feicoes": layer.featureCount(),
        "selecionadas": layer.selectedFeatureCount(),
        "campos": field_list,
        "campos_omitidos": max(0, fields.count() - MAX_FIELDS_PER_LAYER),
        "filtro": layer.subsetString() or None,
        "editavel": layer.isEditable(),
    }


def _raster_info(layer):
    return {
        "tipo": "raster",
        "bandas": layer.bandCount(),
        "largura": layer.width(),
        "altura": layer.height(),
        "pixel_x": layer.rasterUnitsPerPixelX(),
        "pixel_y": layer.rasterUnitsPerPixelY(),
    }


def collect_context(iface=None, project=None):
    """Retorna um dicionário com o contexto do projeto atual."""
    project = project or QgsProject.instance()
    root = project.layerTreeRoot()
    active = iface.activeLayer() if iface else None

    layers = []
    all_layers = list(project.mapLayers().values())
    # Respeita a ordem do painel Camadas quando possível.
    order = {lyr.id(): i for i, lyr in enumerate(root.layerOrder())}
    all_layers.sort(key=lambda lyr: order.get(lyr.id(), len(order)))

    for layer in all_layers[:MAX_LAYERS]:
        node = root.findLayer(layer.id())
        info = {
            "nome": layer.name(),
            "id": layer.id(),
            "provedor": layer.providerType(),
            "arquivo": _safe_source(layer),
            "src": _crs_info(layer.crs()),
            "visivel": bool(node and node.isVisible()),
            "ativa": bool(active and active.id() == layer.id()),
            "valida": layer.isValid(),
        }
        if isinstance(layer, QgsVectorLayer):
            info.update(_vector_info(layer))
        elif isinstance(layer, QgsRasterLayer):
            info.update(_raster_info(layer))
        else:
            info["tipo"] = "outro"
        layers.append(info)

    extent = None
    if iface is not None:
        rect = iface.mapCanvas().extent()
        extent = [
            round(rect.xMinimum(), 6),
            round(rect.yMinimum(), 6),
            round(rect.xMaximum(), 6),
            round(rect.yMaximum(), 6),
        ]

    return {
        "projeto": project.baseName() or "(sem título)",
        "src_projeto": _crs_info(project.crs()),
        "extensao_mapa": extent,
        "total_camadas": len(all_layers),
        "camadas_omitidas": max(0, len(all_layers) - MAX_LAYERS),
        "camadas": layers,
    }


def _fmt_crs(crs):
    return f"{crs['authid']} ({crs['descricao']})" if crs else "indefinido"


def context_to_text(ctx):
    """Converte o contexto em texto compacto, em português, para o prompt."""
    lines = [
        f"Projeto: {ctx['projeto']}",
        f"SRC do projeto: {_fmt_crs(ctx['src_projeto'])}",
    ]
    if ctx["extensao_mapa"]:
        lines.append(
            "Extensão visível do mapa (xmin, ymin, xmax, ymax, no SRC do projeto): "
            + ", ".join(str(v) for v in ctx["extensao_mapa"])
        )
    lines.append(f"Camadas abertas: {ctx['total_camadas']}")
    if not ctx["camadas"]:
        lines.append("(nenhuma camada carregada)")

    for i, lyr in enumerate(ctx["camadas"], 1):
        flags = []
        if lyr["ativa"]:
            flags.append("ATIVA")
        flags.append("visível" if lyr["visivel"] else "oculta")
        if not lyr["valida"]:
            flags.append("INVÁLIDA")
        header = f"{i}. \"{lyr['nome']}\" [{lyr['tipo']}, {', '.join(flags)}]"
        lines.append(header)
        lines.append(f"   id: {lyr['id']} | provedor: {lyr['provedor']}"
                     + (f" | arquivo: {lyr['arquivo']}" if lyr["arquivo"] else ""))
        lines.append(f"   SRC: {_fmt_crs(lyr['src'])}")

        if lyr["tipo"] == "vetorial":
            sel = f", {lyr['selecionadas']} selecionadas" if lyr["selecionadas"] else ""
            lines.append(f"   geometria: {lyr['geometria']} | feições: {lyr['feicoes']}{sel}")
            if lyr["filtro"]:
                lines.append(f"   filtro ativo: {lyr['filtro']}")
            if lyr["editavel"]:
                lines.append("   em modo de edição")
            campos = ", ".join(f"{c['nome']} ({c['tipo']})" for c in lyr["campos"])
            lines.append(f"   campos: {campos or '(nenhum)'}")
            if lyr["campos_omitidos"]:
                lines.append(f"   (+{lyr['campos_omitidos']} campos omitidos)")
        elif lyr["tipo"] == "raster":
            lines.append(
                f"   bandas: {lyr['bandas']} | {lyr['largura']}x{lyr['altura']} px"
                f" | pixel: {lyr['pixel_x']:g} x {lyr['pixel_y']:g}"
            )

    if ctx["camadas_omitidas"]:
        lines.append(f"(+{ctx['camadas_omitidas']} camadas omitidas)")
    return "\n".join(lines)
