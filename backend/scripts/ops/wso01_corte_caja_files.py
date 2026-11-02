"""WSO-01: verify and permanently delete retired Corte de Caja RAW files.

inspect: read-only DB/files + a private hash manifest (no copy of raw files).
delete: after Alembic migration, verify absence of the source in DB and every
remaining file against the manifest before unlinking anything.
No quarantine, no backup creation, no SQL modifications. Irreversible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import text

from app import create_app
from app.extensions import db

REPORT_KEY = "corte_caja"

UPLOADS_SQL = """
SELECT u.id, u.stored_path, u.stored_filename,
       u.file_size_bytes, u.file_hash_sha256
FROM public.warehouse_uploads u
JOIN public.warehouse_report_types rt ON rt.id = u.report_type_id
WHERE rt.key = :key
ORDER BY u.id
"""

SHARED_SQL = """
SELECT COUNT(*)
FROM public.warehouse_uploads a
JOIN public.warehouse_report_types rt ON rt.id = a.report_type_id
JOIN public.warehouse_uploads b
  ON b.id <> a.id
 AND b.stored_path = a.stored_path
 AND b.stored_filename = a.stored_filename
WHERE rt.key = :key
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_relative(stored_path: str, filename: str) -> Path:
    path = Path(stored_path)
    parts = path.parts
    if (
        path.is_absolute()
        or len(parts) != 6
        or parts[0:2] != ("uploads", "warehouse")
        or parts[3] != REPORT_KEY
        or not parts[4].isdigit()
        or len(parts[4]) != 4
        or not parts[5].isdigit()
        or len(parts[5]) != 2
        or any(part in {".", ".."} for part in parts)
        or Path(filename).name != filename
        or filename in {"", ".", ".."}
    ):
        raise RuntimeError("WSO-01 blocked: unexpected Warehouse storage path")
    return path / filename


def _safe_file(root: Path, relative: Path, *, must_exist: bool) -> Path:
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root):
        raise RuntimeError("WSO-01 blocked: path escapes approved root")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError("WSO-01 blocked: symbolic link in target path")
    if must_exist and (not candidate.is_file() or candidate.is_symlink()):
        raise RuntimeError("WSO-01 blocked: expected regular file is missing")
    return candidate


def _read_db():
    app = create_app()
    with app.app_context():
        records = db.session.execute(text(UPLOADS_SQL), {"key": REPORT_KEY}).mappings().all()
        collisions = db.session.execute(text(SHARED_SQL), {"key": REPORT_KEY}).scalar_one()
        db.session.rollback()
        db.session.remove()
    if int(collisions) != 0:
        raise RuntimeError("WSO-01 blocked: physical path shared by another upload")
    return [dict(row) for row in records]


def _assert_retired_in_db() -> None:
    """Only permit physical deletion after the destructive migration commits."""
    app = create_app()
    with app.app_context():
        state = db.session.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM public.warehouse_report_types
               WHERE key = :key) AS report_types,
              to_regclass('public.corte_caja_snapshots') IS NOT NULL AS headers_exist,
              to_regclass('public.corte_caja_snapshot_rows') IS NOT NULL AS rows_exist
        """), {"key": REPORT_KEY}).mappings().one()
        db.session.rollback()
        db.session.remove()
    if int(state["report_types"]) or state["headers_exist"] or state["rows_exist"]:
        raise RuntimeError(
            "WSO-01 blocked: Alembic retirement has not removed Corte de Caja metadata"
        )


def _items_from_db(root: Path, *, expected_count: int, expected_bytes: int) -> list[dict]:
    records = _read_db()
    actual_bytes = sum(int(row["file_size_bytes"]) for row in records)
    if len(records) != expected_count or actual_bytes != expected_bytes:
        raise RuntimeError(
            f"WSO-01 blocked: database changed (count={len(records)}, bytes={actual_bytes})"
        )
    items = []
    for row in records:
        relative = _validate_relative(str(row["stored_path"]), str(row["stored_filename"]))
        path = _safe_file(root, relative, must_exist=True)
        actual_size = path.stat().st_size
        if actual_size != int(row["file_size_bytes"]):
            raise RuntimeError(f"WSO-01 blocked: size mismatch for upload {row['id']}")
        if _sha256(path).lower() != str(row["file_hash_sha256"]).lower():
            raise RuntimeError(f"WSO-01 blocked: checksum mismatch for upload {row['id']}")
        items.append({
            "id": int(row["id"]),
            "relative": relative.as_posix(),
            "size": int(row["file_size_bytes"]),
            "sha256": str(row["file_hash_sha256"]).lower(),
        })
    return items


def _read_manifest(manifest: Path) -> list[dict]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("report_key") != REPORT_KEY or not isinstance(data.get("items"), list):
        raise RuntimeError("WSO-01 blocked: invalid manifest")
    items = data["items"]
    if len({row["id"] for row in items}) != len(items):
        raise RuntimeError("WSO-01 blocked: duplicate manifest IDs")
    for row in items:
        stored = Path(row["relative"])
        _validate_relative(str(stored.parent), stored.name)
    return items


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["inspect", "delete"])
    p.add_argument("--root", type=Path, required=True, help="Absolute project root with uploads/warehouse")
    p.add_argument("--manifest", type=Path, required=True, help="Private manifest outside uploads/")
    p.add_argument("--expected-count", type=int, default=2061)
    p.add_argument("--expected-bytes", type=int, default=5961032253)
    p.add_argument("--apply", action="store_true", help="Required to delete physical files")
    p.add_argument("--ack-irreversible", action="store_true", help="Explicit permanent-deletion acknowledgment")
    args = p.parse_args()

    if not args.root.is_absolute() or not args.manifest.is_absolute():
        raise RuntimeError("WSO-01 blocked: use absolute filesystem paths")
    root = args.root.resolve(strict=True)
    manifest = args.manifest
    # A manifest is a tiny inventory, never a copy of the RAW data.
    if manifest.is_symlink() or not manifest.resolve().is_relative_to(root):
        raise RuntimeError("WSO-01 blocked: manifest location is not trusted")
    if manifest.resolve().is_relative_to(root / "uploads"):
        raise RuntimeError("WSO-01 blocked: manifest must be outside uploads/")

    if args.mode == "inspect":
        if manifest.exists():
            raise RuntimeError("WSO-01 blocked: manifest already exists (no overwrite)")
        items = _items_from_db(
            root, expected_count=args.expected_count, expected_bytes=args.expected_bytes
        )
        payload = {"report_key": REPORT_KEY, "items": items}
        print(json.dumps({
            "mode": "inspect", "files_verified": len(items),
            "bytes": sum(x["size"] for x in items)
        }))
        manifest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        manifest.parent.chmod(0o700)
        fd = os.open(
            manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(json.dumps(payload, indent=2) + "\n")
        return

    items = _read_manifest(manifest)
    if len(items) != args.expected_count or sum(x["size"] for x in items) != args.expected_bytes:
        raise RuntimeError("WSO-01 blocked: manifest totals differ")

    _assert_retired_in_db()
    # Verify ALL remaining files before deleting the first one.
    # Missing paths may be due to a prior partial run; they are not deleted again.
    verified = []
    already_absent = 0
    for item in items:
        rel = Path(item["relative"])
        target = _safe_file(root, rel, must_exist=False)
        if not target.exists():
            already_absent += 1
            continue
        if not target.is_file() or target.is_symlink():
            raise RuntimeError(f"WSO-01 blocked: unsafe file for upload {item['id']}")
        if target.stat().st_size != item["size"] or _sha256(target) != item["sha256"]:
            raise RuntimeError(f"WSO-01 blocked: changed file for upload {item['id']}")
        verified.append(target)

    if not (args.apply and args.ack_irreversible):
        print(json.dumps({
            "mode": "delete", "dry_run": True,
            "verified_for_deletion": len(verified), "already_absent": already_absent
        }))
        return

    for target in verified:
        # Recheck pathname safety at time of use.
        rel = target.relative_to(root)
        _safe_file(root, rel, must_exist=True)
        target.unlink()

    print(json.dumps({
        "mode": "delete", "deleted": len(verified), "already_absent": already_absent
    }))


if __name__ == "__main__":
    main()
