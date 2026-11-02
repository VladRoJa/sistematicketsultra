#!/usr/bin/env python3
"""Prueba aislada de voz, sin credenciales, usuarios ni datos de Suite Ultra.

SOLO EVALUACIÓN: edge-tts utiliza un endpoint no contractual de Microsoft Edge.
No integrar este método en el pipeline productivo sin definir proveedor formal.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

VOICE = "es-MX-JorgeNeural"
TEXT = (
    "Bienvenido a Suite Ultra. Hoy vamos a revisar un ticket de tapizado "
    "con tres aparatos. Te mostraré cómo consultar su historial, identificar "
    "el avance de cada equipo y verificar su estado. Todo con información "
    "de prueba, sin cambiar datos reales."
)
OUTPUT = Path("artifacts/capacitacion/voz-demo")
DURATION = 15.0


def run(*args: str) -> str:
    completed = subprocess.run(
        args, check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = OUTPUT / "jorge-neural-original.mp3"
    finished = OUTPUT / "jorge-neural-15s.mp3"

    run(
        "edge-tts", "--voice", VOICE, "--rate=-5%",
        "--text", TEXT, "--write-media", str(original),
    )
    duration = float(run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(original),
    ))
    if not 8.0 <= duration <= 25.0:
        raise RuntimeError(f"Duración inesperada para narración breve: {duration:.2f}s")

    # Ajustar ligeramente el tempo sin cortar palabras.
    tempo = duration / DURATION
    run(
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(original), "-af",
        f"atempo={tempo:.5f},loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur=15",
        "-t", str(DURATION), "-codec:a", "libmp3lame", "-q:a", "3",
        str(finished),
    )
    final_duration = float(run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(finished),
    ))
    if abs(final_duration - DURATION) > 0.12 or finished.stat().st_size < 10000:
        raise RuntimeError("La prueba de audio no alcanzó duración/tamaño válidos.")

    (OUTPUT / "texto.txt").write_text(TEXT + "\n", encoding="utf-8")
    (OUTPUT / "manifest.json").write_text(
        json.dumps({
            "purpose": "voice-evaluation-only",
            "voice": VOICE,
            "duration_seconds": round(final_duration, 3),
            "provider": "edge-tts / interfaz no oficial, no producción",
            "demo_only": True,
            "ticket_data_included": False,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    original.unlink()
    print(f"VOICE_PREVIEW_PASS duration={final_duration:.2f}s bytes={finished.stat().st_size}")


if __name__ == "__main__":
    main()
