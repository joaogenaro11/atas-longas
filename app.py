"""
Servidor web local (Flask) para transcrição de áudio.

Fluxo: UPLOAD -> FILA (SQLite) -> worker transcreve em segmentos -> TXT.
Roda 100% local. Nenhum áudio sai da máquina. Abra em http://localhost:7860

Um único worker processa a fila sequencialmente (mais estável em memória).
Cada job pode, opcionalmente, transcrever seus segmentos em paralelo.
"""

from __future__ import annotations

import os
import threading
import time
import traceback

import re
import unicodedata

from flask import Flask, jsonify, request, send_file, abort

import db
from transcribe import detect_hardware, choose_model, transcribe_file, fmt_hms

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))
OUT_DIR = os.environ.get("TRANSCRICOES_DIR", os.path.join(BASE_DIR, "transcricoes"))
STATIC_DIR = os.path.join(BASE_DIR, "static")
PORT = int(os.environ.get("PORT", "7860"))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

HW = detect_hardware()

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = None  # áudios de várias horas são grandes

ALLOWED = {".mp3", ".m4a", ".wav", ".mp4", ".aac", ".flac",
           ".ogg", ".opus", ".webm", ".mov"}


def safe_name(name: str) -> str:
    """
    Nome de arquivo seguro que PRESERVA acentos e espaços (bom no macOS),
    removendo apenas componentes de caminho e caracteres perigosos.
    """
    name = os.path.basename(name or "")
    name = unicodedata.normalize("NFC", name)
    name = name.replace("\\", "_").replace("/", "_")
    name = re.sub(r"[\x00-\x1f]", "", name)      # remove caracteres de controle
    name = name.strip().lstrip(".")               # sem ponto inicial (arquivo oculto)
    return name or "audio"


# ---------------------------------------------------------------------------
# Worker: processa a fila em background, um job por vez.
# ---------------------------------------------------------------------------
_worker_started = False
_worker_lock = threading.Lock()


def _process_job(job: dict) -> None:
    job_id = job["id"]
    db.update_job(job_id, status="processando", message="iniciando…")

    def cb(frac, msg):
        db.update_job(job_id, progress=float(frac), message=str(msg)[:300])

    try:
        res = transcribe_file(
            job["stored_path"], OUT_DIR,
            quality=job["quality"], hw=HW, progress=cb,
            workers=int(job["workers"] or 1),
        )
        db.update_job(
            job_id, status="concluído", progress=1.0,
            message=f"{res['segments_count']} blocos",
            txt_path=res["txt_path"], language=res["language"],
            duration=res["duration"], model=res["model"],
        )
    except Exception as e:
        traceback.print_exc()
        db.update_job(job_id, status="erro", message=str(e)[:300])


def _worker_loop() -> None:
    while True:
        try:
            job = db.next_pending()
            if job:
                _process_job(job)
            else:
                time.sleep(1.5)
        except Exception:
            traceback.print_exc()
            time.sleep(2)


def start_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        t = threading.Thread(target=_worker_loop, daemon=True, name="transcriber")
        t.start()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return send_file(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/hardware")
def api_hardware():
    return jsonify({
        **HW,
        "models": {q: choose_model(HW, q) for q in ("rapido", "equilibrado", "maxima")},
        "out_dir": OUT_DIR,
    })


@app.post("/api/upload")
def api_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "nenhum arquivo enviado"}), 400
    quality = request.form.get("quality", "equilibrado")
    try:
        workers = max(1, min(8, int(request.form.get("workers", "1"))))
    except ValueError:
        workers = 1

    created = []
    for f in files:
        if not f or not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED:
            continue
        safe = safe_name(f.filename)
        # evita sobrescrever se subir arquivos com mesmo nome
        dest = os.path.join(UPLOAD_DIR, safe)
        n = 1
        while os.path.exists(dest):
            stem, e = os.path.splitext(safe)
            dest = os.path.join(UPLOAD_DIR, f"{stem}_{n}{e}")
            n += 1
        f.save(dest)
        job_id = db.add_job(os.path.basename(dest), dest, quality, workers)
        created.append(job_id)

    if not created:
        return jsonify({"error": "nenhum formato de áudio válido"}), 400
    return jsonify({"created": created})


@app.get("/api/jobs")
def api_jobs():
    jobs = db.list_jobs()
    for j in jobs:
        j["duration_hms"] = fmt_hms(j.get("duration") or 0)
    return jsonify(jobs)


@app.get("/api/jobs/<int:job_id>/download")
def api_download(job_id):
    job = db.get_job(job_id)
    if not job or not job.get("txt_path") or not os.path.exists(job["txt_path"]):
        abort(404)
    return send_file(job["txt_path"], as_attachment=True,
                     download_name=os.path.basename(job["txt_path"]),
                     mimetype="text/plain")


@app.post("/api/jobs/<int:job_id>/retry")
def api_retry(job_id):
    job = db.get_job(job_id)
    if not job:
        abort(404)
    # graças ao cache de segmentos, o retry só refaz o que faltou.
    db.update_job(job_id, status="aguardando", message="reenfileirado", progress=0)
    return jsonify({"ok": True})


db.init_db()
start_worker()


if __name__ == "__main__":
    print("Backend:", HW)
    print(f"Servindo em http://localhost:{PORT}")
    # use_reloader=False: evita iniciar dois workers e reprocessar a fila.
    app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)
