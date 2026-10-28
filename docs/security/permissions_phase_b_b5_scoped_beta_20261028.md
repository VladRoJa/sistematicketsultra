# Suite Ultra — Fase B / B5: editor beta de grants por sucursal

**Issue:** #1161. **Modo:** `compare_only`, sin enforcement de Nube.
**Seguridad:** `PERMISSIONS_B5_EDITOR_ENABLED=false` por defecto. No se habilita
ni se crean grants en producción por el merge de este PR.

## Por qué se implementa de forma aislada

B4 observó tres grants productivos, entre ellos:
`inventory.correction_approve`, `tickets.maintenance.coordinate` y
`tickets.maintenance.read_assigned_only`. Esas acciones usan grants reales
en los guards de Inventario/Tickets y **NO** son equivalentes al catálogo
global en `compare_only`. Por eso B5 solo acepta la acción exacta
`internal_documents.view` como configuración diagnóstica.

`internal_documents.manage` está excluida. El guard
`can_view_internal_document` continúa independiente para cada documento,
con sus reglas por estado, sensibilidad, visibilidad y excepciones de
cobranza y agregadoras. El grant beta no habilita entradas, lecturas
ni descargas por sí mismo.

## Diseño y límites

- API nueva: `permissions_b5_beta_routes.py`, blueprint registrado en
  `create_app()` bajo `/api/permissions/catalog`.
- Solo administrador validado desde DB con JWT.
- `GET /grants/beta/status`: flag, acción permitida, scopes, modo.
- `POST /grants/beta/preview`: valida sin persistir, funciona incluso
  con flag OFF, retorna `catalog_allowed=null`, `object_access_certified=false`,
  `http_authorization=not_evaluated`.
- `POST /grants/beta`: creación individual.
- `PATCH /grants/beta/<grant_id>`: modificación del mismo ID/usuario/acción,
  requiere `expected_updated_at` ISO con zona.
- `POST /grants/beta/<grant_id>/disable`: baja selectiva (`inherit`
  lógico), no elimina físicamente ni desactiva grants asociados.
- Métodos de escritura **403** mientras el flag OFF, antes de leer/crear
  datos. Activar este flag es un gate futuro, NO parte del milestone.

Los payloads solo admiten principal de usuario existente, acción exacta
`internal_documents.view`, efecto `allow|deny`, scope `branch|branch_list`,
sucursales existentes `ACTIVA` y no demo asignadas al usuario según DB,
motivo explícito y fechas ISO con offset (nulas permitidas).

No se admiten grants globales, de rol, departamento, módulo, custom ni
`scope_payload`. La tabla y el audit log ya soportan estos campos; no
se agrega tabla ni migración Alembic en B5.

## Política de conflicto

Cada operación sobre un usuario debe serializarse mediante `FOR UPDATE`
sobre la fila de ese usuario **antes** de comprobar colisiones, incluso si
no existía un grant previo. Así, dos creates concurrentes quedan ordenados.
Para el mismo usuario y acción, grants activos y no borrados no pueden
solaparse a la vez en sucursales y tiempo, incluso con el mismo efecto.
Las ventanas son semiabiertas `[start,end)`: intervalos contiguos no
colisionan; extremos nulos equivalen a infinito.

Grants globales, personalizados, por rol correspondiente o scopes
ilegibles devuelven HTTP 409; no se aplica precedencia artificial.
Grants inactivos son históricos y no compiten. `PATCH` compara timestamp
de última actualización y devuelve HTTP 409 en conflicto de versión.

`created`, `updated` y `disabled` registran snapshots before/after,
actor, motivo y timestamp dentro de la misma transacción. Si falla auditoría,
se revierte la modificación. Las reglas actuales del editor V1 permanecen,
salvo que con B5 habilitado se rechace la escritura global del módulo
`internal_documents` (HTTP 409) para evitar dos escritores incompatibles.

## Interfaz Angular

Componente standalone separado en `.ts`, `.html` y `.css` en la pestaña
Grants beta; el servicio ya administra las llamadas y el componente evalúa
la vista de preview. Botones mutadores inhabilitados salvo confirmación de
flag backend y previsualización; el backend mantiene toda la autorización.
En producción con flag OFF solo es posible preparar/validar, no guardar.

## Pruebas requeridas

- Backend sintético: 401 sin JWT, 403 no admin y flag OFF,
  allowlist estricta, IDs, scope/fechas inválidos, UTC y fronteras
  temporales, conflictos, versionado, rollback cuando falla auditoría.
- CI: `py_compile` para blueprint y pruebas de permisos existentes,
  Angular `ng build --configuration production`.
- QA producción B5 inicial: status OFF + preview sintético read-only,
  **sin crear o alterar grants**.
- QA de concurrencia verdadera con PostgreSQL y dos transacciones antes
  de aprobar la activación futura del flag; no afirmar que un mock equivale
  a ejecución paralela en producción.
- Gate independiente antes de encender escritura: revisión de seguridad,
  atomicidad, auditoría, permisos admin, alcance y conflictos con datos
  sintéticos. No encender `grants_overlay` ni `grants_enforced`.

**Rollback:** retirar el código del PR y volver a frontend/backend previos.
Mientras flag OFF, no existe migración ni escritura beta que revertir.
