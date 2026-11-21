from unittest.mock import Mock, call

import pytest

from app.integrations.iventas import template_browser as adapter
from app.services.marketing_campaign_v2_template_credentials_service import IventasTemplateCredentials


def test_existing_template_ends_session_without_entering_create_wizard(monkeypatch):
    browser = Mock()
    context = browser.new_context.return_value
    page = context.new_page.return_value
    page.url = f"{adapter.ORIGIN}/login"
    inventory = Mock()
    monkeypatch.setattr(adapter, "_open_inventory", inventory)
    page.get_by_text.return_value.first.is_visible.return_value = True

    status, _ = adapter.upload_template(
        browser, IventasTemplateCredentials("qa@example.test", "synthetic-password"),
        {"name": "plantilla_existente"}, None, None,
    )

    assert status == "EXISTS"
    inventory.assert_called_once_with(page)
    page.goto.assert_called_once_with(f"{adapter.ORIGIN}/login", wait_until="domcontentloaded")
    assert page.get_by_role.call_count == 1
    context.close.assert_called_once()


def test_unexpected_login_origin_never_fills_the_form():
    browser = Mock()
    context = browser.new_context.return_value
    page = context.new_page.return_value
    page.url = "https://unexpected.example.test/login"

    status, _ = adapter.upload_template(
        browser, IventasTemplateCredentials("qa@example.test", "synthetic-password"),
        {"name": "plantilla_de_prueba"}, None, None,
    )

    assert status == "ERROR"
    page.locator.assert_not_called()
    context.close.assert_called_once()


@pytest.mark.parametrize("skipped", [False, True])
def test_category_step_goes_back_only_if_multimedia_opens_first(skipped):
    page, category, multimedia = Mock(), Mock(), Mock()
    multimedia.is_visible.return_value = skipped
    category.is_visible.return_value = not skipped
    actions = Mock()
    page.get_by_text.return_value.click = actions.go_back
    category.click = actions.choose_category
    page.get_by_role.return_value.click = actions.continue_wizard

    adapter._select_category(page, category, multimedia)

    expected = [call.choose_category(), call.continue_wizard()]
    if skipped:
        page.get_by_text.assert_called_once_with("Regresar", exact=True)
        expected.insert(0, call.go_back())
    assert actions.mock_calls == expected


def test_category_step_stops_if_regresar_does_not_show_requested_category():
    page, category, multimedia = Mock(), Mock(), Mock()
    multimedia.is_visible.return_value = True
    category.is_visible.return_value = False
    category.click.side_effect = adapter.PlaywrightTimeoutError("category unavailable")

    with pytest.raises(adapter.TemplateBrowserError, match="no mostró la categoría solicitada"):
        adapter._select_category(page, category, multimedia)

    page.get_by_text.return_value.click.assert_called_once_with()
    page.get_by_role.assert_not_called()
