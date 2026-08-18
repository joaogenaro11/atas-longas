#!/usr/bin/env bash
# Inicia a aplicação em http://localhost:7860  (nativo, via uv)
set -euo pipefail
cd "$(dirname "$0")"

export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv não encontrado. Rodando a instalação primeiro…"
  ./install.sh
fi

if [ ! -d ".venv" ]; then
  echo "Ambiente não encontrado. Instalando…"
  ./install.sh
fi

echo "Abrindo em http://localhost:7860  (Ctrl+C para parar)"
( sleep 2; command -v open >/dev/null 2>&1 && open http://localhost:7860 ) &

exec uv run python app.py
