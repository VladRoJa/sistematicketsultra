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
    wanted = ("inicio", "ticket", "parcial", "completo", "cierre",
              "rechazo", "reversion", "historial", "fin")
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
        if len(links) != 3 or received != 2:
            raise RuntimeError("CAP-V1: la reversión final no dejó 2/3 recibidos")
        if ticket.estado in ("finalizado", "cerrado", "por_validar"):
            raise RuntimeError("CAP-V1: ticket no debe quedar cerrado/por validar")

    path = root / "capacitacion.mp4"
    report = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path)
    ], text=True))
    streams = {x["codec_type"]: x.get("codec_name") for x in report["streams"]}
    duration = float(report["format"]["duration"])
    if (streams.get("video") != "h264" or streams.get("subtitle") != "mov_text"
            or duration < 60 or path.stat().st_size < 50000):
        raise RuntimeError("CAP-V1: MP4/subtítulos incompletos")
    if not (root / "subtitulos.srt").is_file():
        raise RuntimeError("CAP-V1: faltan subtítulos externos")
    print(f"CAP-V1 FULL UI QA PASS: {len(scenes)} escenas, {received}/3, {duration:.1f} s")


if __name__ == "__main__":
    main()
