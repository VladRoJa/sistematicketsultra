from sqlalchemy.dialects import postgresql

from app.services.purchase_requisition_workflow_service import (
    _locked_requisition_stmt,
)


def test_workflow_mutations_use_postgresql_row_lock():
    sql = str(
        _locked_requisition_stmt(123).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    assert "FOR UPDATE" in sql
    assert "PURCHASE_REQUISITIONS.ID = 123" in sql
