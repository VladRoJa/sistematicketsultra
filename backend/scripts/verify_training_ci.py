"""Gate de aceptación CAP-V1 tras grabación real en runner sintético."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from sqlalchemy.engine import make_url


def main() -> None:
    parsed = make_url(os.environ["SQLALCHEMY_DATABASE_URI"])
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("CAP_V1_SYNTHETIC_CI") != "YES_TEMPORARY_DB"
            or parsed.database != "suite_ultra_tickets_qa"
            or parsed.host != "127.0.0.1"
            or parsed.username != "cap_v1_ci"):
        raise RuntimeError("No se permite verificar contra DB no sintética")

    root = Path("../artifacts/capacitacion/tapizado-full")
    dataset = json.loads((root / "dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifiesto.json").read_text(encoding="utf-8"))
    v2 = manifest.get("cap_v2_source") is True
    wanted = ("inicio", "ticket", "parcial", "completo", "cierre",
              "rechazo", "reversion", "historial")
    if v2:
        wanted += ("subsanacion", "reenvio", "aprobacion")
    wanted += ("fin",)
    scenes = manifest["escenas"]
    if (manifest["schema"] != "suite-ultra-training-v1"
            or len(scenes) != len(wanted)
            or tuple(s["key"] for s in scenes) != wanted
            or dataset["mode"] != "EPHEMERAL_SYNTHETIC_UI"
            or dataset["ticket_id"] != manifest["ticket_id_demo"]
            or dataset["branch_id"] != 990101):
        raise RuntimeError("CAP-V1: nueve escenas/fixture inválidos")

    from app import create_app
    from app.extensions import db
    from app.models.ticket_model import Ticket

    app = create_app()
    with app.app_context():
        ticket = db.session.get(Ticket, dataset["ticket_id"])
        if not ticket or ticket.sucursal_id_destino != 990101:
            raise RuntimeError("CAP-V1: ticket no coincide con sucursal sintética")
        links = ticket.aparatos_asociados
        received = sum(1 for link in links if link.recibido_en_utc is not None)
        if len(links) != 3:
            raise RuntimeError("CAP-V1/CAP-V2: inventario sintético inesperado")
        if v2:
            if received != 3 or ticket.estado != "finalizado" or ticket.estado_cierre:
                raise RuntimeError("CAP-V2: aprobación no terminó en 3/3 y finalizado")
            events = [e.get("tipo") for e in (ticket.historial_fechas or [])]
            if ("rechazo_cierre_gerente" not in events
                    or "maintenance_conformity_accepted_v1" not in events):
                raise RuntimeError("CAP-V2: falta historial de rechazo y aprobación")
        elif (received != 2
              or ticket.estado in ("finalizado", "cerrado", "por_validar")):
            raise RuntimeError("CAP-V1: reversión final inválida, esperado 2/3 sin cierre")

    # CAP-V2: el master incluye cortes exactos por rol; sin cambios de cuenta en clips.
    if v2:
        wanted_roles = {
            "inicio": "mantenimiento", "ticket": "mantenimiento",
            "parcial": "mantenimiento", "completo": "mantenimiento",
            "cierre": "mantenimiento", "rechazo": "gerencia",
            "reversion": "mantenimiento", "historial": "mantenimiento",
            "subsanacion": "mantenimiento", "reenvio": "mantenimiento",
            "aprobacion": "gerencia", "fin": "gerencia",
        }
        segments = manifest.get("segmentos", [])
        previous_end = 0
        if len(segments) != len(wanted_roles):
            raise RuntimeError("CAP-V2: faltan secciones de rol")
        for marker, (key, role) in zip(segments, wanted_roles.items()):
            if (marker.get("key") != key or marker.get("role") != role
                    or marker["start"] < previous_end - .005
                    or marker["end"] <= marker["start"]):
                raise RuntimeError("CAP-V2: corte temporal o permiso/rol incorrecto")
            previous_end = marker["end"]
        if not (root / "navegacion.webm").is_file():
            raise RuntimeError("CAP-V2: falta grabación maestra para edición")
    path = root / "capacitacion.mp4"
    report = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path)
    ], text=True))
    streams = {x["codec_type"]: x.get("codec_name") for x in report["streams"]}
    duration = float(report["format"]["duration"])
    if (streams.get("video") != "h264" or streams.get("subtitle") != "mov_text"
            or duration < (25 if v2 else 60) or path.stat().st_size < 50000):
        raise RuntimeError("CAP-V1: MP4/subtítulos incompletos")
    if not (root / "subtitulos.srt").is_file():
        raise RuntimeError("CAP-V1: faltan subtítulos externos")
    print(f"CAP-{'V2' if v2 else 'V1'} FULL UI QA PASS: "
          f"{len(scenes)} escenas, {received}/3, "
          f"estado={ticket.estado}, {duration:.1f} s")


if __name__ == "__main__":
    main()
