# Issue #856 — Centro Operativo Campañas V2: auditoría y hito UI

Estado: EN DESARROLLO. Prohibido interpretar un preview como autorización de envío.

## Auditoría en main al 2026-10-14

Existente backend:
- Configuración de plantillas, 26 channel bindings y tarifas de referencia MXN.
- Política append-only `operational_channel_cap`/`operational_portfolio_cap`, sin exigir remanente Meta.
- Preflight con blacklist, exclusiones, plantillas, variables, presupuesto y capacidad.
- Aprobación + reserva; materialización READY/HELD; confirmación de autorización; execute por child; monitor; conciliación y HELD.
- QA_MANUAL helper/script con preview SHA y freeze por una sucursal/<=10 destinatarios.
- Kill switches de envío reales separados, ambos OFF.

Brechas:
- Los endpoints de aprobación, materialización, autorización, ejecución gobernada y monitor carecen de clientes/flujo de operador en Angular.
- QA_MANUAL no tiene ruta/API/UX de operador protegida por JWT; la prueba #16 nació desde CLI.
- Los catálogos tienen formularios separados y no muestran una matriz de 26 canales.
- No hay evidencia de que el cliente iVentas provea asociación canal → Business Portfolio Meta. La pertenencia (posiblemente tres portafolios) debe corroborarse fuera de Suite o por una integración autorizada de lectura; no inventar IDs.
- La cotización USD→MXN requiere una fuente de tipo de cambio documentada; 0.0542 USD no equivale a una tarifa MXN persistida.
- Los límites Meta se calculan sobre usuarios únicos por ventana a nivel de portafolio; los topes internos de Suite cuentan sus intentos/reservas y **NO** son la misma métrica.

## Entrega A — Matriz (este PR)

Archivos:
- `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2-readiness.logic.ts`: proyección pura de políticas/tarifas más recientes y detección de topes contradictorios.
- `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2-readiness-dialog.component.{ts,html,css}`: tabla compacta de 26, filtros por plantilla, acceso a configuración ya existente.
- `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2-page.component.{ts,html}`: abre el modal con permisos frontend existentes.
- `frontend/src/app/marketing-campaign-v2/marketing-campaign-v2.logic.node-test.ts`: regresiones de matriz y UI sin envío.

No se escribe nada desde la matriz, no hay Alembic ni cambios de permisos. `Completa*` solo significa que el registro interno existe; nunca confirma portafolio Meta, costo realmente facturado o capacidad real de enviar.

## Fases restantes antes del QA live

B. Configuración asistida: contraste canal→portafolio con evidencia externa, fuente y límites internos conservadores; tarifa MXN revisada/confirmada por operador. No inferir la identidad de tres portafolios ni usar un nominal de 100k como saldo.

C. QA_MANUAL en Suite: dos endpoints autenticados y autorizados (preview y freeze); no aceptar actor desde navegador; no logging de teléfono; flujo conservador de 26 campañas de un solo destinatario, nombres únicos y recuperación de un freeze existente. No alterar cohorts comerciales ni excluir blacklist. Preflight de cada campaña. Agregar regresiones de permisos 401/403, TOCTOU y reintentos.

D. Consola gobernada: consume endpoints existentes para preflight, presupuesto, aprobación y reserva, materialización, authorize, ejecución manual por child y monitoreo de estados de proveedor. Cada acción sensible exige confirmación y fingerprints/digests vigentes. No transmitir teléfonos, variables ni credenciales del proveedor desde Angular.

E. CI/QA: integración + Angular + backend/PG aislado + gates negativos de kill switches; revisión de UX en producción con flags OFF; envío canario #16 solo mediante autorización explícita de esa ejecución, seguido 25 bajo control secuencial y sin reenvío ante estados ambiguos.

**No comenzar prueba live antes de B–E.**
