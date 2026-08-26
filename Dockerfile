# Imagem para rodar na NUVEM (Hugging Face Spaces, Docker SDK, porta 7860).
# Backend: faster-whisper (CPU). Grátis, sempre no ar, acessível de qualquer
# lugar sem o seu computador. Mais lento que o Mac; áudio passa pelo servidor
# da Hugging Face (deixa de ser 100% local — proteja com senha, veja README).
FROM python:3.11-slim

# FFmpeg é obrigatório para ler/normalizar os áudios.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências (pip simples — robusto no build do Spaces).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No Spaces o disco persistente não existe no plano grátis: tudo em /tmp
# (gravável). Uploads/transcrições/DB são efêmeros — o fluxo é: enviar,
# transcrever, baixar o TXT na hora.
ENV PORT=7860 \
    DB_PATH=/tmp/data/jobs.db \
    UPLOAD_DIR=/tmp/data/uploads \
    TRANSCRICOES_DIR=/tmp/transcricoes \
    HF_HOME=/tmp/hf \
    PYTHONUNBUFFERED=1

EXPOSE 7860
CMD ["python", "app.py"]
