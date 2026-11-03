#!/usr/bin/env python3
"""CAP-V2: una captura sintética, tres capacitaciones segmentadas por rol.

Los cortes proceden de marcas del recorrido real (ANTES de cada acción).
No se graban cambios de usuario ni se reutilizan timestamps narrativos V1.
JorgeNeural/edge-tts es EXPERIMENTAL; nada se publica automáticamente.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

SOURCE = Path("artifacts/capacitacion/tapizado-full")
OUTPUT = Path("artifacts/capacitacion/tapizado-v2")
SCENE_ROLES = {
    "ticket": "mantenimiento",
    "parcial": "mantenimiento",
    "completo": "mantenimiento",
    "cierre": "mantenimiento",
    "rechazo": "gerencia",
    "reversion": "mantenimiento",
    "historial": "mantenimiento",
}
PROFILES = {
    "mantenimiento": ("ticket", "parcial", "completo", "cierre", "reversion", "historial"),
    "gerencia": ("rechazo",),
    "integral": ("ticket", "parcial", "completo", "cierre", "rechazo", "reversion", "historial"),
}
# Locuciones deliberadamente breves: se explican las acciones MIENTRAS ocurren.
# El material del gerente demuestra RECHAZO, no aprobación (aún no grabada).
NARRATION = {
    "ticket": "Abre el ticket de tapizado y revisa los aparatos relacionados.",
    "parcial": "Marca los equipos recibidos y guarda los cambios. La recepción queda parcial.",
    "completo": "Registra el aparato restante. Con todos recibidos, se permite solicitar conformidad.",
    "cierre": "Escribe las notas y solicita conformidad. La gerencia revisará la solicitud.",
    "rechazo": "En la vista de gerencia, revisa la solicitud. Si no procede, rechaza e indica el motivo.",
    "reversion": "Si el cierre fue rechazado, mantenimiento corrige la recepción, captura el motivo y guarda.",
    "historial": "En Ver Historial consulta responsables, fechas y motivos registrados.",
}
EXPECTED_ORDER = ("inicio", "ticket", "parcial", "completo", "cierre", "rechazo",
                  "reversion", "historial", "fin")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MAX_SPEECH_TEMPO = 1.35


def run(args: list[str]) -> str:
    proc = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    return proc.stdout.strip()


def seconds(path: Path, stream: str = "v:0") -> float:
    result = run(["ffprobe", "-v", "error", "-select_streams", stream,
                  "-show_entries", "stream=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    # Playwright graba WebM VP8, cuyo stream suele omitir duration.
    if result and result != "N/A":
        return float(result)
    result = run(["ffprobe", "-v", "error", "-show_entries",
                  "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    if not result or result == "N/A":
        raise ValueError(f"CAP-V2: sin duración verificable de {path.name}")
    return float(result)


def stamp(sec: float) -> str:
    milli = round(sec * 1000)
    hh, milli = divmod(milli, 3600000)
    mm, milli = divmod(milli, 60000)
    ss, milli = divmod(milli, 1000)
    return f"{hh:02}:{mm:02}:{ss:02},{milli:03}"


def load_source():
    dataset = json.loads((SOURCE / "dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads((SOURCE / "manifiesto.json").read_text(encoding="utf-8"))
    source = SOURCE / "navegacion.webm"
    if (os.environ.get("CAP_V1_SYNTHETIC_CI") != "YES_TEMPORARY_DB"
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or dataset.get("mode") != "EPHEMERAL_SYNTHETIC_UI"
            or dataset.get("branch_id") != 990101
            or len(dataset.get("codes", [])) != 3
            or dataset.get("ticket_id") != manifest.get("ticket_id_demo")
            or manifest.get("schema") != "suite-ultra-training-v1"
            or manifest.get("cap_v2_source") is not True
            or manifest.get("entorno") != "loopback-aislado-declarado"
            or not source.is_file()):
        raise ValueError("CAP-V2: únicamente fuente CI aislada y sintética")
    segments = manifest.get("segmentos", [])
    if tuple(s.get("key") for s in segments) != EXPECTED_ORDER:
        raise ValueError("CAP-V2: marcadores de nueve escenas incompletos")
    video_seconds = seconds(source)
    previous = 0.0
    result = {}
    for seg in segments:
        key = seg["key"]
        expected_role = "gerencia" if key == "rechazo" else "mantenimiento"
        start, end = float(seg["start"]), float(seg["end"])
        if (seg["role"] != expected_role or start < previous - 0.005
                or end <= start or end > video_seconds + 1.0):
            raise ValueError(f"CAP-V2: corte o rol inválido en {key}")
        previous = end
        result[key] = {"start": start, "end": end, "role": seg["role"]}
    for profile, keys in PROFILES.items():
        if any(result[key]["role"] != SCENE_ROLES[key] for key in keys):
            raise ValueError(f"CAP-V2: acciones de otro rol en perfil {profile}")
    return result, source, dataset


def synthesize(key: str, target: Path) -> float:
    phrase = NARRATION[key].replace("Suite Ultra", "Súit Ultra")
    run(["edge-tts", "--voice", "es-MX-JorgeNeural", "--rate=-5%",
         "--text", phrase, "--write-media", str(target)])
    return seconds(target, "a:0")


def render_clip(key: str, seg: dict, source: Path, clips: Path):
    start, end = seg["start"], seg["end"]
    duration = end - start
    if duration < 1.1:
        raise ValueError(f"CAP-V2: escena demasiado corta para narrar: {key}")
    voice = clips / f"{key}.mp3"
    natural = synthesize(key, voice)
    # Dejar 250ms para ver el resultado; nunca estirar silencios artificiales.
    available = duration - 0.25
    tempo = max(1.0, natural / available)
    if tempo > MAX_SPEECH_TEMPO:
        raise ValueError(f"CAP-V2: narración {key} requiere {tempo:.2f}x; "
                         "acortar el guion, no congelar la pantalla")
    role_label = "GERENCIA" if seg["role"] == "gerencia" else "MANTENIMIENTO"
    # Rótulo de rol visible tanto en la edición integral como individual.
    vf = (
        "fps=25,scale=1920:1080,format=yuv420p,"
        "drawbox=x=1510:y=23:w=370:h=64:color=black@0.72:t=fill,"
        f"drawtext=fontfile={FONT}:text='{role_label}':"
        "fontsize=28:fontcolor=white:x=1530:y=41"
    )
    path = clips / f"{key}.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-i", str(voice),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]atempo={tempo:.5f},"
                           "aresample=48000,apad[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(path),
    ])
    actual = seconds(path)
    if abs(actual - duration) > 0.25:
        raise ValueError(f"CAP-V2: corte {key} cambió duración inesperadamente")
    return path, actual, natural / tempo, tempo


def render_profile(profile: str, keys: tuple, assets: dict):
    folder = OUTPUT / profile
    folder.mkdir(parents=True, exist_ok=True)
    concat = folder / "clips.txt"
    concat.write_text("".join(
        "file '" + str(assets[key][0].resolve()).replace("'", "'\\''") + "'\n"
        for key in keys), encoding="utf-8")
    srt_lines = []
    at = 0.0
    report_scenes = []
    for index, key in enumerate(keys, start=1):
        _, length, spoken, tempo = assets[key]
        sub_end = min(length - 0.06, spoken + 0.10)
        if sub_end <= 0:
            raise ValueError("CAP-V2: subtítulo fuera de escena")
        srt_lines.append(
            f"{index}\n{stamp(at)} --> {stamp(at + sub_end)}\n"
            f"{NARRATION[key]}\n"
        )
        report_scenes.append({
            "key": key, "role": SCENE_ROLES[key],
            "start": round(at, 3), "duration": round(length, 3),
            "tempo": round(tempo, 3),
        })
        at += length
    srt = folder / "subtitulos.srt"
    srt.write_text("\n".join(srt_lines) + "\n", encoding="utf-8")
    mp4 = folder / f"tapizado-{profile}.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(srt),
        "-map", "0:v:0", "-map", "0:a:0", "-map", "1:s:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=spa", "-movflags", "+faststart",
        str(mp4),
    ])
    duration = seconds(mp4)
    audio_duration = seconds(mp4, "a:0")
    if abs(duration - audio_duration) > 0.25 or abs(duration - at) > 0.50:
        raise ValueError(f"CAP-V2: audio y video desincronizados en {profile}")
    if any(x["role"] != profile for x in report_scenes) and profile != "integral":
        raise ValueError(f"CAP-V2: contaminación de roles: {profile}")
    report = {
        "schema": "suite-ultra-cap-v2-role-cut",
        "profile": profile,
        "source": "recorrido sintético real CAP-V2",
        "voice": "es-MX-JorgeNeural (EXPERIMENTAL, no integrado en producto)",
        "production_requests": 0,
        "publication": "NO PUBLICAR / NO MERGE AUTOMÁTICO",
        "scenes": report_scenes,
        "duration": round(duration, 3),
        "audio_duration": round(audio_duration, 3),
        "coverage": ("Demuestra rechazo, NO aprobación" if profile == "gerencia"
                     else "Recorrido sintético de recepción y cierre"),
    }
    (folder / "manifiesto.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    if not all(shutil.which(binary) for binary in ("ffmpeg", "ffprobe", "edge-tts")):
        raise RuntimeError("CAP-V2: faltan FFmpeg, FFprobe o edge-tts")
    if not Path(FONT).is_file():
        raise RuntimeError("CAP-V2: fuente para rótulos de rol no disponible")
    segments, source, _ = load_source()
    clips = OUTPUT / "_clips"
    clips.mkdir(parents=True, exist_ok=True)
    assets = {key: render_clip(key, segments[key], source, clips)
              for key in SCENE_ROLES}
    reports = {profile: render_profile(profile, keys, assets)
               for profile, keys in PROFILES.items()}
    print("CAP-V2 ROLE-CUT PASS", {
        profile: (len(report["scenes"]), report["duration"])
        for profile, report in reports.items()
    })


if __name__ == "__main__":
    main()
