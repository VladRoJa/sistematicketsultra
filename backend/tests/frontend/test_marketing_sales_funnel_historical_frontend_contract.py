from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FUNNEL_DIR = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "app"
    / "marketing-sales-funnel"
)


def _read(name: str) -> str:
    return (FUNNEL_DIR / name).read_text(encoding="utf-8")


def test_historical_funnel_models_allow_unavailable_crm_metrics():
    source = _read("marketing-sales-funnel.models.ts")

    for contract in (
        "leads_meta: number | null;",
        "visits_iventas: number | null;",
        "visits_not_iventas: number | null;",
        "sales_iventas: number | null;",
        "sales_not_iventas: number | null;",
        "sales_digital: number | null;",
        "crm_history_available?: boolean;",
        "match_mode: string | null;",
        "visit_conversion_cohort_complete?: boolean | null;",
    ):
        assert contract in source


def test_both_funnels_offer_months_from_january_2026_and_render_null_as_dash():
    for name in (
        "marketing-sales-funnel.component.ts",
        "marketing-sales-funnel-original.component.ts",
    ):
        source = _read(name)

        assert "const firstMonth = new Date(2026, 0, 1);" in source
        assert "const firstMonth = new Date(2026, 6, 1);" not in source
        assert (
            "formatInteger(value: number | null | undefined): string"
            in source
        )
        assert "return '—';" in source
        assert "private safeRatio(" in source


def test_both_funnel_stories_do_not_fake_missing_crm_history():
    for name in (
        "marketing-sales-funnel-story.component.ts",
        "marketing-sales-funnel-original-story.component.ts",
    ):
        source = _read(name)

        assert (
            "Sin histórico CRM disponible para este periodo"
            in source
        )
        assert (
            "formatInteger(value: number | null | undefined): string"
            in source
        )
        assert "metric: value === null ? '' : metric" in source
        assert "summary.sales_digital === null" in source
        assert "return [];" in source
