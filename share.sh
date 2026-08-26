#!/usr/bin/env bash
# Acesso de qualquer lugar (celular / outro PC) por um link público temporário.
# Quem transcreve continua sendo o SEU Mac (qualidade máxima, grátis).
#
# Uso:  ./share.sh
#
# Mostra: LINK grande + QR code (escaneie com a câmera) + SENHA.
# OBS: o túnel gratuito da Cloudflare limita uploads a ~100 MB por arquivo.
# Para áudios de várias horas (arquivos grandes), use o Tailscale (ver README).
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

APP_LOG="/tmp/atas_app.log"
TUN_LOG="/tmp/atas_tunnel.log"

# Senha de acesso (gera uma aleatória se você não definir APP_PASSWORD).
if [ -z "${APP_PASSWORD:-}" ]; then
  APP_PASSWORD="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 6 || echo trocar)"
fi
export APP_PASSWORD

# Garante o cloudflared.
if ! command -v cloudflared >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> Instalando cloudflared (uma vez)…"; brew install cloudflared
  else
    echo "Instale o cloudflared:  brew install cloudflared"; exit 1
  fi
fi

# Garante o ambiente e o gerador de QR (opcional).
[ -d .venv ] || ./install.sh
uv pip install qrcode >/dev/null 2>&1 || true

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"

echo "==> Iniciando a aplicação…"
PORT=7860 "$PY" app.py >"$APP_LOG" 2>&1 &
APP_PID=$!

echo "==> Abrindo o túnel público…"
cloudflared tunnel --url "http://localhost:7860" >"$TUN_LOG" 2>&1 &
TUN_PID=$!

# encerra tudo ao sair (Ctrl+C)
trap 'kill $APP_PID $TUN_PID 2>/dev/null || true' EXIT

# espera a app subir
for _ in $(seq 1 40); do
  curl -s -o /dev/null "http://127.0.0.1:7860/" && break || sleep 1
done

# espera o cloudflared publicar a URL
URL=""
for _ in $(seq 1 40); do
  URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUN_LOG" | head -n1 || true)"
  [ -n "$URL" ] && break || sleep 1
done

clear 2>/dev/null || true
echo ""
echo "=================================================================="
if [ -n "$URL" ]; then
  echo "  ✅ ABRA ISTO NO CELULAR / OUTRO COMPUTADOR:"
  echo ""
  echo "      $URL"
  echo ""
  echo "  🔑 SENHA:  $APP_PASSWORD   (usuário: qualquer coisa)"
  echo "=================================================================="
  echo "  📷 Ou escaneie o QR abaixo com a câmera do celular:"
  echo ""
  "$PY" qr.py "$URL" || true
else
  echo "  ⚠️  Não consegui capturar o link. Veja o log: $TUN_LOG"
  echo "=================================================================="
fi
echo ""
echo "  Deixe esta janela ABERTA enquanto usar. Ctrl+C encerra tudo."
echo "=================================================================="

# mantém rodando até Ctrl+C
wait $TUN_PID
