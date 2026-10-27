# Contact Center — expansión del piloto gerencial a Mexicali y San Luis (2026-10-27)

## Decisión y alcance operativo

Solicitud: habilitar Contact Center a los gerentes de Mexicali y San Luis, conservando Costa BC y Villas del Rey ya en piloto.

La lista de sucursales del piloto pasa de `[1,7,8,9,10,11,12,13]` a `[1,2,3,4,5,6,7,8,9,10,11,12,13]`.
- **1–5:** Mexicali (incluye Villas del Rey 1 ya autorizado).
- **6:** San Luis Río Colorado.
- **7–13:** Costa BC / Tijuana, Rosarito y Ensenada.
- **14 o mayores, 1000 y otras sucursales fuera del piloto:** sin nueva habilitación.

## Contrato de seguridad

**Backend:** `backend/app/utils/contact_center_access.py::CONTACT_CENTER_MANAGER_ALLOWED_BRANCH_IDS` se amplía a los IDs 1–13. `_manager_allowed_branch_ids()` mantiene la intersección **sucursales asignadas al usuario ∩ sucursales piloto**, no la lista del piloto completa. El rol `GERENTE` entra solo si el resultado tiene al menos una sucursal. La excepción regional sigue siendo únicamente `id=55`, `username=EDMUNDO`, `rol=GERENTE_REGIONAL`; **otros GERENTE_REGIONAL no obtienen acceso**.

**Angular:** `frontend/src/app/contact-center/contact-center-access.guard.ts` replica los IDs del piloto para habilitar navegación. El menú continúa solicitando `GET /api/contact-center/access` y únicamente se publica con `allowed=true` del backend. Ningún check de `permission_grants` cambia autorización real de Contact Center en este milestone.

**Capacidades:** `is_manager=true`, `is_supervisor=false` para estos gerentes. Los handlers de `contact_center_routes.py` preservan restricciones legacy en lectura de cartera, contactos, CRM, citas y escritura sobre recursos. No concede capacidades de operador ni supervisor. Una sucursal habilitada no convierte en propios contactos/casos ajenos. Se conserva la excepción legacy de seguimiento de cita no asistida donde aplique.

**Impacto explícito en Edmundo:** el usuario 55 tiene asignadas sucursales 1–13, por lo que su alcance `allowed_branch_ids` pasa de ocho a **trece** al ampliar el piloto. No recibe acceso a sucursal 1000. Si se requiere restringirlo nuevamente a Costa BC, habría que definir una regla regional específica que esta expansión **no implementa**.

## QA / regresiones

- GERENTE de sucursales 2, 3, 4, 5 y 6: acceso sí, un único branch permitido en caso de tener solo ese asignado.
- GERENTE de sucursal externa 14: rechazo.
- GERENTE con sucursales mixtas [3,6,14,20]: solo [3,6].
- Otros regionales/roles administrativos: no amplían capacidad por pertenecer a esas sucursales.
- Edmundo: [1..13], sin supervisor ni operador; caso y cita en sucursal 14 siguen denegados.
- Persisten controles por caso/folio/sucursal y chequeo backend, frontend build, pruebas de contrato de menú.

Cambios exclusivamente Python, TypeScript de guard, tests y documentación. **Sin Alembic, sin migraciones, sin reasignar roles ni alterar datos**. Tras fusionar, desplegar ambos servicios `backend` y `frontend` por Git/Compose y validar un gerente de Mexicali, uno de San Luis y Edmundo usando `GET /api/contact-center/access` en su propia sesión.
