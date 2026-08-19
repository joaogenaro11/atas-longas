"""
Execução de UM job em processo separado.

Rodar a transcrição num subprocesso permite CANCELAR de forma garantida:
o processo pai simplesmente encerra (mata) este processo — pare é parar,
não importa se está baixando o modelo, no VAD ou na inferência.
"""

from __future__ import annotations

import os
import time
import traceback


def run_child(job_id: int, stored_path: str, out_dir: str,
              quality: str, workers: int, hw: dict) -> None:
    import db
    from transcribe import transcribe_file

    def cb(frac, msg):
        db.update_job(job_id, progress=float(frac), message=str(msg)[:300])

    # --- seam de teste: caminho sentinela apenas para validar o cancelamento
    if isinstance(stored_path, str) and stored_path.startswith("__TEST_SLEEP__:"):
        total = float(stored_path.split(":", 1)[1])
        steps = max(1, int(total * 5))
        for i in range(steps):
            cb(min(0.99, i / steps), f"teste {i}")
            time.sleep(0.2)
        db.update_job(job_id, status="concluído", progress=1.0, message="teste ok")
        return

    try:
        res = transcribe_file(stored_path, out_dir, quality=quality,
                              hw=hw, progress=cb, workers=workers)
        db.update_job(
            job_id, status="concluído", progress=1.0,
            message=f"{res['segments_count']} blocos",
            txt_path=res["txt_path"], language=res["language"],
            duration=res["duration"], model=res["model"],
        )
    except Exception as e:
        traceback.print_exc()
        db.update_job(job_id, status="erro", message=str(e)[:300])
