#!/usr/bin/env bash
# Instalação automática (uv). Detecta o Mac e instala o backend certo.
# Uso:  ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Detectando sistema…"
OS="$(uname -s)"; ARCH="$(uname -m)"
echo "    $OS / $ARCH"

# --- FFmpeg -----------------------------------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "==> FFmpeg não encontrado."
  if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    echo "    Instalando via Homebrew…"; brew install ffmpeg
  else
    echo "    ⚠️  Instale o FFmpeg:  brew install ffmpeg   (https://brew.sh)"
  fi
else
  echo "==> FFmpeg OK: $(command -v ffmpeg)"
fi

# --- uv ---------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "==> Instalando uv (gerenciador de pacotes)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "==> uv OK: $(uv --version)"

# --- Dependências -----------------------------------------------------------
echo "==> Instalando dependências (.venv via uv)…"
if [ "$OS" = "Darwin" ] && { [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; }; then
  echo "    Apple Silicon detectado — incluindo mlx-whisper (otimizado)."
  uv sync --extra mlx || uv sync
else
  echo "    Backend faster-whisper (CPU)."
  uv sync
fi

# --- Remove o PyTorch (não é usado e deixa o carregamento MUITO lento) -------
# O ctranslate2 (faster-whisper) importa o torch se ele existir, o que trava o
# início em máquinas modestas. Nenhum backend aqui precisa dele.
echo "==> Removendo PyTorch (desnecessário e lento)…"
uv pip uninstall torch torchaudio torchvision >/dev/null 2>&1 || true

echo ""
echo "✅ Instalação concluída."
echo "   Para iniciar:  ./start.sh        (nativo, recomendado no Mac)"
echo "   Ou via Docker: docker compose up  (portátil, CPU)"
