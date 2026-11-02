#!/usr/bin/env python3
"""CAP-V1: prueba de doblaje neural sobre el MP4 DEMO ya verificado.

NO visita Suite Ultra ni usa credenciales. No es un proveedor autorizado para
producción: edge-tts es una interfaz no contractual, usada solo para evaluación.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess

SOURCE_RUN_ID = 41506639194
SOURCE_TICKET_ID = 3328
SOURCE_BRANCH_ID = 1001
VOICE = "es-MX-JorgeNeural"
EXPECTED_SCENES = ("inicio", "ticket", "historial", "avance", "fin")
# Textos breves: cada frase debe caber en su intervalo real sin acelerar
# excesivamente la voz. La marca se escribe correctamente en subtítulos.
SCRIPT = {
    "inicio": "Bienvenido a Suite Ultra. Esta es una demostración.",
    "ticket": "Este ticket de tapizado incluye tres aparatos.",
    "historial": "Revisamos el historial sin modificar datos.",
    "avance": "Consultamos el avance de cada aparato.",
    "fin": "El cierre necesita autorización. Aquí termina la demostración.",
}
ALIAS_PRONUNCIACION = {"Suite Ultra": "Súit Ultra"}
SOURCE_DIR = Path("artifacts/capacitacion/source-readonly")
OUTPUT_DIR = Path("artifacts/capacitacion/voice-sync-preview")
MAX_TEMPO = 1.30
NARRATION_MARGIN_SECONDS = 0.22


def run(args: list[str]) -> str:
    # Sólo comandos de FFmpeg/FFprobe y frases sintéticas. No hay credenciales
    # ni URLs privadas en los argumentos que se usan en este experimento.
    process = subprocess.run(args, capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(
            f"{args[0]} falló (código {process.returncode}): "
            + process.stderr[-3500:]
        )
    return process.stdout.strip()


def probe_duration(media: Path, selector: str = "format=duration") -> float:
    duration = float(run([
        "ffprobe", "-v", "error", "-show_entries", selector,
        "-of", "default=noprint_wrappers=1:nokey=1", str(media),
    ]).splitlines()[0])
    if duration <= 0:
        raise ValueError(f"Duración de medio inválida: {media.name}")
    return duration


def srt_timestamp(seconds: float) -> str:
    n = round(seconds * 1000)
    hours, n = divmod(n, 3600000)
    mins, n = divmod(n, 60000)
    secs, n = divmod(n, 1000)
    return f"{hours:02}:{mins:02}:{secs:02},{n:03}"


def parse_original_srt(content: str) -> list[float]:
    """Tomar las marcas de la grabación, no tiempos supuestos."""
    times = re.findall(
        r"(?m)^\d+\s*\n(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->", content,
    )
    if len(times) != len(EXPECTED_SCENES):
        raise ValueError("La fuente no contiene las cinco escenas esperadas.")
    starts = [
        int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
        for h, m, s, ms in times
    ]
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("Timeline no es creciente.")
    return starts


def validate_source() -> tuple[Path, list[float], float]:
    source = SOURCE_DIR / "capacitacion.mp4"
    manifest = json.loads((SOURCE_DIR / "manifiesto.json").read_text(encoding="utf-8"))
    if not (
        manifest.get("schema") == "suite-ultra-training-prod-readonly-v1"
        and manifest.get("mode") == "READ_ONLY"
        and manifest.get("business_writes") == "BLOCKED_BY_PLAYWRIGHT"
        and manifest.get("demo_ticket_id") == SOURCE_TICKET_ID
        and manifest.get("demo_branch_id") == SOURCE_BRANCH_ID
        and manifest.get("aparatos") == 3
        and tuple(manifest.get("scenes", [])) == EXPECTED_SCENES
    ):
        raise ValueError("La fuente no corresponde a CAP-V1 DEMO readonly verificado.")
    starts = parse_original_srt(
        (SOURCE_DIR / "subtitulos.srt").read_text(encoding="utf-8"),
    )
    video_duration = probe_duration(source, "stream=duration")
    if not 24.0 <= video_duration <= 40.0 or starts[-1] >= video_duration:
        raise ValueError("Duración/timeline de origen inesperada.")
    return source, starts, video_duration


def synthesize(out: Path, scene: str) -> float:
    spoken = SCRIPT[scene]
    for source, alias in ALIAS_PRONUNCIACION.items():
        spoken = spoken.replace(source, alias)
    target = out / f"voz-{scene}.mp3"
    run([
        "edge-tts", "--voice", VOICE, "--rate=-5%",
        "--text", spoken, "--write-media", str(target),
    ])
    duration = probe_duration(target)
    if not 1.0 < duration < 15.0:
        raise ValueError(f"Narración no válida: {scene}")
    return duration


def create_synced_preview() -> None:
    if not all(shutil.which(exe) for exe in ("edge-tts", "ffmpeg", "ffprobe")):
        raise EnvironmentError("edge-tts, ffmpeg y ffprobe son obligatorios.")
    source, starts, end = validate_source()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scenes: list[dict] = []
    filter_terms: list[str] = []
    input_audio: list[str] = []
    subtitles = []

    for i, key in enumerate(EXPECTED_SCENES):
        start = starts[i]
        next_start = starts[i + 1] if i + 1 < len(starts) else end
        window = next_start - start
        natural_duration = synthesize(OUTPUT_DIR, key)
        allowed = window - NARRATION_MARGIN_SECONDS
        if allowed <= 0:
            raise ValueError(f"Escena sin ventana útil: {key}")
        tempo = max(1.0, natural_duration / allowed)
        if tempo > MAX_TEMPO:
            raise ValueError(
                f"La frase {key} dura {natural_duration:.2f}s y necesita "
                f"aceleración {tempo:.2f}x; hay que acortar texto, no forzar voz."
            )
        spoken_duration = natural_duration / tempo
        input_audio.extend(["-i", str(OUTPUT_DIR / f"voz-{key}.mp3")])
        # retrasos en milisegundos; atempo solo acelera si es imprescindible
        filter_terms.append(
            f"[{i+1}:a]atempo={tempo:.5f},"
            f"adelay={round(start*1000)}:all=1,"
            f"apad=whole_dur={end:.3f}[n{i}]"
        )
        # El texto oficial no lleva ninguna sustitución fonética.
        subtitle_end = min(next_start - 0.08, start + spoken_duration + 0.18)
        subtitles.append(
            f"{i + 1}\n{srt_timestamp(start)} --> "
            f"{srt_timestamp(subtitle_end)}\n{SCRIPT[key]}\n"
        )
        scenes.append({
            "key": key,
            "start_seconds": start,
            "window_seconds": round(window, 3),
            "voice_seconds_original": round(natural_duration, 3),
            "voice_seconds_final": round(spoken_duration, 3),
            "tempo": round(tempo, 3),
        })

    out_srt = OUTPUT_DIR / "subtitulos.srt"
    out_srt.write_text("\n".join(subtitles) + "\n", encoding="utf-8")
    mix = "".join(f"[n{i}]" for i in range(len(scenes)))
    filter_terms.append(
        f"{mix}amix=inputs={len(scenes)}:duration=longest:normalize=0,"
        f"atrim=duration={end:.3f},"
        f"aresample=48000,volume=0.80,alimiter=limit=0.95[narracion]"
    )
    mp4 = OUTPUT_DIR / "capacitacion-jorge-neural.mp4"
    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), *input_audio, "-i", str(out_srt),
        "-filter_complex", ";".join(filter_terms),
        "-map", "0:v:0", "-map", "[narracion]", "-map", f"{len(scenes)+1}:s:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=spa",
        "-movflags", "+faststart", "-t", f"{end:.3f}",
        str(mp4),
    ]
    run(args)
    result_video_duration = probe_duration(mp4, "stream=duration")
    if abs(result_video_duration - end) > 0.15:
        raise ValueError("Regresión: el doblaje cambió la longitud del video.")

    # Verificar audio y subtítulos realmente incorporados, no solo archivo no vacío.
    probe = json.loads(run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(mp4),
    ]))
    kinds = {s.get("codec_type") for s in probe.get("streams", [])}
    if kinds != {"video", "audio", "subtitle"} or mp4.stat().st_size < 50000:
        raise ValueError("Salida incompleta: se requieren video, narración y subtítulos.")

    manifest = {
        "schema": "suite-ultra-cap-v1-voice-sync-preview",
        "source_workflow_run": SOURCE_RUN_ID,
        "source_ticket_id": SOURCE_TICKET_ID,
        "source_branch_id": SOURCE_BRANCH_ID,
        "source_is_readonly": True,
        "new_production_requests": 0,
        "narrator": VOICE,
        "provider": "edge-tts experimental, NO producción",
        "pronunciation_alias": ALIAS_PRONUNCIACION,
        "source_video_seconds": round(end, 3),
        "result_video_seconds": round(result_video_duration, 3),
        "scenes": scenes,
        "files": [mp4.name, out_srt.name],
    }
    (OUTPUT_DIR / "manifiesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "CAPV1 VOICE SYNC PREVIEW PASS "
        f"source_run={SOURCE_RUN_ID} scene_count={len(scenes)} "
        f"video_seconds={result_video_duration:.3f} bytes={mp4.stat().st_size}"
    )


if __name__ == "__main__":
    create_synced_preview()
