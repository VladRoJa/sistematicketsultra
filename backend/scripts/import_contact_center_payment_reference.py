"""Offline admin-only import; never run through the web request path.

Example:
  python scripts/import_contact_center_payment_reference.py \
    --file /app/runtime/payment-reference/incoming/padron.csv \
    --cutoff 2026-10-31 --dry-run

  python scripts/import_contact_center_payment_reference.py \
    --file /app/runtime/payment-reference/incoming/padron.csv \
    --cutoff 2026-10-31 \
    --archive-dir /app/runtime/payment-reference/archive --activate
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app import create_app
from app.services.contact_center_payment_reference_service import (
    import_payment_reference_csv,
    validate_payment_reference_csv,
)


def main():
    parser = argparse.ArgumentParser(description="Padrón histórico para ligas Contact Center")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        if args.activate:
            parser.error("--activate y --dry-run no se pueden combinar")
        result = validate_payment_reference_csv(args.file)
        print(json.dumps({"dry_run": True, "cutoff": args.cutoff.isoformat(),
                          **vars(result)}, ensure_ascii=False))
        return
    if not args.archive_dir:
        parser.error("--archive-dir es obligatorio para importación")

    app = create_app()
    with app.app_context():
        print(json.dumps(import_payment_reference_csv(
            file_path=args.file,
            cutoff_date=args.cutoff,
            archive_dir=args.archive_dir,
            activate=args.activate,
        ), ensure_ascii=False))


if __name__ == "__main__":
    main()
