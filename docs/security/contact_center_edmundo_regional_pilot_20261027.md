# Suite Ultra — Contact Center / Piloto regional EDMUNDO (27-oct-2026)

## Evidencia y decisión

Consulta ADMICORP `/api/permissions/catalog/users/search?q=EDMUNDO` en producción: `id=55`, `username=EDMUNDO`, `rol=GERENTE_REGIONAL`, `sucursal_id=1000`, sucursales asignadas `1..13`.

El piloto vigente de Contact Center permite a gerentes solo las sucursales **1, 7, 8, 9, 10, 11, 12, 13**. Edmundo cumple la intersección, pero `contact-center-access.guard.ts` y `contact_center_access.py` solo reconocían el rol `GERENTE`.

Para **no dar acceso a todos los usuarios con `GERENTE_REGIONAL`**, el piloto se amplía **solo a la cuenta de Edmundo**:
- Backend: ID de usuario 55, username normalizado EDMUNDO, rol GERENTE_REGIONAL. El frontend permite presentar el menú para username EDMUNDO + rol GERENTE_REGIONAL, y sigue condicionándolo a la respuesta de `GET /api/contact-center/access` que resuelve identidad real en backend.
- Se preserva el rol GERENTE para sus sucursales existentes; ni SANDRA/CANDY ni ADMICORP cambian.
- El backend calcula `allowed_branch_ids = asignadas ∩ piloto`: para Edmundo, `[1,7,8,9,10,11,12,13]`. **NO** incluye 2–6 ni 1000.
- `is_manager=true`, `is_supervisor=false`; no obtiene privilegios de operador ni vista global. Se mantiene la regla de gerente: su cartera propia, excepciones preexistentes de seguimiento por no asistencia y restricciones de escritura/agenda por sucursal. Si no tiene casos asignados, la cartera puede aparecer vacía.
- En Angular el menú se publica solo tras `/contact-center/access.allowed===true`. La ruta mantiene su guard frontend y el backend continúa aplicando filtros y controles reales en cada endpoint.

## QA

Pruebas sintéticas: ocho sucursales autorizadas y cinco bloqueadas; ninguna habilitación para otro regional, otra identidad, otro rol ni regional sin sucursal piloto. Negado el acceso de operador y operaciones sobre casos/citas en sucursales no piloto. Contrato HTTP de `GET /contact-center/access` y contrato frontend de guard + menú. CI ejecuta pruebas backend y Angular build.

**Sin cambios a BD / Alembic / roles, al menú general, servicios, grants ni permisos centralizados.** El editor visual de permisos todavía no gobierna Contact Center; una futura integración de `contact_center.access` deberá mantener la intersección de sucursales y guards existentes, con migración/QA separados.
