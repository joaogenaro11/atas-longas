"""
Execução de UM job em processo separado.

Rodar a transcrição num subprocesso permite CANCELAR de forma garantida:
o processo pai simplesmente encerra (mata) este processo — parar é parar,
não importa se está carregando o modelo, no VAD ou na inferência.

Este arquivo é chamado como programa próprio (python worker_proc.py ...),
então NÃO importa o servidor Flask — inicia leve e rápido.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback


def run_child(job_id: int, stored_path: str, out_dir: str,
              quality: str, workers: int, hw: dict) -> None:
    import db
    from transcribe import transcribe_file

    def cb(frac, msg):
        db.update_job(job_id, progress=float(frac), message=str(msg)[:300])

    # --- seam de teste (valida cancelamento sem precisar de modelo) ----------
    if isinstance(stored_path, str) and stored_path.startswith("__TEST_SLEEP__:"):
        total = float(stored_path.split(":", 1)[1])
        steps = max(1, int(total * 5))
        for i in range(steps):
            cb(min(0.99, i / steps), f"teste {i}")
            time.sleep(0.2)
        db.update_job(job_id, status="concluído", progress=1.0, message="teste ok")
        return

    # Sinaliza cedo que o processo está vivo (o modelo carrega na 1ª vez).
    print(f"[worker] job {job_id} iniciou (pid {os.getpid()})", flush=True)
    db.update_job(job_id, progress=0.02,
                  message="carregando modelo (só na 1ª vez)…")

    try:
        res = transcribe_file(stored_path, out_dir, quality=quality,
                              hw=hw, progress=cb, workers=workers)
        db.update_job(
            job_id, status="concluído", progress=1.0,
            message=f"{res['segments_count']} blocos",
            txt_path=res["txt_path"], language=res["language"],
            duration=res["duration"], model=res["model"],
        )
        print(f"[worker] job {job_id} concluído", flush=True)
    except Exception as e:
        traceback.print_exc()
        db.update_job(job_id, status="erro", message=str(e)[:300])


if __name__ == "__main__":
    # Args: job_id stored_path out_dir quality workers hw_json
    _job_id = int(sys.argv[1])
    _stored = sys.argv[2]
    _out = sys.argv[3]
    _quality = sys.argv[4]
    _workers = int(sys.argv[5])
    _hw = json.loads(sys.argv[6])
    run_child(_job_id, _stored, _out, _quality, _workers, _hw)
