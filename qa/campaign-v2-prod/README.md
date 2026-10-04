# Campaign V2 production SAFE smoke

Browser smoke suite for the deployed Campaign V2 Phase 2.

## Safety boundary

SAFE mode permits only:

- GET/HEAD under `/api/marketing/campaigns-v2/**`
- POST `/api/marketing/campaigns-v2/preview`
- POST `/api/marketing/campaigns-v2/preview-detail`

Any other Campaign V2 mutation is aborted by Playwright before leaving the browser. SAFE mode cannot Freeze a campaign, update purpose, or classify tariffs.

## Install browser once

```bash
npm run qa:campaign-v2:install
```

## Authenticate without storing a password in Git

Recommended:

```bash
npm run qa:campaign-v2:auth
```

A Chromium window opens against `https://suiteultragym.com` with `admicorp` prefilled. Complete login manually. Playwright stores the resulting browser state only in:

```text
artifacts/campaign-v2-prod/auth.json
```

`artifacts/` is ignored by Git. Treat that file as sensitive because it contains an authenticated browser session.

Alternative: provide these environment variables at runtime:

```text
SUITE_ULTRA_BASE_URL=https://suiteultragym.com
SUITE_ULTRA_QA_USERNAME=...
SUITE_ULTRA_QA_PASSWORD=...
```

## Optional deterministic QA inputs

```text
SUITE_ULTRA_QA_EXPIRED_FROM=YYYY-MM-DD
SUITE_ULTRA_QA_EXPIRED_TO=YYYY-MM-DD
SUITE_ULTRA_QA_FUNNEL_MONTH=YYYY-MM
```

Without explicit expired-member dates, SAFE smoke uses the 90-day period ending yesterday.
Without an explicit Funnel month, it uses the previous calendar month and waits for Suite to resolve a complete cutoff.

## Run

```bash
npm run qa:campaign-v2:safe
```

Artifacts:

```text
artifacts/campaign-v2-prod/
  auth.json
  screenshots/
  test-results/
  playwright-report/
```

## Current SAFE flows

- F1: Expired members Preview with Domiciliado + Trimestral, no Freeze.
- F2: Expired members Preview with all selectable commercial families.
- F3: Active members Preview and source-specific form behavior.
- F4: Funnel Preview with a complete cutoff, including buyer/active-member suppression metrics.
- F5: Historical Targeting INCLUDE + ALL with VIEWED + button interaction.
- F6: Historical Targeting EXCLUDE + ANY with VIEWED + FAILED.
- F8: Consolidated Reporting, WITHOUT_SNAPSHOT filter, Excel download and five-sheet validation; empty reporting is a valid state.

The suite intentionally does not implement WRITE_QA/Freeze yet. Individual Reporting and non-empty consolidated KPI parity require at least one controlled frozen QA campaign.
