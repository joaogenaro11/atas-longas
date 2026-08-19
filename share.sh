#!/usr/bin/env bash
# Link público temporário (Cloudflare) para acessar do celular/qualquer lugar.
# Quem transcreve continua sendo o SEU Mac (qualidade máxima, grátis).
#
# Uso:  ./share.sh
#
# OBS: o túnel gratuito da Cloudflare limita uploads a ~100 MB por arquivo.
# Para áudios muito grandes (várias horas), prefira o Tailscale (ver README).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

# Senha de acesso (gera uma aleatória se você não definir APP_PASSWORD).
if [ -z "${APP_PASSWORD:-}" ]; then
  APP_PASSWORD="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 8 || echo trocar123)"
fi
export APP_PASSWORD

# Garante o cloudflared.
if ! command -v cloudflared >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Instalando cloudflared…"; brew install cloudflared
  else
    echo "Instale o cloudflared:  brew install cloudflared"; exit 1
  fi
fi

# Garante o ambiente.
[ -d .venv ] || ./install.sh

echo "==> Iniciando a aplicação…"
PORT=7860 uv run python app.py >/tmp/transcricao_app.log 2>&1 &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -s -o /dev/null "http://127.0.0.1:7860/" && break || sleep 1
done

echo ""
echo "======================================================"
echo "  SENHA DE ACESSO:  $APP_PASSWORD"
echo "  (no navegador, usuário pode ser qualquer coisa)"
echo "======================================================"
echo "  Gerando o link público abaixo (https://...trycloudflare.com)"
echo "  Abra esse link no celular. Ctrl+C aqui encerra tudo."
echo "======================================================"
echo ""

exec cloudflared tunnel --url "http://localhost:7860"
