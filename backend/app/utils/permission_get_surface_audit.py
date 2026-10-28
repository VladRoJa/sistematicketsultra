"""P33: GET method/route exposure triage (read-only, manual, no handlers).

Static URL/handler-name classification is a REVIEW QUEUE, never an auth decision.
Only reads the current PostgreSQL route map in SET TRANSACTION READ ONLY,
using the existing P25 reader and Flask url_map introspection.
"""
from collections import Counter
from datetime import datetime, timezone
import json

from app.utils.permission_route_inventory import (
    compare_route_maps, flask_registry, read_current_route_map,
)

PRIORITY = {
    "oauth_callback_protocol": 1,
    "internal_or_machine_protocol": 1,
    "download_export_or_document": 1,
    "identity_or_personal_records": 1,
    "operational_and_financial_data": 2,
    "general_read_review": 3,
}

EXPORT_WORDS = (
    "export", "download", "archivo", "attachment", "evidence",
    "file", "document", "pdf", "xlsx", "csv", "comprobante", "image",
)
PERSON_WORDS = (
    "usuarios", "users", "contact", "socio", "member", "client",
    "lead", "persona", "rh", "rrhh", "employee", "personal", "nomina",
    "payroll", "candidate", "candidato", "telefono", "phone",
)
OPERATIONS_WORDS = (
    "warehouse", "track", "marketing", "ticket", "inventario", "inventory",
    "purchase", "finance", "apertura", "openings", "report", "kpi",
    "permissions", "permission", "system-daily", "pm", "mantenimiento",
    "rpa", "routine", "contact-center", "ads", "monitor",
)
INTERNAL_WORDS = ("internal", "scheduler", "webhook", "machine", "worker")


def get_review_priority(route: str, endpoint: str = "") -> str:
    """Heuristic text triage. Neither implies nor certifies protection."""
    path = str(route or "").lower()
    hint = (path + " " + str(endpoint or "").lower())
    if ("oauth" in hint or "google-ads" in path) and "callback" in hint:
        return "oauth_callback_protocol"
    if any(x in hint for x in INTERNAL_WORDS):
        return "internal_or_machine_protocol"
    if any(x in hint for x in EXPORT_WORDS):
        return "download_export_or_document"
    if any(x in hint for x in PERSON_WORDS):
        return "identity_or_personal_records"
    if any(x in hint for x in OPERATIONS_WORDS):
        return "operational_and_financial_data"
    return "general_read_review"


def make_get_review_report(reconciliation: dict) -> dict:
    """Preserve exactly the unmapped GET identities from live reconciliation."""
    items = [
        row for row in reconciliation["route_rows"]
        if row["method"] == "GET"
        and row["classification"] not in {"exact", "handler_alias"}
    ]
    seen = set()
    result = []
    for row in sorted(items, key=lambda r: (r["route"], r["endpoint"])):
        key = (row["method"], row["route"], row["endpoint"])
        if key in seen:
            raise ValueError("Duplicated GET identity: " + repr(key))
        seen.add(key)
        group = get_review_priority(row["route"], row["endpoint"])
        result.append({
            "method": "GET",
            "route": row["route"],
            "endpoint": row["endpoint"],
            "family": row["family"],
            "catalog_classification": row["classification"],
            "review_category": group,
            "priority": PRIORITY[group],
            "jwt_enforcement_checked": False,
            "resource_scope_checked": False,
            "user_data_accessed": False,
            "decision": "review_required",
        })
    counts = Counter(row["review_category"] for row in result)
    by_family = Counter(row["family"] for row in result)
    return {
        "read_only": True,
        "handlers_executed": False,
        "auth_or_branch_scope_certified": False,
        "basis": "live Flask url_map + PostgreSQL permission_route_map",
        "historical_get_uncatalogued_reference_20261026": 247,
        "count": len(result),
        "review_category_counts": dict(sorted(counts.items())),
        "review_family_counts": dict(sorted(by_family.items())),
        "items": result,
    }


def main() -> None:
    from app import create_app
    from app.extensions import db

    app = create_app()
    with app.app_context():
        current = read_current_route_map(db.engine)
        report = compare_route_maps(flask_registry(app), current)
    result = make_get_review_report(report)
    result["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
