# backend\app\utils\warehouse_audit.py


from app.extensions import db
from app.models import WarehouseAuditLogORM


def log_warehouse_audit(
    *,
    action: str,
    performed_by_user_id: int,
    upload_id: int | None = None,
    details: dict | None = None,
) -> WarehouseAuditLogORM:
    audit = WarehouseAuditLogORM(
        upload_id=upload_id,
        action=action,
        performed_by_user_id=performed_by_user_id,
        details=details or {},
    )

    db.session.add(audit)
    return audit