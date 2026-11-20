from unittest.mock import Mock

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
