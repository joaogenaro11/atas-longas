"""
Núcleo de transcrição local.

Responsável por:
  - detectar o hardware do Mac e escolher o melhor backend local;
  - normalizar o áudio com FFmpeg;
  - fatiar áudios longos em segmentos com sobreposição (sem perder frases);
  - transcrever cada segmento com cache/recuperação;
  - consolidar tudo em um único TXT fiel ao áudio.

Backends:
  - Apple Silicon  -> mlx-whisper (MLX)          [rápido e otimizado para o Neural Engine/GPU]
  - Intel / outros -> faster-whisper (CTranslate2)[CPU, multiplataforma, sem compilar]

Nenhum áudio sai da máquina. Tudo roda localmente.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime

# ---------------------------------------------------------------------------
# Detecção de hardware / escolha de backend
# ---------------------------------------------------------------------------

def _total_ram_gb() -> float:
    """RAM total em GB (best-effort, sem depender de libs externas)."""
    try:
        import psutil  # opcional
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass
    try:  # POSIX
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
    except Exception:
        return 8.0  # chute conservador


def detect_hardware() -> dict:
    system = platform.system()          # 'Darwin', 'Linux', ...
    machine = platform.machine()        # 'arm64', 'x86_64', ...
    is_mac = system == "Darwin"
    is_apple_silicon = is_mac and machine in ("arm64", "aarch64")
    ram_gb = _total_ram_gb()

    # Backend padrão: faster-whisper (estável em qualquer máquina).
    # O MLX (Apple Silicon) é OPCIONAL e só é usado se você pedir com USE_MLX=1
    # — assim o app nunca fica preso caso o mlx_whisper trave ao importar.
    force = os.environ.get("FORCE_BACKEND", "").strip().lower()
    use_mlx = os.environ.get("USE_MLX", "").strip().lower() in ("1", "true", "yes")

    if force in ("mlx", "faster-whisper"):
        backend = force
    elif use_mlx and is_apple_silicon and _mlx_available():
        backend = "mlx"
    else:
        backend = "faster-whisper"

    return {
        "system": system,
        "machine": machine,
        "is_mac": is_mac,
        "is_apple_silicon": is_apple_silicon,
        "ram_gb": round(ram_gb, 1),
        "backend": backend,
    }


def _mlx_available() -> bool:
    try:
        import mlx_whisper  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Presets de qualidade -> modelo por backend
# ---------------------------------------------------------------------------
# "large-v3-turbo" é o ponto de equilíbrio: qualidade próxima do large-v3 e
# muito mais rápido. Em máquinas com pouca RAM caímos para um modelo menor.

# No faster-whisper usamos SEMPRE o large-v3-turbo: é o melhor equilíbrio
# (qualidade próxima do large-v3, bem mais rápido), roda bem em 8 GB e evita
# baixar modelos diferentes quando o usuário troca de preset (o que causava
# travas em '1%' aguardando um download novo). No MLX mantemos os tiers.
QUALITY_PRESETS = {
    "rapido":      {"mlx": "mlx-community/whisper-medium-mlx",     "faster": "large-v3-turbo"},
    "equilibrado": {"mlx": "mlx-community/whisper-large-v3-turbo", "faster": "large-v3-turbo"},
    "maxima":      {"mlx": "mlx-community/whisper-large-v3-mlx",   "faster": "large-v3-turbo"},
}

# Em RAM baixa, o MLX cai para modelos menores; o faster-whisper mantém o turbo.
LOW_RAM_PRESETS = {
    "rapido":      {"mlx": "mlx-community/whisper-small-mlx",       "faster": "large-v3-turbo"},
    "equilibrado": {"mlx": "mlx-community/whisper-medium-mlx",      "faster": "large-v3-turbo"},
    "maxima":      {"mlx": "mlx-community/whisper-large-v3-turbo",  "faster": "large-v3-turbo"},
}


def choose_model(hw: dict, quality: str) -> str:
    quality = quality if quality in QUALITY_PRESETS else "equilibrado"
    low_ram = hw["ram_gb"] < 12
    table = LOW_RAM_PRESETS if low_ram else QUALITY_PRESETS
    key = "mlx" if hw["backend"] == "mlx" else "faster"
    return table[quality][key]


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # fallback: binário estático distribuído pelo pacote imageio-ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise RuntimeError(
            "FFmpeg não encontrado. Instale com 'brew install ffmpeg' (macOS)."
        )


def _ffprobe_bin() -> str | None:
    return shutil.which("ffprobe")


def audio_duration_seconds(path: str) -> float:
    """Duração do áudio em segundos. Usa ffprobe; se faltar, parseia o ffmpeg."""
    probe = _ffprobe_bin()
    if probe:
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            return float(out)
        except Exception:
            pass
    # Fallback: ler a duração da saída de erro do ffmpeg
    try:
        res = subprocess.run([_ffmpeg_bin(), "-i", path], capture_output=True, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
        if m:
            h, mnt, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600 + mnt * 60 + s
    except Exception:
        pass
    return 0.0


def extract_chunk_wav(src: str, dst: str, start: float, duration: float) -> None:
    """Extrai um trecho do áudio já normalizado para 16kHz mono WAV."""
    cmd = [
        _ffmpeg_bin(), "-y", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-i", src,
        "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        dst,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Backends de transcrição (interface unificada)
# ---------------------------------------------------------------------------

class CancelledError(Exception):
    """Levantada quando um job é cancelado pelo usuário."""


@dataclass
class Segment:
    start: float
    end: float
    text: str


class BaseBackend:
    def __init__(self, model_id: str):
        self.model_id = model_id

    def transcribe(self, wav_path: str, language: str | None,
                   initial_prompt: str | None,
                   should_cancel=None) -> tuple[list[Segment], str]:
        raise NotImplementedError


class MlxBackend(BaseBackend):
    def transcribe(self, wav_path, language, initial_prompt, should_cancel=None):
        import mlx_whisper
        result = mlx_whisper.transcribe(
            wav_path,
            path_or_hf_repo=self.model_id,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=True,
            word_timestamps=False,
            fp16=True,
        )
        segs = [Segment(s["start"], s["end"], s["text"]) for s in result.get("segments", [])]
        return segs, result.get("language", language or "pt")


class FasterWhisperBackend(BaseBackend):
    _model_cache: dict = {}

    def __init__(self, model_id: str, num_workers: int = 1):
        super().__init__(model_id)
        self.num_workers = max(1, num_workers)

    def _get_model(self):
        key = (self.model_id, self.num_workers)
        if key not in self._model_cache:
            print(f"[modelo] importando faster-whisper…", flush=True)
            from faster_whisper import WhisperModel
            print(f"[modelo] baixando/carregando '{self.model_id}' "
                  f"(baixa só na 1ª vez)…", flush=True)
            # int8 é leve e rápido na CPU; auto usa GPU se houver.
            # num_workers replica o modelo (pesos compartilhados) para atender
            # vários segmentos em paralelo sem multiplicar a memória.
            self._model_cache[key] = WhisperModel(
                self.model_id, device="auto", compute_type="int8",
                cpu_threads=os.cpu_count() or 4,
                num_workers=self.num_workers,
            )
            print("[modelo] pronto.", flush=True)
        return self._model_cache[key]

    def transcribe(self, wav_path, language, initial_prompt, should_cancel=None):
        model = self._get_model()
        segments, info = model.transcribe(
            wav_path,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            beam_size=5,
        )
        # 'segments' é um gerador: consome sob demanda e permite cancelar
        # no meio do trecho (a cada poucos segundos de áudio), não só no fim.
        segs = []
        for s in segments:
            if should_cancel and should_cancel():
                raise CancelledError()
            segs.append(Segment(s.start, s.end, s.text))
        return segs, info.language


def make_backend(hw: dict, model_id: str, num_workers: int = 1) -> BaseBackend:
    if hw["backend"] == "mlx":
        return MlxBackend(model_id)  # MLX: 1 GPU, paralelismo não ajuda
    return FasterWhisperBackend(model_id, num_workers=num_workers)


# ---------------------------------------------------------------------------
# Fatiamento de áudios longos
# ---------------------------------------------------------------------------
CHUNK_SECONDS = 600      # 10 min por segmento
OVERLAP_SECONDS = 15     # sobreposição para não cortar frases


def build_chunk_plan(duration: float) -> list[tuple[float, float]]:
    """Lista de (start, length) cobrindo o áudio inteiro com sobreposição."""
    if duration <= 0:
        return [(0.0, CHUNK_SECONDS)]
    if duration <= CHUNK_SECONDS:
        return [(0.0, duration)]
    plan = []
    start = 0.0
    while start < duration:
        length = min(CHUNK_SECONDS + OVERLAP_SECONDS, duration - start)
        plan.append((start, length))
        start += CHUNK_SECONDS
    return plan


def merge_segments(all_chunks: list[list[Segment]]) -> list[Segment]:
    """
    Junta os segmentos de todos os chunks removendo duplicatas na sobreposição.
    Regra: descarta segmentos cujo início já foi coberto pelo chunk anterior.
    """
    merged: list[Segment] = []
    last_end = -1.0
    for chunk in all_chunks:
        for seg in chunk:
            txt = seg.text.strip()
            if not txt:
                continue
            # ignora o que cai dentro da região já transcrita
            if seg.start < last_end - 0.5:
                continue
            merged.append(Segment(seg.start, seg.end, txt))
            last_end = max(last_end, seg.end)
    return merged


# ---------------------------------------------------------------------------
# Formatação do TXT
# ---------------------------------------------------------------------------

def fmt_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


TIMESTAMP_EVERY = 45  # segundos aproximados entre marcadores de tempo


def segments_to_text(segments: list[Segment]) -> str:
    """Converte segmentos em texto contínuo com timestamps discretos por bloco."""
    if not segments:
        return "(nenhuma fala detectada)"
    lines: list[str] = []
    block: list[str] = []
    block_start = segments[0].start
    for seg in segments:
        if block and (seg.start - block_start) >= TIMESTAMP_EVERY:
            lines.append(f"[{fmt_hms(block_start)}] " + " ".join(block).strip())
            block = []
            block_start = seg.start
        block.append(seg.text.strip())
    if block:
        lines.append(f"[{fmt_hms(block_start)}] " + " ".join(block).strip())
    return "\n\n".join(lines)


def build_txt(meta: dict, segments: list[Segment]) -> str:
    header = [
        f"Arquivo: {meta['filename']}",
        f"Duração: {fmt_hms(meta['duration'])}",
        f"Idioma detectado: {meta['language']}",
        f"Modelo: {meta['model']} ({meta['backend']})",
        f"Data da transcrição: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "=" * 60,
        "",
    ]
    return "\n".join(header) + segments_to_text(segments) + "\n"


# ---------------------------------------------------------------------------
# Orquestração de um arquivo (com cache/recuperação)
# ---------------------------------------------------------------------------

def _cache_dir(out_dir: str, filename: str) -> str:
    safe = re.sub(r"[^\w.\-]", "_", filename)
    d = os.path.join(out_dir, ".cache", safe)
    os.makedirs(d, exist_ok=True)
    return d


def _load_chunk(chunk_json: str) -> tuple[list[Segment], str | None]:
    with open(chunk_json, encoding="utf-8") as f:
        data = json.load(f)
    return [Segment(**s) for s in data["segments"]], data.get("language")


def _save_chunk(chunk_json: str, segs: list[Segment], language: str | None) -> None:
    with open(chunk_json, "w", encoding="utf-8") as f:
        json.dump({"language": language,
                   "segments": [asdict(s) for s in segs]},
                  f, ensure_ascii=False)


def transcribe_file(
    src_path: str,
    out_dir: str,
    quality: str = "equilibrado",
    hw: dict | None = None,
    progress=None,          # callable(frac: float, msg: str)
    keep_cache: bool = False,
    workers: int = 1,       # >1: transcreve segmentos em paralelo (só faster-whisper)
    should_cancel=None,     # callable() -> bool; se True, aborta com CancelledError
) -> dict:
    """
    Transcreve um arquivo inteiro e grava o TXT em out_dir.
    Retorna dict com {txt_path, language, duration, segments_count}.
    Resultados parciais de cada chunk são salvos em disco para recuperação.

    workers=1  -> sequencial, com contexto entre segmentos (melhor fidelidade).
    workers>1  -> segmentos em paralelo (mais rápido em CPU multi-core; sem
                  contexto cruzado, mas a sobreposição evita perder frases).
    """
    hw = hw or detect_hardware()
    model_id = choose_model(hw, quality)

    filename = os.path.basename(src_path)
    stem = os.path.splitext(filename)[0]
    os.makedirs(out_dir, exist_ok=True)
    txt_path = os.path.join(out_dir, stem + ".txt")

    duration = audio_duration_seconds(src_path)
    plan = build_chunk_plan(duration)
    cache = _cache_dir(out_dir, filename)

    # Paralelismo só faz sentido no faster-whisper (MLX = 1 GPU) e com >1 chunk.
    eff_workers = workers if hw["backend"] == "faster-whisper" else 1
    eff_workers = max(1, min(eff_workers, len(plan)))
    backend = make_backend(hw, model_id, num_workers=eff_workers)

    def emit(frac, msg):
        if progress:
            progress(frac, msg)

    def check_cancel():
        if should_cancel and should_cancel():
            raise CancelledError()

    meta = {"filename": filename, "duration": duration, "language": "pt",
            "model": model_id, "backend": hw["backend"]}

    def transcribe_one(i, start, length, language, prompt):
        """Transcreve um chunk (usando cache se existir) e devolve (segs, lang)."""
        chunk_json = os.path.join(cache, f"chunk_{i:04d}.json")
        if os.path.exists(chunk_json):
            segs, lang = _load_chunk(chunk_json)
            return segs, lang or language
        wav = os.path.join(cache, f"chunk_{i:04d}.wav")
        print(f"[seg {i+1}] extraindo áudio…", flush=True)
        extract_chunk_wav(src_path, wav, start, length)
        print(f"[seg {i+1}] transcrevendo…", flush=True)
        segs, detected = backend.transcribe(wav, language=language,
                                            initial_prompt=prompt,
                                            should_cancel=should_cancel)
        print(f"[seg {i+1}] ok ({len(segs)} trechos)", flush=True)
        for s in segs:              # tempo absoluto
            s.start += start
            s.end += start
        _save_chunk(chunk_json, segs, language or detected)
        try:
            os.remove(wav)
        except OSError:
            pass
        return segs, (language or detected)

    emit(0.02, f"Preparando ({len(plan)} segmento(s), {eff_workers} em paralelo)…")

    all_chunks: list[list[Segment]] = [[] for _ in plan]

    if eff_workers == 1:
        # ---- Sequencial: mantém contexto entre segmentos (máxima fidelidade)
        language: str | None = None
        tail_context = ""
        for i, (start, length) in enumerate(plan):
            check_cancel()
            emit(i / len(plan) + 0.01, f"Transcrevendo segmento {i+1}/{len(plan)}…")
            segs, language = transcribe_one(i, start, length, language,
                                            tail_context or None)
            all_chunks[i] = segs
            if segs:
                tail_context = " ".join(s.text for s in segs[-3:])[-200:]
            meta["language"] = language or "pt"
            with open(txt_path, "w", encoding="utf-8") as f:  # salvamento parcial
                f.write(build_txt(meta, merge_segments(all_chunks)))
            emit((i + 1) / len(plan), f"Segmento {i+1}/{len(plan)} concluído")
        language = language or "pt"
    else:
        # ---- Paralelo: detecta idioma no 1º chunk, depois processa o resto
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        segs0, language = transcribe_one(0, plan[0][0], plan[0][1], None, None)
        all_chunks[0] = segs0
        language = language or "pt"
        meta["language"] = language
        done = {0}
        lock = threading.Lock()

        def work(i):
            check_cancel()
            start, length = plan[i]
            segs, _ = transcribe_one(i, start, length, language, None)
            return i, segs

        with ThreadPoolExecutor(max_workers=eff_workers) as ex:
            futures = [ex.submit(work, i) for i in range(1, len(plan))]
            for fut in as_completed(futures):
                i, segs = fut.result()
                with lock:
                    all_chunks[i] = segs
                    done.add(i)
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(build_txt(meta, merge_segments(all_chunks)))
                    emit(len(done) / len(plan),
                         f"{len(done)}/{len(plan)} segmentos concluídos")

    segments = merge_segments(all_chunks)
    meta = {"filename": filename, "duration": duration,
            "language": language or "pt", "model": model_id,
            "backend": hw["backend"]}
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(build_txt(meta, segments))

    if not keep_cache:
        shutil.rmtree(cache, ignore_errors=True)

    emit(1.0, "Concluído")
    return {
        "txt_path": txt_path,
        "language": language or "pt",
        "duration": duration,
        "segments_count": len(segments),
        "model": model_id,
        "backend": hw["backend"],
    }


if __name__ == "__main__":
    # Uso: python transcribe.py <audio> [saida] [qualidade]
    hw = detect_hardware()
    print("Hardware:", hw, file=sys.stderr)
    if len(sys.argv) < 2:
        print("uso: python transcribe.py <audio> [pasta_saida] [rapido|equilibrado|maxima]")
        sys.exit(1)
    audio = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "transcricoes"
    q = sys.argv[3] if len(sys.argv) > 3 else "equilibrado"
    res = transcribe_file(audio, out, q, hw,
                          progress=lambda p, m: print(f"[{int(p*100):3d}%] {m}", file=sys.stderr))
    print("OK ->", res["txt_path"])
