"""WSO-01: preflight and quarantining of obsolete Corte de Caja RAW files.

Run from the existing Flask/backend runtime. Default is READ ONLY.
Do not invoke mutate modes before backup/restore and deployment approval.
The script NEVER invokes DROP/DELETE in PostgreSQL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    p.add_argument("mode", choices=["inspect", "quarantine", "restore", "purge"])
    p.add_argument("--root", type=Path, required=True, help="Absolute project root with uploads/warehouse")
    p.add_argument("--manifest", type=Path, required=True, help="Private manifest outside uploads/")
    p.add_argument("--quarantine-dir", type=Path, required=True)
    p.add_argument("--expected-count", type=int, default=2061)
    p.add_argument("--expected-bytes", type=int, default=5961032253)
    p.add_argument("--apply", action="store_true", help="Required to mutate the filesystem")
    p.add_argument("--ack-irreversible", action="store_true", help="Required for final purge")
    args = p.parse_args()

    if not args.root.is_absolute() or not args.quarantine_dir.is_absolute():
        raise RuntimeError("WSO-01 blocked: use absolute filesystem paths")
    root = args.root.resolve(strict=True)
    quarantine = args.quarantine_dir.resolve()
    manifest = args.manifest.resolve()
    if not quarantine.is_relative_to(root) or not manifest.is_relative_to(root):
        raise RuntimeError("WSO-01 blocked: quarantine/manifest must be inside project root")
    if quarantine.is_relative_to(root / "uploads") or manifest.is_relative_to(root / "uploads"):
        raise RuntimeError("WSO-01 blocked: quarantine and manifest must be outside uploads")
    if quarantine.is_symlink() or manifest.is_symlink():
        raise RuntimeError("WSO-01 blocked: manifest/quarantine cannot be symlinks")

    if args.mode == "inspect":
        if manifest.exists():
            raise RuntimeError("WSO-01 blocked: manifest already exists (no overwrite)")
        items = _items_from_db(root, expected_count=args.expected_count, expected_bytes=args.expected_bytes)
        payload = {"report_key": REPORT_KEY, "items": items}
        print(json.dumps({"mode": "inspect", "files_verified": len(items), "bytes": sum(x["size"] for x in items)}))
        # Creation of a private manifest is the only write in inspection mode.
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        manifest.chmod(0o600)
        return

    items = _read_manifest(manifest)
    if len(items) != args.expected_count or sum(x["size"] for x in items) != args.expected_bytes:
        raise RuntimeError("WSO-01 blocked: manifest totals differ")
    if not args.apply:
        print(json.dumps({"mode": args.mode, "dry_run": True, "files": len(items)}))
        return

    if args.mode == "quarantine":
        fresh = _items_from_db(root, expected_count=args.expected_count, expected_bytes=args.expected_bytes)
        if fresh != items:
            raise RuntimeError("WSO-01 blocked: manifest differs from live database")
        # All files were fully verified before moving the first byte.
        quarantine.mkdir(parents=True, exist_ok=True)
        moved = []
        try:
            for item in items:
                rel = Path(item["relative"])
                source = _safe_file(root, rel, must_exist=True)
                dest = _safe_file(quarantine, rel, must_exist=False)
                if dest.exists():
                    raise RuntimeError("WSO-01 blocked: quarantine target already exists")
                dest.parent.mkdir(parents=True, exist_ok=True)
                source.rename(dest)  # Same-filesystem move; no copy or unlink.
                moved.append((source, dest))
        except Exception:
            for source, dest in reversed(moved):
                dest.rename(source)
            raise
        print(json.dumps({"mode": "quarantine", "moved": len(moved)}))
        return

    # Restore / purge are independent of the retired database rows.
    if args.mode == "purge":
        remaining = _read_db()
        if remaining:
            raise RuntimeError("WSO-01 blocked: Corte de Caja metadata still exists in DB")
        if not args.ack_irreversible:
            raise RuntimeError("WSO-01 blocked: --ack-irreversible required")
    verified = []
    for item in items:
        rel = Path(item["relative"])
        source = _safe_file(root, rel, must_exist=False)
        dest = _safe_file(quarantine, rel, must_exist=True)
        if args.mode == "restore" and source.exists():
            raise RuntimeError("WSO-01 blocked: original path already exists")
        if dest.stat().st_size != item["size"] or _sha256(dest) != item["sha256"]:
            raise RuntimeError("WSO-01 blocked: quarantined file checksum mismatch")
        verified.append((source, dest))
    for source, dest in verified:
        if args.mode == "restore":
            source.parent.mkdir(parents=True, exist_ok=True)
            dest.rename(source)
        else:
            dest.unlink()
    print(json.dumps({"mode": args.mode, "files": len(verified)}))


if __name__ == "__main__":
    main()
