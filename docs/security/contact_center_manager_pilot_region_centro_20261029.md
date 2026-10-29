# Contact Center — extensión del piloto a Región Centro (2026-10-29)

## Alcance verificado

La consulta de producción a `suite_sucursal_region_assignments`, `suite_regions` y
`sucursales`, filtrada por región vigente `CDMX_IXT_TLAL_CHIH`, devuelve
exactamente las cinco sucursales de **Región Centro**:

| ID | Sucursal |
| ---: | --- |
| 19 | Sendero Chihuahua |
| 21 | Ixtapaluca |
| 22 | Insurgentes |
| 23 | Tlalnepantla |
| 25 | Metepec |

Se agregan a las 13 sucursales gerenciales ya habilitadas (1–13). El piloto
total queda en **18 sucursales**. Permanecen fuera del piloto, entre otras,
14–18, 20, 24 y 26.

## Contrato de acceso

- Backend: `backend/app/utils/contact_center_access.py` amplía
  `CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS` con 19, 21, 22, 23 y 25.
  `_manager_allowed_branch_ids()` conserva la intersección entre
  sucursales asignadas al usuario y sucursales del piloto.
- Frontend: `frontend/src/app/contact-center/contact-center-access.guard.ts`
  refleja exactamente el nuevo allowlist para habilitar navegación.
  El menú sigue dependiendo de `GET /api/contact-center/access` con
  `allowed=true`; no reemplaza los controles del backend.
- Los gerentes de sucursal tienen `is_manager=true`,
  `is_supervisor=false` y no obtienen permisos de operador, cartera global,
  ni operaciones sobre casos y citas de otras sucursales.
- La excepción regional existente sigue siendo exclusivamente **EDMUNDO**
  (ID 55, rol `GERENTE_REGIONAL`). La ampliación **no autoriza a ROBERTO**
  ni a otros gerentes regionales. Edmundo tampoco hereda automáticamente las
  sucursales Centro sin asignación explícita.
- Sin cambios en `permission_grants`, roles, asignaciones, base de datos ni
  Alembic. No se modifica el alcance de los operadores SANDRA y CANDY.

## QA

- Cada gerente de sucursal 19, 21, 22, 23 y 25 puede entrar, pero solo con
  su propio `allowed_branch_ids` y sin capacidades de operador/supervisor.
- Casos/citas de otra sucursal Centro se rechazan incluso si el caso aparece
  asignado al gerente por ID.
- Usuario con sucursales mixtas solo conserva las asignadas que pertenezcan al
  piloto; 14–18, 20, 24 y 26 continúan denegadas.
- ROBERTO como `GERENTE_REGIONAL` continúa denegado, mientras EDMUNDO conserva
  únicamente el alcance realmente asignado.
- CI: contrato de backend, contrato frontend del allowlist, aislamiento de
  sucursales y build Angular de producción.

## Despliegue posterior al merge

Desplegar mediante Git/Compose **backend y frontend** en servidor, sin edición
manual y sin migraciones. Validar con una sesión real de gerente Centro
`GET /api/contact-center/access`: `allowed=true`, `is_manager=true`,
`is_supervisor=false` y `allowed_branch_ids` limitado a su sucursal.
Validar una cuenta regional distinta a EDMUNDO con `403` si intenta acceder.
