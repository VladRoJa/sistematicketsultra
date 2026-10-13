"""M5 UI contracts: separate section, no changes to existing Meta KPI basis."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONT = ROOT / "frontend/src/app/marketing-sales-funnel"
BACK = ROOT / "backend/app/services/marketing_sales_funnel_cutoff_service.py"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def test_m5_response_is_a_separate_optional_contract():
    model = _read("marketing-sales-funnel.models.ts")
    assert "google_ads_branch_attribution?: MarketingGoogleAdsBranchAttribution;" in model
    assert "scope_attributed_cost: number | null;" in model
    assert "account_cost_observed?: number;" in model
    assert "unassigned_cost_observed?: number;" in model
    assert "existing_cpl_cpt_cac_basis: 'META_ASSIGNED_ONLY';" in model
    assert "investment?: number | null;" in model


def test_m5_is_separate_from_meta_kpi_and_excel_export():
    ts = _read("marketing-sales-funnel.component.ts")
    html = _read("marketing-sales-funnel.component.html")
    export = _read("marketing-sales-funnel-table-export.ts")
    backend = BACK.read_text(encoding="utf-8")

    assert 'payload["google_ads_branch_attribution"]' in backend
    assert '_attach_google_ads_branch_attribution(' in backend
    assert "this.buildGoogleBranchAttributionView(data)" in ts
    assert "this.dashboard?.summary.investment ?? null" in ts
    assert "this.resolveBranchInvestment(branch.sucursal_id)" in ts
    assert "exportMarketingSalesFunnelBranchTable" in ts
    assert "google_ads_branch_attribution" not in export
    assert "google-branch-attribution" in html
    assert "Google Ads · atribución histórica por sucursal" in ts
    assert "app-marketing-sales-funnel-story" in html


def test_m5_frontend_never_infers_global_amount_for_restricted_view():
    ts = _read("marketing-sales-funnel.component.ts")
    assert "evidence.account_reconciled === true" in ts
    assert "evidence.account_cost_observed !== undefined" in ts
    assert "evidence.unassigned_cost_observed !== undefined" in ts
    assert "accountValue: globallyReconciled" in ts
    assert "unassignedValue: globallyReconciled" in ts
    assert "status: evidence.status" in ts
    assert "evidence.scope_attributed_cost !== null" in ts
    assert "this.formatMoneyPrecise(evidence.scope_attributed_cost)" in ts


def test_m5_html_only_simple_bindings_and_separate_styles():
    ts = _read("marketing-sales-funnel.component.ts")
    html = _read("marketing-sales-funnel.component.html")
    css = _read("marketing-sales-funnel-google-attribution.component.css")
    assert "'./marketing-sales-funnel-google-attribution.component.css'" in ts
    assert "googleBranchAttributionView as attribution" in html
    assert "*ngFor=\"let row of attribution.rows\"" in html
    assert "{{ attribution.scopeValue }}" in html
    assert "{{ row.branch }}" in html
    assert "max-height: 242px" in css
    assert "overflow: auto" in css
    assert "ngStyle" not in html
