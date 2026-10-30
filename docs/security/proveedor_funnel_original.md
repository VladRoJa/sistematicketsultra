# Proveedor exclusivo de Funnel Original

El rol `PROVEEDOR_FUNNEL_ORIGINAL` usa `users.rol`, el login/JWT existente y las asignaciones de `usuario_sucursal`. No añade tablas, columnas, grants observacionales ni migraciones. No crea ni modifica cuentas o asignaciones automáticamente.

## Alta y alcance

Un administrador autorizado puede elegir el nuevo rol en la pantalla existente de alta de usuarios. Debe asignar únicamente las sucursales aprobadas mediante la administración existente de sucursales del usuario. La sucursal primaria y los IDs corporativos no conceden acceso implícito. Sin asignaciones explícitas, el Funnel responde 403.

No se definió un conjunto de sucursales para iVentas en este cambio: esa aprobación sigue siendo necesaria para provisionar la cuenta real.

## Frontera de autorización

`register_funnel_provider_guard()` se registra en `create_app()` antes de los demás controles de negocio. Para un JWT válido consulta el usuario persistido; no confía en el rol o sucursales del JWT para ampliar permisos. Un cambio del rol efectivo a proveedor restringe incluso tokens anteriores con claims administrativos.

Lista permitida por método y endpoint:

- POST `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout`.
- GET `/api/auth/session-info`.
- GET `/api/marketing/sales-funnel`, exclusivamente con `visit_mode=registered_only`.

El Funnel sólo admite los parámetros `month`, `visit_mode`, `branch_ids`, `cutoff_date` y `cutoff_policy`, sin parámetros repetidos. El resolver existente valida los filtros contra las sucursales asignadas. Los preflight OPTIONS continúan sin JWT y no entregan datos.

Cualquier otro endpoint/método con el JWT del proveedor responde 403, incluso rutas futuras y rutas que sólo requieren `jwt_required()`. Login, refresh y logout mantienen su autenticación propia por contraseña/cookie y los controles existentes de origen. No se añaden excepciones por nombre de usuario.

La respuesta del dashboard conserva los agregados por sucursal, filtros y cortes del contrato existente. Los endpoints de detalle individual y su exportación permanecen denegados para evitar nombres, teléfonos, PIN, folios y otros datos personales.

## Interfaz y exportación

El login navega a `/#/marketing-conversion/venta-total-original`. Un guard padre cubre también rutas fuera del layout y navegación directa. El menú muestra Original y cierre de sesión; no inicia descubrimiento de otros módulos, alertas de tickets/automatización, revisión diaria ni el widget de campañas en segundo plano. Los controles de sesión e inactividad se conservan.

El proveedor descarga el Excel existente de la tabla visible, generado localmente sólo con las filas del dashboard autorizado. No consulta endpoints de exportación ni descarga detalles individuales. La exportación histórica semanal de ADMICORP se conserva sin cambios; incluso un proveedor llamado ADMICORP utiliza únicamente la exportación de filas visibles.

## Validación reproducible

Desde `backend`:

```powershell
../.venv/Scripts/python.exe -m pytest tests/marketing/test_funnel_provider_access.py tests/marketing/test_marketing_access.py tests/marketing/test_marketing_sales_funnel_routes.py tests/marketing/test_marketing_sales_funnel_weekly_export.py -q
```

Desde `frontend`:

```powershell
node --test tests/funnel-provider-access.test.cjs tests/auth-session-activity.test.cjs tests/auth-refresh-coordinator.test.cjs
node node_modules/@angular/cli/bin/ng.js build --optimization=false --source-map=false
node tests/funnel-provider-browser-e2e.cjs
```

Las pruebas Flask usan JWT firmados, el registro real de rutas de `create_app()` y usuarios/repositorios simulados, sin consultar una base externa. El test recorre todas las operaciones registradas ajenas a la lista permitida. Chromium carga Angular compilado con respuestas HTTP sintéticas y lee el XLSX real descargado para verificar las filas autorizadas. Esta evidencia no sustituye la aceptación con la cuenta y los datos reales antes del despliegue.

## Registro de ejecución

- Investigación: `git status --short`, `git branch --show-current`, `git remote -v`, `git log`, `rg --files`, búsquedas `rg -n`, `Get-Content`, `Test-Path` y `Get-ChildItem` sobre autenticación, permisos, rutas, componentes, configuración de pruebas y exportadores. `graphify query "How do authentication, user roles and branch permissions authorize the Original marketing sales funnel and its exports?"` ejecutado antes de investigar código.
- Algunas búsquedas iniciales con comodines dentro de rutas de `rg` no fueron válidas en Windows; se sustituyeron por archivos concretos o búsquedas sobre directorios. No existe `backend/tests/conftest.py`; el bootstrap usado es `backend/tests/marketing/conftest.py`.
- El primer pytest desde la raíz falló en colección (`No module named app`). Repetido desde `backend`: 10 pruebas nuevas pasaron. Regresiones específicas: 17 pruebas existentes pasaron.
- `node --test tests/funnel-provider-access.test.cjs`: 4 pruebas pasaron. Con los dos archivos existentes de autenticación: 17 pruebas pasaron.
- `npm run build -- --configuration development` falló por transmisión de argumentos. `npm run build -- --configuration=development` arrancó sin transmitir la configuración y se interrumpió en preparación. Se sustituyó por invocación directa de Angular CLI; el intento dentro del sandbox también se interrumpió sin completar.
- Git: creación de `codex/proveedor-funnel-original`, `git fetch origin main`, commit de implementación y `git rebase --onto origin/main f4b6e83f`. Se resolvió el conflicto del layout conservando el widget de campañas para usuarios existentes y excluyéndolo para el proveedor. Los archivos preexistentes de `backend/runtime/` no forman parte del cambio.

## Resultados sobre `main` actualizado

- Backend: **33 passed, 1 failed**. Las 11 pruebas nuevas del proveedor pasan. El fallo es `test_linked_period_filters_show_effective_dates_and_custom_inputs`, que espera el atributo XML `errorStyle="stop"` en F4/K4 del Excel semanal de ADMICORP; el XML generado no contiene ese atributo.
- El fallo se reprodujo con `../.venv/Scripts/python.exe -m pytest tests/marketing/test_marketing_sales_funnel_weekly_export.py::test_linked_period_filters_show_effective_dates_and_custom_inputs -q`. La comparación `git diff --exit-code origin/main -- backend/app/services/marketing_sales_funnel_weekly_export_service.py backend/tests/marketing/test_marketing_sales_funnel_weekly_export.py` desde la raíz no muestra cambios. Tampoco hay cambios en `marketing_sales_funnel_original_sheet_service.py`. La prueba importa esos generadores directamente, sin cargar la autenticación modificada. Es un fallo preexistente reproducible en este entorno, fuera del alcance del perfil.
- Frontend: **17 pruebas pasaron**, repetidas después del rebase.
- Angular: **compilación aprobada** con la invocación directa indicada arriba, ejecutada fuera del sandbox. Advertencias CommonJS de dependencias existentes; sin errores de compilación.
- Chromium: **aprobado** login, menú, ausencia de ambos widgets, filtro por sucursal, XLSX real con sólo la sucursal seleccionada, denegación/redirección de las nueve URLs directas probadas y logout. **Cero consultas ajenas**; tres solicitudes API (login y dos consultas Original).
- Chromium no estaba disponible en la ubicación del sandbox; se usó el instalado fuera del sandbox, sin instalar paquetes. El primer recorrido allí falló por usar una URL inexistente de Campañas; corregido el test a `/marketing/campaigns-v2`, pasó completo.
- `git diff --check`: sin errores. `git status --short`: revisado; `backend/runtime/` preexistente permanece fuera del commit.
- `graphify update .`: extracción AST realizada; advierte de siete fuentes sin nodos y falta del parser opcional `tree_sitter_sql`. El resultado final se registra en el PR.

Pendiente: aceptación con cuenta real, sucursales aprobadas y datos reales, además del fallo preexistente del Excel semanal. El PR se entrega en borrador. No se ejecutaron migraciones, merge ni despliegue.
