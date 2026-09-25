from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROUTES = REPOSITORY_ROOT / "frontend/src/app/app.routes.ts"
LAYOUT_TS = REPOSITORY_ROOT / "frontend/src/app/layout/layout.component.ts"
ACCESS_GUARD = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-access.guard.ts"
)
COMPONENT_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.ts"
)
COMPONENT_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.html"
)
COMPONENT_CSS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.component.css"
)
SERVICE_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center.service.ts"
)
APPOINTMENT_DIALOG_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-appointment-dialog.component.ts"
)
APPOINTMENT_DIALOG_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-appointment-dialog.component.html"
)
CRM_IMPORT_DIALOG_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-crm-import-dialog.component.ts"
)
CRM_IMPORT_DIALOG_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-crm-import-dialog.component.html"
)
NEW_CONTACT_DIALOG_TS = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-new-contact-dialog.component.ts"
)
NEW_CONTACT_DIALOG_HTML = REPOSITORY_ROOT / (
    "frontend/src/app/contact-center/contact-center-new-contact-dialog.component.html"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contact_center_route_is_guarded_and_lazy_loaded():
    routes = _read(APP_ROUTES)

    assert "path: 'contact-center'" in routes
    assert "canActivate: [contactCenterAccessGuard]" in routes
    assert "import('./contact-center/contact-center.component')" in routes


def test_contact_center_frontend_access_covers_villas_and_costa_bc_managers():
    guard = _read(ACCESS_GUARD)

    assert "'ADMICORP'" in guard
    assert "'SANDRA'" in guard
    assert "'CANDY'" in guard
    assert "CONTACT_CENTER_INITIAL_ROLES" in guard
    assert "CONTACT_CENTER_INITIAL_USERS" in guard
    assert "CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS" in guard
    assert "role === 'GERENTE'" in guard
    assert "CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS.has(branchId)" in guard

    # No abrir el rollout por roles administrativos/globales genéricos.
    assert "'ADMINISTRADOR'" not in guard
    assert "'LECTOR_GLOBAL'" not in guard

    for branch_id in (1, 7, 8, 9, 10, 11, 12, 13):
        assert f"  {branch_id}," in guard


def test_contact_center_menu_waits_for_backend_access_confirmation():
    layout = _read(LAYOUT_TS)

    assert "habilitarContactCenterEnMenuSiAplica" in layout
    assert "canAccessContactCenter(user)" in layout
    assert "/contact-center/access" in layout
    assert "if (!response?.allowed)" in layout


def test_contact_center_v1_keeps_logic_out_of_inline_templates_and_styles():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    component_css = _read(COMPONENT_CSS)

    assert "templateUrl: './contact-center.component.html'" in component_ts
    assert "styleUrls: ['./contact-center.component.css']" in component_ts
    assert "template:" not in component_ts
    assert "styles:" not in component_ts
    assert "<style" not in component_html.lower()
    assert ".cc-page" in component_css


def test_contact_center_v1_exposes_portfolio_crm_and_appointment_calendar():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    service = _read(SERVICE_TS)

    assert "type ContactCenterTab = 'PORTFOLIO' | 'CRM' | 'APPOINTMENTS'" in component_ts
    assert "type AppointmentView = 'TABLE' | 'CALENDAR'" in component_ts
    assert "calendarCells" in component_ts

    assert "{{ portfolioTitle }}" in component_html
    assert "return this.isManager ? 'Mi cartera' : 'Cartera compartida';" in component_ts
    assert "CRM / Funnel" in component_html
    assert "Citas" in component_html
    assert "calendar-grid" in component_html

    assert "getContacts(" in service
    assert "getCrmCandidates(" in service
    assert "getAppointments(" in service
    assert "getReport(" in service

def test_contact_center_hides_new_appointment_when_one_is_active():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "get activeScheduledAppointment()" in component_ts
    assert "row.status === 'SCHEDULED'" in component_ts
    assert "manageActiveAppointment()" in component_ts
    assert "activeCase && canOperateActiveCase && !activeScheduledAppointment" in component_html
    assert "activeAppointmentHelpText" in component_html
    assert "Gestionar cita" in component_html

def test_contact_center_manager_ui_has_mini_portfolio_crm_and_appointments():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "get isManager()" in component_ts
    assert "this.activeTab = tab" in component_ts
    assert "this.activeTab = 'APPOINTMENTS'" not in component_ts
    assert "if (this.isManager && tab !== 'APPOINTMENTS')" not in component_ts
    assert "return this.isManager ? 'Mi cartera' : 'Cartera compartida';" in component_ts
    assert "return 'Asignados a mí';" in component_ts
    assert "CRM / Funnel" in component_html
    assert "Citas" in component_html
    assert "Gerente" in component_html
    assert "Validar compra" in component_html

def test_contact_center_crm_phone_search_is_global_not_month_scoped():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    service = _read(SERVICE_TS)

    assert "crmPhoneSearch" in component_ts
    assert "searchCrmByPhone()" in component_ts
    assert "crmSearchMode: 'MONTH' | 'PHONE'" in component_ts
    assert "Buscar teléfono · todo el histórico" in component_html
    assert "La búsqueda por teléfono revisa todo el histórico." in component_html
    assert "(keyup.enter)=\"searchCrmByPhone()\"" in component_html

    assert "phone?: string" in service
    assert "if (phone?.trim())" in service
    assert "params = params.set('phone', phone.trim())" in service
    assert "else {" in service
    assert "params = params.set('month', month)" in service

def test_contact_center_portfolio_can_filter_closed_contacts():
    component_html = _read(COMPONENT_HTML)

    assert '<option value="CLOSED">Cerrado</option>' in component_html
    assert "{{ contacts.length }} contactos</p>" in component_html
    assert "{{ contacts.length }} contactos activos</p>" not in component_html

def test_contact_center_calendar_history_and_foreign_cases_are_read_only():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "appointment.status !== 'SCHEDULED'" in component_ts
    assert "!this.canOperateAppointment(appointment)" in component_ts
    assert "!canOperateAppointment(appointment)" in component_html
    assert "[disabled]=" in component_html
    assert "[class.calendar-event--readonly]=" in component_html

def test_contact_center_manager_cannot_reschedule_from_dialog():
    component_ts = _read(COMPONENT_TS)
    dialog_ts = _read(APPOINTMENT_DIALOG_TS)
    dialog_html = _read(APPOINTMENT_DIALOG_HTML)

    assert "canReschedule: !this.isManager" in component_ts
    assert "canReschedule: boolean" in dialog_ts
    assert "if (!this.data.canReschedule)" in dialog_ts
    assert '*ngIf="data.canReschedule"' in dialog_html
    assert "*ngIf=\"action === 'RESCHEDULE' && data.canReschedule\"" in dialog_html
    assert "isManager ? 'Registrar resultado' : 'Cerrar / reagendar'" in component_html

def test_contact_center_crm_add_confirms_name_before_import():
    component_ts = _read(COMPONENT_TS)
    dialog_ts = _read(CRM_IMPORT_DIALOG_TS)
    dialog_html = _read(CRM_IMPORT_DIALOG_HTML)
    service = _read(SERVICE_TS)

    assert "ContactCenterCrmImportDialogComponent" in component_ts
    assert "if (row.already_in_contact_center)" in component_ts
    assert "displayName" in component_ts
    assert "display_name?: string" in service
    assert "payload.display_name = displayName.trim()" in service

    assert "Nombre en cartera *" in dialog_html
    assert "maxlength=\"255\"" in dialog_html
    assert "Agregar a cartera" in dialog_html
    assert "this.displayName = String(data.candidate.name || '').trim()" in dialog_ts


def test_contact_center_crm_keeps_single_phone_search_control():
    component_html = _read(COMPONENT_HTML)

    assert "(keyup.enter)=\"searchCrmByPhone()\"" in component_html
    assert "(click)=\"searchCrmByPhone()\"" not in component_html
    assert "Enter para buscar" in component_html

def test_contact_center_shared_operator_view_is_read_only_for_foreign_cases():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    component_css = _read(COMPONENT_CSS)

    assert "get canOperateActiveCase()" in component_ts
    assert "return 'Vista compartida';" in component_ts
    assert "showPortfolioAgentColumn" in component_ts
    assert "activeCase && !canOperateActiveCase" in component_html
    assert "Solo lectura · asignado a" in component_html
    assert "activeCase && canOperateActiveCase" in component_html
    assert ".detail-readonly" in component_css


def test_contact_center_manager_crm_does_not_take_foreign_active_case():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "active_case_assigned_user_id" in component_ts
    assert "return 'En atención';" in component_ts
    assert "crmActionDisabled(row)" in component_ts
    assert '[disabled]="crmActionDisabled(row)"' in component_html


def test_contact_center_shared_appointments_only_show_actions_when_allowed():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "canOperateAppointment(" in component_ts
    assert "appointment.case?.assigned_user?.id === this.access.user.id" in component_ts
    assert "&& canOperateAppointment(appointment)" in component_html
    assert "appointment.purchase_reported" in component_html

def test_contact_center_manager_can_create_manual_contact_with_required_branch():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    dialog_ts = _read(NEW_CONTACT_DIALOG_TS)
    dialog_html = _read(NEW_CONTACT_DIALOG_HTML)

    assert "if (!this.access || this.isManager)" not in component_ts
    assert "isManager: this.isManager" in component_ts
    assert '(click)="openNewContact()"' in component_html

    assert "isManager: boolean" in dialog_ts
    assert "this.data.isManager && !this.sucursalId" in dialog_ts
    assert "Selecciona una sucursal." in dialog_ts
    assert "data.isManager ? ' *' : ''" in dialog_html


def test_contact_center_crm_exposes_phone_reconciliation_states():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "crmStatusLabel(row" in component_ts
    assert "return 'Revisar coincidencia';" in component_ts
    assert "'Ya en cartera'" in component_ts
    assert "if (row.phone_match_ambiguous)" in component_ts
    assert "{{ crmStatusLabel(row) }}" in component_html
    assert "row.phone_match_ambiguous" in component_html

def test_contact_center_closed_appointment_has_explicit_result_correction_flow():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)
    dialog_ts = _read(APPOINTMENT_DIALOG_TS)
    dialog_html = _read(APPOINTMENT_DIALOG_HTML)
    service = _read(SERVICE_TS)

    assert "canCorrectAppointment(" in component_ts
    assert "correctAppointmentResult(" in component_ts
    assert "appointment.purchase_verification_status !== 'VERIFIED'" in component_ts
    assert "correctionMode: true" in component_ts

    assert "Corregir resultado" in component_html
    assert '(click)="correctAppointmentResult(appointment)"' in component_html

    assert "correctionMode?: boolean" in dialog_ts
    assert "'CORRECT_RESULT'" in dialog_ts
    assert "Guardar corrección" in dialog_ts
    assert "El cambio quedará registrado en el historial de la cita." in dialog_html
    assert '*ngIf="!data.correctionMode"' in dialog_html

    assert "correctAppointmentResult(" in service
    assert "/correct-result" in service


def test_contact_center_calendar_history_remains_read_only_despite_table_correction():
    component_ts = _read(COMPONENT_TS)
    component_html = _read(COMPONENT_HTML)

    assert "appointment.status !== 'SCHEDULED'" in component_ts
    assert "[class.calendar-event--readonly]=" in component_html
    assert "[disabled]=" in component_html
    assert "(click)=\"appointmentAction(appointment)\"" in component_html

