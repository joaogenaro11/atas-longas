"""
Execução de UM job em processo separado.

Rodar a transcrição num subprocesso permite CANCELAR de forma garantida:
o processo pai encerra (mata) este processo — parar é parar, não importa em
que ponto esteja. O carregamento do modelo é feito do cache local (sem rede),
então não trava.

Chamado como programa próprio (python worker_proc.py ...): inicia leve.
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

    print(f"[worker] job {job_id} iniciou (pid {os.getpid()})", flush=True)
    db.update_job(job_id, progress=0.02, message="carregando modelo…")

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
    run_child(int(sys.argv[1]), sys.argv[2], sys.argv[3],
              sys.argv[4], int(sys.argv[5]), json.loads(sys.argv[6]))
