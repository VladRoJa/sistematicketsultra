"""Drive the iVentas template editor through its public browser interface."""

import re
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.integrations.iventas.template_inventory import evaluate_template_coverage, parse_template_inventory


ORIGIN = "https://app.iventas.com"
_CATEGORY_TEXT = {
    "MARKETING": "Avisos, marketing y promociones",
    "UTILITY": "Actualización de estatus de un evento o transacción",
}
_CATEGORY_LABEL = {"MARKETING": "Marketing", "UTILITY": "Utilidad"}
_MULTIMEDIA = "¿Quieres agregar multimedia a tu mensaje?"
_NAME_PROMPT = "Para terminar, dale un nombre a tu plantilla"
_SEARCH_PLACEHOLDER = re.compile(r"^Buscar plantillas", re.I)
_EMPTY_INVENTORY = re.compile(r"sin plantillas|no (hay|se encontraron) (plantillas|resultados)", re.I)


class TemplateBrowserError(RuntimeError):
    pass


def _require_iventas_url(page) -> None:
    current = urlsplit(page.url)
    if (current.scheme, current.netloc) != ("https", "app.iventas.com"):
        raise TemplateBrowserError("El navegador salió del dominio de iVentas.")


def _continue(page) -> None:
    page.get_by_role("button", name="Continuar", exact=True).click()


def _select_category(page, category, multimedia) -> None:
    try:
        category.or_(multimedia).filter(visible=True).first.wait_for()
        if multimedia.is_visible() and not category.is_visible():
            # iVentas can open multimedia first and expose the category only when going back.
            page.get_by_text("Regresar", exact=True).click()
        category.click()
    except PlaywrightTimeoutError:
        raise TemplateBrowserError("iVentas no mostró la categoría solicitada para esta plantilla.") from None
    _continue(page)


def _select_editor_text(editor, field: dict) -> None:
    selected = editor.evaluate(
        """(node, { start, end }) => {
            const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
            const range = document.createRange();
            let offset = 0;
            let startFound = false;
            for (let text = walker.nextNode(); text; text = walker.nextNode()) {
                const nextOffset = offset + text.length;
                if (!startFound && start < nextOffset) {
                    range.setStart(text, start - offset);
                    startFound = true;
                }
                if (startFound && end <= nextOffset) {
                    range.setEnd(text, end - offset);
                    node.focus();
                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                    document.dispatchEvent(new Event('selectionchange'));
                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    return range.toString();
                }
                offset = nextOffset;
            }
            return null;
        }""",
        {"start": field["start"], "end": field["end"]},
    )
    if selected != field["example"]:
        raise TemplateBrowserError("El editor no conservó la selección del campo personalizado.")


def _open_inventory(page) -> None:
    page.goto(f"{ORIGIN}/config", wait_until="domcontentloaded")
    _require_iventas_url(page)
    page.get_by_text("Plantillas de WhatsApp", exact=True).wait_for()
    # Search is visible during loading. Wait for inventory or its empty state.
    page.get_by_text(re.compile(r"^nombre$", re.I)).or_(
        page.get_by_text(_EMPTY_INVENTORY)
    ).first.wait_for()


def _login(page, login) -> None:
    page.set_default_timeout(12_000)
    page.goto(f"{ORIGIN}/login", wait_until="domcontentloaded")
    _require_iventas_url(page)
    page.locator('input[type="email"]:visible').or_(
        page.get_by_label(re.compile(r"correo electrónico", re.I))
    ).fill(login.email)
    page.locator('input[type="password"]:visible').fill(login.password)
    page.get_by_role("button", name="Iniciar Sesión", exact=True).click()
    try:
        page.get_by_text("Configuración", exact=True).first.wait_for()
    except PlaywrightError:
        raise TemplateBrowserError("iVentas no confirmó el inicio de sesión de esta sucursal.") from None


def _inventory_response(response):
    url = urlsplit(response.url)
    domain = url.hostname or ""
    inventory_domain = domain in {"iventas.com", "iventas.ai", "rest.iventas.mx"} or domain.endswith(
        (".iventas.com", ".iventas.ai")
    )
    return (
        response.ok and response.request.method == "GET" and url.scheme == "https" and inventory_domain
        and "whatsapptemplate" in url.path.casefold().split("/")
    )




def _open_inventory_for_read(page) -> None:
    """Read-only: wait for authenticated provider inventory, not a UI heading.

    iVentas can render its /config page after the inventory GET has completed.
    The existing checked response predicate and strict JSON parser remain the
    source of approval evidence; a missing response must fail closed.
    """
    try:
        with page.expect_response(_inventory_response, timeout=30_000):
            page.goto(f"{ORIGIN}/config", wait_until="domcontentloaded")
            _require_iventas_url(page)
    except PlaywrightTimeoutError:
        raise TemplateBrowserError(
            "iVentas no devolvió el inventario de plantillas dentro de 30 segundos."
        ) from None



def read_template_inventory(browser, login):
    """Inspect existing templates in one authenticated session, without POSTs.

    Return only validated name/channel/status records. Absent inventory and
    conflicting provider observations fail closed instead of guessing approval.
    """
    context = browser.new_context()
    try:
        page = context.new_page()
        _login(page, login)
        responses = []
        page.on("response", lambda response: responses.append(response)
                if _inventory_response(response) else None)
        _open_inventory_for_read(page)
        if not responses:
            raise TemplateBrowserError("iVentas no devolvió el inventario de plantillas.")
        found = {}
        for response in responses:
            try:
                inventory = parse_template_inventory(response.json())
            except (ValueError, TypeError, PlaywrightError) as exc:
                raise TemplateBrowserError("No fue posible validar el inventario de iVentas.") from exc
            for record in inventory:
                key = (record.template_name.casefold(), record.channel_id)
                previous = found.get(key)
                if previous is not None and previous != record:
                    raise TemplateBrowserError("iVentas devolvió estados de plantilla contradictorios.")
                found[key] = record
        if not found:
            raise TemplateBrowserError("El inventario de iVentas está vacío o no verificable.")
        return tuple(sorted(found.values(), key=lambda r: (r.template_name, r.channel_id)))
    finally:
        try:
            context.close()
        except PlaywrightError:
            pass



def read_template_approval(browser, login, template: dict, channel_id: str) -> tuple[str, str]:
    """Read the authenticated portal inventory without creating or sending anything."""
    context = browser.new_context()
    try:
        page = context.new_page()
        _login(page, login)
        responses = []

        def collect(response):
            if _inventory_response(response):
                responses.append(response)

        page.on("response", collect)
        _open_inventory(page)
        page.get_by_placeholder(_SEARCH_PLACEHOLDER).fill(template["name"])
        row = page.get_by_role("row").filter(
            has=page.get_by_text(template["name"], exact=True),
        ).filter(has=page.get_by_text(_CATEGORY_LABEL[template["category"]], exact=True))
        row.first.wait_for()

        states = set()
        for response in responses:
            try:
                inventory = parse_template_inventory(response.json())
                coverage = evaluate_template_coverage(
                    inventory=inventory, expected_channel_ids=[channel_id], template_names=[template["name"]],
                )
            except (ValueError, PlaywrightError):
                continue
            state = coverage[template["name"]][channel_id]
            if state != "not_observed":
                states.add(state)
        if states == {"accepted"} and row.get_by_text("Aprobada", exact=True).first.is_visible():
            return "APPROVED", "Aprobada por iVentas para este canal."
        if states == {"rejected"} and row.get_by_text("Rechazada", exact=True).first.is_visible():
            return "REJECTED", "iVentas rechazó la plantilla en este canal."
        if row.get_by_text("En revisión", exact=True).first.is_visible():
            return "IN_REVIEW", "Pendiente de aprobación en iVentas."
        return "IN_REVIEW", "A la espera de confirmar el estado en el canal emisor."
    except (PlaywrightError, TemplateBrowserError):
        return "IN_REVIEW", "No se pudo verificar el estado. La Suite volverá a consultar iVentas."
    finally:
        try:
            context.close()
        except PlaywrightError:
            pass


def upload_template(browser, login, template: dict, image: bytes | None, image_type: str | None) -> tuple[str, str]:
    """Use a fresh browser context for a single account and a single submission."""
    context = browser.new_context()
    save_attempted = False
    try:
        page = context.new_page()
        _login(page, login)
        _open_inventory(page)
        if page.get_by_text(template["name"], exact=True).first.is_visible():
            return "EXISTS", "La plantilla ya existe en esta cuenta. Consulta el catálogo para vincularla."
        # Inventory search also resolves templates outside the first visible page.
        search = page.get_by_placeholder(_SEARCH_PLACEHOLDER)
        search.fill(template["name"])
        match = page.get_by_text(template["name"], exact=True)
        empty_result = page.get_by_text(_EMPTY_INVENTORY)
        empty_result.or_(match).first.wait_for()
        if match.first.is_visible():
            return "EXISTS", "La plantilla ya existe en esta cuenta. Consulta el catálogo para vincularla."

        page.get_by_text(re.compile(r"^\+?\s*Crear Plantilla$", re.I)).click()
        fields = template["fields"]
        template_type = "Plantilla con campos personalizables" if fields else "Plantilla simple"
        page.get_by_text(template_type, exact=True).click()
        editor = page.locator('[contenteditable="true"]:visible, textarea:visible')
        editor.fill(template["message"])
        for field in reversed(fields):
            _select_editor_text(editor, field)
            create_field = page.get_by_text("Crear campo", exact=True)
            create_field.click()
            create_field.wait_for(state="hidden")
            editor.get_by_text(field["example"], exact=True).last.wait_for()

        _continue(page)
        category = page.get_by_text(_CATEGORY_TEXT[template["category"]], exact=True)
        multimedia = page.get_by_text(_MULTIMEDIA, exact=True)
        if fields and editor.is_visible() and not category.is_visible() and not multimedia.is_visible():
            _continue(page)
        _select_category(page, category, multimedia)

        multimedia.wait_for()
        if image is None:
            page.get_by_text("No, gracias.", exact=True).click()
        else:
            page.get_by_text("Sí, quiero agregar multimedia.", exact=True).click()
            name = "plantilla.png" if image_type == "image/png" else "plantilla.jpg"
            page.locator('input[type="file"]').set_input_files(
                {"name": name, "mimeType": image_type, "buffer": image}
            )
            if not page.get_by_text("Botones (opcional)", exact=True).is_visible():
                _continue(page)

        page.get_by_text("Botones (opcional)", exact=True).wait_for()
        text_buttons = page.locator('input:visible:not([type]), input[type="text"]:visible')
        for label in template["buttons"]:
            count = text_buttons.count()
            page.get_by_text("Agregar botón", exact=True).click()
            text_buttons.nth(count).fill(label)
        _continue(page)
        page.get_by_text(_NAME_PROMPT, exact=True).wait_for()
        name_input = page.get_by_role("textbox")
        name_input.fill(template["name"])
        _require_iventas_url(page)
        save_attempted = True
        _continue(page)

        page.get_by_text("Plantillas de WhatsApp", exact=True).wait_for()
        saved = page.get_by_text(template["name"], exact=True)
        saved.wait_for()
        row = saved.locator("xpath=ancestor::tr[1]")
        if row.get_by_text(_CATEGORY_LABEL[template["category"]], exact=True).is_visible():
            for state in ("En revisión", "Aprobada"):
                if row.get_by_text(state, exact=True).is_visible():
                    result = "IN_REVIEW" if template.get("catalog") else "SUBMITTED"
                    return result, f"Estado en iVentas: {state}."
        return "VERIFY", "La plantilla aparece en iVentas. Verifica su categoría y estado."
    except TemplateBrowserError as error:
        return "VERIFY" if save_attempted else "ERROR", str(error)
    except PlaywrightError:
        if save_attempted:
            return "VERIFY", "No se pudo confirmar el guardado. Consulta iVentas antes de repetir la carga."
        return "ERROR", "iVentas no mostró el paso esperado antes de guardar."
    finally:
        try:
            context.close()
        except PlaywrightError:
            pass
