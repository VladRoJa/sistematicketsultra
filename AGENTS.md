# Suite Ultra — Project Instructions

## Project context

Suite Ultra is an internal operations and BI platform built with:

- Frontend: Angular, Angular Material and standalone components.
- Backend: Flask, Python, SQLAlchemy and Alembic.
- Database: PostgreSQL.
- Authentication: JWT.
- Deployment: Docker Compose.
- Business timezone: America/Tijuana.

Main modules:

- Tickets
- Inventario
- Mantenimiento Preventivo
- Warehouse
- Track / BI

## Working method

- Work step by step.
- Perform only one logical change or test at a time.
- Before modifying code, state:
  1. File or files involved.
  2. Function, method or component involved.
  3. Exact objective.
  4. Reason for the change.
- If the observed symptom changes, stop and analyze before continuing.
- Do not introduce hacks, silent fallbacks or speculative fixes.
- Do not perform unrelated refactors.
- Prefer the smallest correct change that satisfies the approved scope.
- Do not invent business rules, formulas, permissions or API fields.
- Inspect and confirm the current implementation before proposing changes.

## Investigation mode

When asked to investigate:

- Do not modify files.
- Trace the complete flow through routes, services, models and components.
- Distinguish confirmed findings from hypotheses.
- Verify conclusions against the source code.
- Report exact file paths, functions and relevant relationships.
- Do not convert exploratory findings directly into production code without approval.

## Angular frontend

- Keep components separated into `.ts`, `.html` and `.css` files.
- Do not use inline templates or inline styles.
- Business logic and presentation logic belong in `.ts`.
- HTML must contain only visual structure, simple bindings and calls to existing properties or methods.
- Reuse existing domain services and `environment.apiUrl`.
- Do not duplicate API access logic inside components.
- Respect standalone component patterns already used by the project.
- Preserve hash routing using `/#/ruta`.
- Review `frontend/src/app/app.routes.ts` before adding routes.
- Review `frontend/src/app/layout/layout.component.ts` before adding menu entries.
- Do not assume hiding a menu grants or removes authorization.
- Avoid generic AI-generated SaaS styling.
- Do not abuse cards, gradients, pills, large border radii, decorative shadows or excessive empty space.
- Suite Ultra is a dense internal operations and BI tool, not a marketing landing page.
- Reuse existing visual patterns and shared components before creating new ones.
- Maintain accessibility, responsive behavior and clear information hierarchy.

## Authentication and permissions

- The backend is the real source of authorization.
- Frontend guards and hidden menus only guide the user interface.
- Every protected operation must be validated by the backend.
- Review existing JWT claims, decorators and domain-specific checks before adding permission logic.
- Do not weaken existing permission checks.
- Pay special attention to:
  - role
  - sucursal_id
  - sucursales_ids
  - department_id
- Be cautious of duplicated token sources between:
  - AuthService
  - SessionService
  - localStorage
  - auth.interceptor
  - jwt.interceptor

## Flask backend

- Use the application factory in `backend/app/__init__.py`.
- Register routes through blueprints under `/api`.
- Follow existing route, service, repository and model boundaries.
- Keep HTTP contracts backward compatible unless a contract change is explicitly approved.
- Do not place long-running jobs in web requests when they could block Gunicorn workers.
- Preserve useful error handling and explicit HTTP status codes.
- Do not expose secrets, tokens, credentials or sensitive internal details.

## Database and migrations

- PostgreSQL is the target database.
- Every schema change requires an Alembic migration.
- Never rely only on an ORM model change.
- Migrations must include a valid upgrade and downgrade when practical.
- Do not execute migrations against production without explicit authorization.
- Do not run destructive SQL, deletes, truncates or data rewrites without explicit approval.
- Preserve data traceability and existing historical records.

## Warehouse

Follow the principle:

`raw first, structured later`

Preserve:

- upload metadata
- hashes
- report_type_key
- business_date
- snapshot_kind
- is_canonical
- audit history
- idempotency

Before changing Warehouse calculations or ingestion:

- Verify the selected upload.
- Verify canonicality.
- Verify business dates and cutoff dates.
- Verify duplicate handling.
- Verify row counts.
- Verify report and branch aliases.

Do not blame calculations before validating source selection and canonical snapshots.

## Track / BI

- Track builds a daily mart by branch.
- Preserve versioning, snapshot selection and canonicality.
- Verify aliases and source families before modifying calculations.
- Do not invent forecasting, KPI or alert formulas.
- Treat backend calculation contracts as the source of truth.
- Keep Tendencias, Forecast and Alertas Inteligentes as separate functional concerns unless an approved contract joins them.
- Jobs and schedulers must clean database sessions correctly.
- Do not move long-running scheduler work into the web backend.

## Testing and validation

- Run the smallest relevant test first.
- Do not run the entire test suite unless necessary or requested.
- Report every command executed.
- Report the actual result of each validation.
- Never claim a test passed if it was not executed.
- Clearly identify:
  - tests passed
  - tests failed
  - tests not available
  - validations still pending
- After modifying code, show a concise diff summary.
- Recheck `git status --short` before finishing.

## Git and deployment

- Do not work directly on `main`.
- Do not commit, push, merge, create a pull request or deploy unless explicitly requested.
- Do not edit production files manually.
- Correct deployment flow:
  1. Local change.
  2. Commit.
  3. Push branch.
  4. Pull request and merge.
  5. Server `git pull`.
  6. Rebuild the affected Docker service.
  7. Run migrations only when applicable and approved.

## Safety

Without explicit authorization, do not:

- Connect to production.
- Modify production data.
- Run migrations.
- Send emails or notifications.
- Execute destructive commands.
- Change secrets or environment files.
- Disable authentication or permissions.
- Install unrelated dependencies.
- Replace working architecture with a new framework.

When uncertain, stop and report the uncertainty instead of guessing.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
