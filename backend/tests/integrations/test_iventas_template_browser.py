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


@pytest.mark.parametrize("inventory_url", [
    "https://app.iventas.com/whatsappTemplate/list",
    "https://rest.iventas.mx/whatsappTemplate/0123456789abcdef01234567",
])
@pytest.mark.parametrize(("provider_channel", "provider_state", "portal_label", "expected"), [
    ("channel-1", "accepted", "Aprobada", "APPROVED"),
    ("channel-2", "accepted", "Aprobada", "IN_REVIEW"),
    ("channel-1", "pending", "En revisión", "IN_REVIEW"),
    ("channel-1", "rejected", "Rechazada", "REJECTED"),
])
def test_approval_requires_inventory_for_exact_channel(
    monkeypatch, inventory_url, provider_channel, provider_state, portal_label, expected,
):
    browser = Mock()
    context = browser.new_context.return_value
    page = context.new_page.return_value
    response = Mock(url=inventory_url, ok=True)
    response.request.method = "GET"
    response.json.return_value = [{
        "name": "asistencia_demo", "status": provider_state,
        "channelId": provider_channel, "channel": {"id": provider_channel, "name": "QA"},
    }]
    page.on.side_effect = lambda _event, listener: listener(response)
    row = page.get_by_role.return_value.filter.return_value.filter.return_value
    row.get_by_text.side_effect = lambda label, **_: Mock(
        first=Mock(is_visible=Mock(return_value=label == portal_label)),
    )
    monkeypatch.setattr(adapter, "_login", Mock())
    monkeypatch.setattr(adapter, "_open_inventory", Mock())

    status, _ = adapter.read_template_approval(
        browser, None, {"name": "asistencia_demo", "category": "MARKETING"}, "channel-1",
    )

    assert status == expected
    context.close.assert_called_once()


@pytest.mark.parametrize(("url", "method"), [
    ("https://graph-v2.iventas.mx/whatsappTemplate/account", "GET"),
    ("https://rest.iventas.mx.example.test/whatsappTemplate/account", "GET"),
    ("http://rest.iventas.mx/whatsappTemplate/account", "GET"),
    ("https://rest.iventas.mx/whatsappTemplate/account", "POST"),
    ("https://rest.iventas.mx/v2/broadcast", "GET"),
])
def test_inventory_ignores_unrelated_responses(url, method):
    response = Mock(url=url, ok=True)
    response.request.method = method

    assert not adapter._inventory_response(response)


def test_read_full_inventory_uses_one_login_and_only_provider_get(monkeypatch):
    browser = Mock()
    context = browser.new_context.return_value
    page = context.new_page.return_value
    response = Mock(url="https://rest.iventas.mx/whatsappTemplate/list", ok=True)
    response.request.method = "GET"
    response.json.return_value = [
        {"name": "1regresa_299_n3", "status": "accepted", "channelId": "channel-1",
         "channel": {"id": "channel-1", "name": "Costa"}},
        {"name": "2regresa_299_n3", "status": "pending", "channelId": "channel-1",
         "channel": {"id": "channel-1", "name": "Costa"}},
    ]
    login = Mock()
    open_inventory = Mock()
    monkeypatch.setattr(adapter, "_login", login)
    monkeypatch.setattr(adapter, "_open_inventory", open_inventory)
    page.on.side_effect = lambda _event, callback: callback(response)

    result = adapter.read_template_inventory(browser, None)

    assert [(r.template_name, r.status) for r in result] == [
        ("1regresa_299_n3", "accepted"), ("2regresa_299_n3", "pending"),
    ]
    login.assert_called_once()
    open_inventory.assert_called_once_with(page)
    page.get_by_role.assert_not_called()
    context.close.assert_called_once()


def test_read_full_inventory_fails_closed_if_not_observed_or_conflicting(monkeypatch):
    browser = Mock()
    context = browser.new_context.return_value
    page = context.new_page.return_value
    monkeypatch.setattr(adapter, "_login", Mock())
    monkeypatch.setattr(adapter, "_open_inventory", Mock())

    with pytest.raises(adapter.TemplateBrowserError, match="no devolvió"):
        adapter.read_template_inventory(browser, None)

    accepted = Mock(url="https://rest.iventas.mx/whatsappTemplate/list", ok=True)
    accepted.request.method = "GET"
    accepted.json.return_value = [{
        "name": "1regresa_299_n3", "status": "accepted", "channelId": "channel-1",
        "channel": {"id": "channel-1", "name": "Costa"},
    }]
    rejected = Mock(url="https://rest.iventas.mx/whatsappTemplate/list", ok=True)
    rejected.request.method = "GET"
    rejected.json.return_value = [{
        "name": "1regresa_299_n3", "status": "rejected", "channelId": "channel-1",
        "channel": {"id": "channel-1", "name": "Costa"},
    }]
    page.on.side_effect = lambda _event, callback: [callback(accepted), callback(rejected)]
    with pytest.raises(adapter.TemplateBrowserError, match="contradictorios"):
        adapter.read_template_inventory(browser, None)
