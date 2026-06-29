
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


MESSAGES_NEW_URL = "https://messages.google.com/web/conversations/new"
DEFAULT_TIMEOUT_MS = 8000
DEFAULT_SETTLE_AFTER_SEND_MS = 2500


class GoogleMessagesSmsSenderError(RuntimeError):
    """Error controlado del sender Google Messages Web."""


@dataclass(frozen=True)
class GoogleMessagesSmsConfig:
    profile_dir: Path
    headless: bool = False
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    settle_after_send_ms: int = DEFAULT_SETTLE_AFTER_SEND_MS
    key_type_delay_ms: int = 5


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


def resolve_config_from_env() -> GoogleMessagesSmsConfig:
    backend_dir = Path(__file__).resolve().parents[3]

    profile_dir_raw = os.getenv("GOOGLE_MESSAGES_PROFILE_DIR")
    profile_dir = (
        Path(profile_dir_raw).expanduser().resolve()
        if profile_dir_raw
        else backend_dir / ".playwright" / "google_messages_profile"
    )

    timeout_ms = int(os.getenv("GOOGLE_MESSAGES_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)))
    settle_after_send_ms = int(
        os.getenv(
            "GOOGLE_MESSAGES_SETTLE_AFTER_SEND_MS",
            str(DEFAULT_SETTLE_AFTER_SEND_MS),
        )
    )

    return GoogleMessagesSmsConfig(
        profile_dir=profile_dir,
        headless=_bool_from_env(os.getenv("GOOGLE_MESSAGES_HEADLESS"), default=False),
        timeout_ms=timeout_ms,
        settle_after_send_ms=settle_after_send_ms,
        key_type_delay_ms=int(os.getenv("GOOGLE_MESSAGES_KEY_DELAY_MS", "5")),
    )


def normalize_phone_digits(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "")

    if not digits:
        raise GoogleMessagesSmsSenderError("El teléfono destino no tiene dígitos.")

    if len(digits) < 10:
        raise GoogleMessagesSmsSenderError(
            "El teléfono destino parece incompleto para envío SMS."
        )

    return digits


def _wait_for_recipient_option(page: Page, phone_digits: str, timeout_ms: int) -> str:
    candidates = [
        f"Enviar a {phone_digits}",
        f"Send to {phone_digits}",
        phone_digits,
    ]

    last_error: Exception | None = None

    for text in candidates:
        try:
            locator = page.get_by_text(text, exact=False).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return text
        except Exception as exc:
            last_error = exc

    raise GoogleMessagesSmsSenderError(
        f"No se encontró opción de destinatario para {phone_digits}. "
        f"Último error: {last_error}"
    )


def _handle_welcome_gate(page: Page, config: GoogleMessagesSmsConfig) -> bool:
    """
    Google Messages a veces redirige a /welcome antes de entrar a /conversations/new.
    Si aparece la pantalla de bienvenida, intenta continuar con el botón Acceder/Sign in.
    """
    is_welcome_url = "/welcome" in page.url

    visible_access_button = False
    for label in ["Acceder", "Sign in", "Get started"]:
        try:
            if page.get_by_text(label, exact=False).first.is_visible(timeout=1000):
                visible_access_button = True
                break
        except Exception:
            continue

    if not is_welcome_url and not visible_access_button:
        return False

    last_error: Exception | None = None

    for label in ["Acceder", "Sign in", "Get started"]:
        try:
            button = page.get_by_text(label, exact=False).first
            button.wait_for(state="visible", timeout=3000)
            button.click(timeout=config.timeout_ms)

            try:
                page.wait_for_load_state("domcontentloaded", timeout=config.timeout_ms)
            except Exception:
                pass

            page.wait_for_timeout(2500)

            if "/welcome" in page.url:
                page.goto(
                    MESSAGES_NEW_URL,
                    wait_until="domcontentloaded",
                    timeout=config.timeout_ms,
                )
                page.wait_for_timeout(1500)

            return True
        except Exception as exc:
            last_error = exc

    raise GoogleMessagesSmsSenderError(
        f"Google Messages mostró pantalla de bienvenida, "
        f"pero no se pudo continuar. Último error: {last_error}"
    )


def _assert_google_messages_session_ready(page: Page) -> None:
    current_url = page.url or ""

    if "accounts.google.com" in current_url:
        raise GoogleMessagesSmsSenderError(
            "Google Messages requiere iniciar sesión en Google. "
            "No se envió SMS. Reempareja o reactiva la sesión del perfil persistente."
        )

    if "/welcome" in current_url:
        raise GoogleMessagesSmsSenderError(
            "Google Messages sigue en pantalla de bienvenida. "
            "No se envió SMS. Reempareja o reactiva la sesión del perfil persistente."
        )

    if "messages.google.com" not in current_url:
        raise GoogleMessagesSmsSenderError(
            f"Google Messages no está en dominio esperado. URL actual: {current_url}"
        )


def _fill_recipient(page: Page, phone_digits: str, config: GoogleMessagesSmsConfig) -> None:
    recipient_input = page.locator("input[type='text']").first
    recipient_input.wait_for(state="visible", timeout=config.timeout_ms)
    recipient_input.click(timeout=config.timeout_ms)

    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(phone_digits, delay=config.key_type_delay_ms)

    _wait_for_recipient_option(page, phone_digits, config.timeout_ms)


def _wait_until_url_not_contains(page: Page, fragment: str, timeout_ms: int) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_url = page.url

    while time.monotonic() < deadline:
        last_url = page.url
        if fragment not in last_url:
            return

        page.wait_for_timeout(250)

    raise GoogleMessagesSmsSenderError(
        f"Google Messages no cambió de URL después de seleccionar destinatario. URL actual: {last_url}"
    )


def _read_locator_value(locator, timeout_ms: int = 1000) -> str:
    try:
        return locator.input_value(timeout=min(timeout_ms, 1000)) or ""
    except Exception:
        return ""


def _assert_message_box_contains_expected_text(locator, expected: str, timeout_ms: int) -> None:
    current_value = _read_locator_value(locator, timeout_ms=timeout_ms).strip()

    if not current_value:
        raise GoogleMessagesSmsSenderError(
            "Google Messages dejó vacía la caja de mensaje; se cancela envío para evitar SMS vacío."
        )

    if expected not in current_value:
        raise GoogleMessagesSmsSenderError(
            "Google Messages capturó un texto distinto al SMS esperado; se cancela envío."
        )


def _click_send_button_if_available(page: Page, timeout_ms: int) -> bool:
    selectors = [
        "button[aria-label^='Enviar']",
        "button[aria-label*='Enviar']",
        "[role='button'][aria-label^='Enviar']",
        "[role='button'][aria-label*='Enviar']",
        "button[aria-label^='Send']",
        "button[aria-label*='Send']",
        "[role='button'][aria-label^='Send']",
        "[role='button'][aria-label*='Send']",
    ]

    for selector in selectors:
        candidate = page.locator(selector).last

        try:
            if candidate.count() < 1:
                continue

            if not candidate.is_visible(timeout=500):
                continue

            if not candidate.is_enabled(timeout=500):
                continue

            candidate.click(timeout=min(timeout_ms, 3000))
            return True
        except Exception:
            continue

    return False


def _wait_until_locator_value_contains(locator, expected: str, timeout_ms: int) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_value = ""

    while time.monotonic() < deadline:
        try:
            last_value = locator.input_value(timeout=500)
        except Exception:
            last_value = ""

        if expected in last_value:
            return

        time.sleep(0.25)

    raise GoogleMessagesSmsSenderError(
        "Google Messages no confirmó que el texto del SMS quedara capturado en la caja de mensaje."
    )


def _wait_until_locator_empty(locator, timeout_ms: int) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_value = None

    while time.monotonic() < deadline:
        try:
            last_value = locator.input_value(timeout=500)
        except Exception:
            last_value = None

        if last_value == "":
            return

        time.sleep(0.25)

    raise GoogleMessagesSmsSenderError(
        "Google Messages no limpió la caja de mensaje después de presionar Enter."
    )


def _wait_until_body_contains(page: Page, expected: str, timeout_ms: int) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000)
    body = page.locator("body").first
    last_text = ""

    while time.monotonic() < deadline:
        try:
            last_text = body.inner_text(timeout=1000)
        except Exception:
            last_text = ""

        if expected in last_text:
            return

        time.sleep(0.25)

    raise GoogleMessagesSmsSenderError(
        "Google Messages no mostró el mensaje enviado en la conversación después del envío."
    )


def _select_recipient(page: Page, phone_digits: str, config: GoogleMessagesSmsConfig) -> str:
    option_text = _wait_for_recipient_option(page, phone_digits, config.timeout_ms)

    page.get_by_text(option_text, exact=False).first.click(timeout=config.timeout_ms)

    _wait_until_url_not_contains(page, "/conversations/new", config.timeout_ms)

    if "/conversations/new" in page.url:
        raise GoogleMessagesSmsSenderError(
            "Google Messages no entró a la conversación real del destinatario."
        )

    return option_text


def _fill_message(page: Page, message: str, config: GoogleMessagesSmsConfig) -> str:
    if not message or not message.strip():
        raise GoogleMessagesSmsSenderError("El mensaje SMS está vacío.")

    selector = "textarea[aria-label^='Escribir un mensaje']"
    message_box = page.locator(selector).first

    message_box.wait_for(state="visible", timeout=config.timeout_ms)
    message_box.click(timeout=config.timeout_ms)

    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(message, delay=config.key_type_delay_ms)

    _wait_until_locator_value_contains(message_box, message, config.timeout_ms)
    _assert_message_box_contains_expected_text(message_box, message, config.timeout_ms)

    return selector


def _send_by_enter(
    page: Page,
    message_selector: str,
    message: str,
    config: GoogleMessagesSmsConfig,
) -> dict[str, Any]:
    message_box = page.locator(message_selector).first

    message_box.wait_for(state="visible", timeout=config.timeout_ms)
    message_box.click(timeout=config.timeout_ms)

    _assert_message_box_contains_expected_text(message_box, message, config.timeout_ms)

    sent_by_button = _click_send_button_if_available(page, config.timeout_ms)
    if not sent_by_button:
        page.keyboard.press("Enter")

    _wait_until_locator_empty(message_box, config.timeout_ms)

    _wait_until_body_contains(page, message, config.timeout_ms)

    page.wait_for_timeout(config.settle_after_send_ms)

    return {
        "strategy": "keyboard_enter_fallback",
        "evidence": "message_box_cleared_and_message_text_present",
    }


def send_sms_via_google_messages(
    phone: str,
    message: str,
    config: GoogleMessagesSmsConfig | None = None,
) -> dict[str, Any]:
    resolved_config = config or resolve_config_from_env()
    phone_digits = normalize_phone_digits(phone)

    if not resolved_config.profile_dir.exists():
        raise GoogleMessagesSmsSenderError(
            f"No existe perfil Google Messages: {resolved_config.profile_dir}. "
            "Primero se debe emparejar el teléfono."
        )

    started_at = time.perf_counter()
    steps: list[dict[str, Any]] = []

    def measure(label: str, fn):
        step_started_at = time.perf_counter()

        try:
            result = fn()
            ok = True
            return result
        except Exception:
            ok = False
            raise
        finally:
            steps.append(
                {
                    "label": label,
                    "ok": ok,
                    "elapsed_ms": round((time.perf_counter() - step_started_at) * 1000, 2),
                }
            )

    chromium_args = [
        "--disable-notifications",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
    ]

    with sync_playwright() as p:
        context = measure(
            "launch_persistent_chromium",
            lambda: p.chromium.launch_persistent_context(
                user_data_dir=str(resolved_config.profile_dir),
                headless=resolved_config.headless,
                viewport={"width": 1366, "height": 768},
                args=chromium_args,
            ),
        )

        try:
            page = measure("new_page", lambda: context.new_page())

            measure(
                "goto_conversations_new",
                lambda: page.goto(
                    MESSAGES_NEW_URL,
                    wait_until="domcontentloaded",
                    timeout=resolved_config.timeout_ms,
                ),
            )

            measure(
                "handle_welcome_gate",
                lambda: _handle_welcome_gate(page, resolved_config),
            )

            measure(
                "assert_session_ready",
                lambda: _assert_google_messages_session_ready(page),
            )

            measure(
                "fill_recipient",
                lambda: _fill_recipient(page, phone_digits, resolved_config),
            )

            selected_recipient = measure(
                "select_recipient",
                lambda: _select_recipient(page, phone_digits, resolved_config),
            )

            message_selector = measure(
                "fill_message",
                lambda: _fill_message(page, message, resolved_config),
            )

            send_result = measure(
                "send_by_enter",
                lambda: _send_by_enter(
                    page,
                    message_selector,
                    message,
                    resolved_config,
                ),
            )

            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)

            return {
                "ok": True,
                "provider": "google_messages_web",
                "phone_digits": phone_digits,
                "message_length": len(message),
                "selected_recipient": selected_recipient,
                "conversation_url": page.url,
                "headless": resolved_config.headless,
                "elapsed_ms": elapsed_ms,
                "steps": steps,
                **send_result,
            }
        finally:
            measure("close_context", lambda: context.close())
