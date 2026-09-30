from types import SimpleNamespace

from app.utils import internal_documents_access as access


def _context(*, user_id, username, role):
    return access.InternalDocumentUserContext(
        user_id=user_id,
        username=username,
        role=role,
        sucursal_id=None,
        sucursales_ids=tuple(),
        department_id=None,
    )


def _agregadoras_document():
    return SimpleNamespace(
        id=900,
        title="Consolidado de agregadoras",
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.CUSTOM,
        is_sensitive=True,
        current_version_id=901,
        created_by=7,
        owner_user_id=None,
    )


def test_agregadoras_access_is_limited_to_admicorp(monkeypatch):
    document = _agregadoras_document()

    monkeypatch.setattr(
        access,
        "_has_custom_visibility_access",
        lambda _document, context, _action: (
            str(context.username or "").strip().upper()
            == "ADMICORP"
        ),
    )

    admicorp = _context(
        user_id=77,
        username="ADMICORP",
        role="LECTOR_GLOBAL",
    )
    sistemas = _context(
        user_id=88,
        username="SISTEMAS_USER",
        role="SISTEMAS",
    )
    other = _context(
        user_id=99,
        username="OTRO",
        role="LECTOR_GLOBAL",
    )

    assert access.can_view_internal_document(
        document,
        admicorp,
    ) is True
    assert access.can_download_internal_document(
        document,
        admicorp,
    ) is True

    assert access.can_view_internal_document(
        document,
        sistemas,
    ) is False
    assert access.can_download_internal_document(
        document,
        sistemas,
    ) is False

    assert access.can_view_internal_document(
        document,
        other,
    ) is False
    assert access.can_download_internal_document(
        document,
        other,
    ) is False


def test_sistemas_keeps_admin_access_for_other_documents():
    document = SimpleNamespace(
        id=910,
        title="Manual operativo",
        status=access.InternalDocumentStatus.PUBLISHED,
        visibility_mode=access.InternalDocumentVisibilityMode.PRIVATE,
        is_sensitive=False,
        current_version_id=911,
        created_by=7,
        owner_user_id=None,
    )
    sistemas = _context(
        user_id=88,
        username="SISTEMAS_USER",
        role="SISTEMAS",
    )

    assert access.can_view_internal_document(
        document,
        sistemas,
    ) is True
    assert access.can_download_internal_document(
        document,
        sistemas,
    ) is True
