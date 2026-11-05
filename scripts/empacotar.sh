#!/usr/bin/env bash
# Gera dist/qgis_assistente_ia-<versão>.zip para enviar ao plugins.qgis.org.
# O zip contém apenas a pasta do plugin, sem __pycache__ e arquivos de sistema.
set -euo pipefail

cd "$(dirname "$0")/.."
PLUGIN=qgis_assistente_ia
VERSION=$(grep -E '^version=' "$PLUGIN/metadata.txt" | cut -d= -f2 | tr -d '[:space:]')

mkdir -p dist
OUT="dist/${PLUGIN}-${VERSION}.zip"
rm -f "$OUT"

zip -r -q "$OUT" "$PLUGIN" \
  -x "*/__pycache__/*" "*.pyc" "*/.DS_Store" "*/.git*" "*/tests/*"

echo "Gerado: $OUT"
unzip -l "$OUT"
