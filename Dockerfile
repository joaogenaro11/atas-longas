# Imagem portátil (Linux/CPU) usando faster-whisper.
# OBS: Docker no macOS roda numa VM Linux e NÃO acessa a GPU/Neural Engine do
# Apple Silicon — dentro do container só há faster-whisper (CPU). Para máxima
# velocidade no Apple Silicon, rode nativamente com ./start.sh (backend MLX).
FROM python:3.11-slim

# FFmpeg é obrigatório para ler/normalizar os áudios.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv para gerenciar os pacotes.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Instala as dependências primeiro (melhor cache de camadas).
COPY pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

COPY . .

ENV PORT=7860 \
    DB_PATH=/app/data/jobs.db \
    UPLOAD_DIR=/app/data/uploads \
    TRANSCRICOES_DIR=/app/transcricoes

EXPOSE 7860
CMD ["python", "app.py"]
