#!/usr/bin/env python3
"""CAP-V1: doblaje JorgeNeural experimental de nueve escenas del QA aislado.

No visita Suite Ultra, ni usa credenciales. Fuente: artifact de CI sintético.
edge-tts es una interfaz NO contractual, no se propone para producción.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from scripts.training.voice_sync_preview import (
    ALIAS_PRONUNCIACION, VOICE, probe_duration, run, srt_timestamp,
)

EXPECTED = ("inicio", "ticket", "parcial", "completo", "cierre",
            "rechazo", "reversion", "historial", "fin")
INPUT = Path("artifacts/capacitacion/full-source")
OUTPUT = Path("artifacts/capacitacion/full-neural-preview")
MARGIN = 0.22
MAX_TEMPO = 1.30


def main() -> None:
    if not all(shutil.which(tool) for tool in ("edge-tts", "ffmpeg", "ffprobe")):
        raise RuntimeError("CAP-V1 Full: faltan sintetizador o FFmpeg")
    source_run = os.environ.get("CAP_V1_SOURCE_RUN_ID", "")
    if not source_run.isdecimal() or int(source_run) <= 0:
        raise RuntimeError("CAP-V1 Full: indicar fuente CI fija")

    data = json.loads((INPUT / "dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads((INPUT / "manifiesto.json").read_text(encoding="utf-8"))
    if (data.get("mode") != "EPHEMERAL_SYNTHETIC_UI"
            or data.get("branch_id") != 990101
            or len(data.get("codes", [])) != 3
            or manifest.get("schema") != "suite-ultra-training-v1"
            or manifest.get("ticket_id_demo") != data.get("ticket_id")
            or manifest.get("aparatos_demo") != 3
            or manifest.get("entorno") != "loopback-aislado-declarado"):
        raise ValueError("CAP-V1: fuente no sintética o manifiesto inesperado")
    original = manifest.get("escenas", [])
    if tuple(scene.get("key") for scene in original) != EXPECTED:
        raise ValueError("CAP-V1: faltan escenas del proceso completo")

    video = INPUT / "capacitacion.mp4"
    duration = float(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ]))
    starts = [float(scene["at"]) for scene in original]
    if not (70 < duration < 900 and 0 <= starts[0]
            and all(0 < a < b for a, b in zip(starts, starts[1:]))
            and starts[-1] < duration):
        raise ValueError("CAP-V1: duración/marcas no válidas")

    storyboard = json.loads(Path(
        "scripts/training/storyboards/tapizado_multiaparato.json"
    ).read_text(encoding="utf-8"))
    if any(original[i]["text"] != storyboard[key]
           for i, key in enumerate(EXPECTED)):
        raise ValueError("CAP-V1: narraciones no coinciden con storyboard revisado")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    filter_terms = [
        "anullsrc=channel_layout=stereo:sample_rate=48000,"
        f"atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[bed]"
    ]
    inputs, subtitles, scene_report = [], [], []
    for i, key in enumerate(EXPECTED):
        start = starts[i]
        next_at = starts[i + 1] if i < len(EXPECTED) - 1 else duration
        available = next_at - start - MARGIN
        if available <= 1.0:
            raise ValueError(f"CAP-V1: escena sin tiempo para hablar: {key}")
        text = storyboard[key]
        spoken = text
        for official, pronunciation in ALIAS_PRONUNCIACION.items():
            spoken = spoken.replace(official, pronunciation)
        mp3 = OUTPUT / f"voz-{i+1:02}-{key}.mp3"
        run(["edge-tts", "--voice", VOICE, "--rate=-5%",
             "--text", spoken, "--write-media", str(mp3)])
        natural = probe_duration(mp3)
        tempo = max(1.0, natural / available)
        if tempo > MAX_TEMPO:
            raise ValueError(
                f"CAP-V1: locución {key} requiere {tempo:.2f}x; "
                "revisar guion o duración, no acelerar en exceso"
            )
        spoken_seconds = natural / tempo
        inputs.extend(["-i", str(mp3)])
        filter_terms.append(
            f"[{i+1}:a]atempo={tempo:.5f},aresample=48000,"
            f"adelay={round(start * 1000)}:all=1[n{i}]"
        )
        sub_end = min(next_at - .08, start + spoken_seconds + .18)
        subtitles.append(
            f"{i+1}\n{srt_timestamp(start)} --> "
            f"{srt_timestamp(sub_end)}\n{text}\n"
        )
        scene_report.append({
            "key": key, "start": round(start, 3), "window": round(next_at-start, 3),
            "natural_voice_seconds": round(natural, 3),
            "tempo": round(tempo, 3),
        })
    srt = OUTPUT / "subtitulos.srt"
    srt.write_text("\n".join(subtitles) + "\n", encoding="utf-8")
    combined = "[bed]" + "".join(f"[n{i}]" for i in range(len(EXPECTED)))
    filter_terms.append(
        f"{combined}amix=inputs={len(EXPECTED)+1}:duration=first:normalize=0,"
        "volume=0.80,alimiter=limit=0.95[narracion]"
    )
    mp4 = OUTPUT / "tapizado-completo-jorge-neural.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), *inputs, "-i", str(srt),
        "-filter_complex", ";".join(filter_terms),
        "-map", "0:v:0", "-map", "[narracion]",
        "-map", f"{len(EXPECTED)+1}:s:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=spa",
        "-movflags", "+faststart", "-t", f"{duration:.3f}", str(mp4),
    ])
    a_duration = float(run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp4),
    ]))
    v_duration = float(run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp4),
    ]))
    if abs(duration - a_duration) > .18 or abs(duration - v_duration) > .18:
        raise ValueError(f"CAP-V1: voz/video desfasan {v_duration:.2f}/{a_duration:.2f}")
    report = {
        "schema": "suite-ultra-cap-v1-full-neural-preview",
        "provider": "edge-tts EXPERIMENTAL, no autorizado para producto",
        "source_workflow_run": int(source_run),
        "source_mode": "EPHEMERAL_SYNTHETIC_UI",
        "production_requests": 0,
        "scenes": scene_report,
        "narrator": VOICE,
        "pronunciation_alias": ALIAS_PRONUNCIACION,
        "video_seconds": round(v_duration, 3),
        "audio_seconds": round(a_duration, 3),
    }
    (OUTPUT / "manifiesto.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("CAP-V1 FULL JORGE PREVIEW PASS", round(v_duration, 3), len(scene_report))


if __name__ == "__main__":
    main()
