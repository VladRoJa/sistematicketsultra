# Inventarios V2 · E3 — adenda de lotes y autorización efectiva

**Estado:** preparación técnica, sin habilitar permisos ni cambios oficiales. **Fecha:** 2026-10-26.  
**Documentos relacionados:** contrato global §7 y PR draft #1119. Esquema aislado PR draft #1134.

## 1. Regla operativa ratificada

Un revisor **autoriza** una solicitud únicamente cuando el backend logra, en **un solo commit**:
1. Comprobar sesión y capacidad de aprobación en DB, sucursal, departamento, clase de activo e independencia respecto al creador.
2. Bloquear solicitudes y referencias oficiales (`FOR UPDATE`) en orden estable y revalidar estado `PENDING` y baseline.
3. Aplicar cambio oficial y el efecto auditable correspondiente (ajuste, maestro o alta/vinculación).
4. Escribir evento de decisión, asociar al lote, marcar `APPROVED` y confirmar.
   
Cualquier conflicto hace **ROLLBACK de todo el lote**; ninguna solicitud parcialmente aprobada. Rechazo: registrar motivo y decisor y cambiar solo estado a `REJECTED`. El esquema solo habilita persistencia, **no ejecuta estas acciones**.

## 2. Lote de revisión como unidad de idempotencia

La tabla propuesta `inventario_correccion_lotes` identifica una operación de 1 a N decisiones mediante `(actor_usuario_id, idempotency_key)` UNIQUE + fingerprint de **todo el payload**: acción, IDs ordenados, motivo y resoluciones. Las decisiones contienen `lote_id`, `solicitud_id` UNIQUE, actor, fecha y resultado. Los efectos contienen FK compuesta `(decision_id, solicitud_id)`; una bitácora no puede vincularse a una solicitud ajena a su decisión.

**Por qué no UUID por fila:** un mismo clic `Autorizar 10` necesita conservar identidad única y resultado único al reintentar, aunque haya timeout. Si un solo ID falla, todo el lote es rechazado con 409/422 y la operación no registra `APPROVED`. El servicio posterior deberá comprobar que no hay IDs repetidos ni dos solicitudes sobre la misma referencia/atributo capaces de pisarse.

Las reglas **decisión y efecto coexisten**, **lote aplicado atómicamente** y **sin autoaprobación** requieren enforcement en servicio y pruebas; el esquema por sí solo no las ejecuta.

## 3. Competencias: no equiparar acceso E2 con permiso E3

| Perfil/rol | Solicitar E2 | Aprobar E3 | Condición pendiente |
|---|---|---|---|
| Administración corporativa autorizada | Según guard E2 | **Candidato, no concedido** | Grant efectivo en DB y responsabilidad por tipo |
| MANTENIMIENTO | Acceso piloto E2 | **Candidato, no concedido** | Alcance efectivo, departamento y clase de activo |
| COORDINADOR_MANTENIMIENTO (Yuliana) | E2 denegado actualmente | **Pendiente, no concedido** | Reconciliar contrato §7, rol, departamento, sucursales y separación funcional; ninguna excepción por usuario |
| SR_MANTENIMIENTO / AUX_MANTENIMIENTO / TECNICO / SISTEMAS | Alcance piloto según rol | **Denegado por defecto** | Un rol técnico o capacidad de reportar no autoriza cambios oficiales |
| GERENTE y GERENTE_REGIONAL | **No liberados hasta E5** | **Denegado hasta E5** | No introducir una ruta E3 que evada el gate |
| LECTOR_GLOBAL y otros roles | No liberado | **Denegado** | No se admiten inferencias por sucursal primaria |

**No afirmar que estos grants existen**: no se ha consultado la DB de producción con acceso de lectura. El backend E3 deberá tener un guard dedicado `inventory.correction_approve` y denegar por defecto. El frontend solo refleja el resultado autorizado. Una matriz diagnóstica de permisos no es fuente de autorización.

Control de independencia: `decision.actor_usuario_id != solicitud.creado_por_usuario_id` incluso para administradores. Si la cuenta autora es ADMICORP, otro responsable con capacidad validada debe decidir.

### Decisión de alcance ratificada (26/10/2026)

**ADMICORP** tendrá competencia corporativa sobre todas las sucursales Ultra; **los demás autorizadores** solo podrán intervenir solicitudes de sus sucursales expresamente asignadas en `usuario_sucursal`, nunca por `sucursal_id` primaria ficticia (p. ej. 100). Esta regla no equivale a conceder permisos: el guard E3 necesita la acción explícita `inventory.correction_approve` vigente y no debe tomar privilegios `inventory.master_write` o `inventory.movement_write` como sustitutos.

Para evitar privilegios corporativos accidentales a otros usuarios con rol ADMINISTRADOR, el alcance global se reconocerá exclusivamente mediante **grant explícito individual** de `inventory.correction_approve` con `scope_type=global`; jamás basta el rol ADMINISTRADOR, ni se programa una excepción por `username` o `id=47`. Si la acción no tiene grants, **todos quedan denegados**. En el momento autorizado se puede asignar a ADMICORP mediante procedimiento auditado; no forma parte del PR actual.

Los perfiles MANTENIMIENTO y COORDINADOR_MANTENIMIENTO podrán ser candidatos E3 solo con grant explícito; además sus ramas efectivas son la intersección entre el alcance del grant y `usuario_sucursal` leído de DB por operación. Un grant `global` para esos roles **no amplía** más allá de sus asignaciones. A los gerentes y regionales **no se les permite E3 hasta E5**, aunque dispongan de asignaciones u otros permisos.

**Maestro global:** corregir `inventario_general` impacta a todas las sucursales que usen ese registro, así que un permiso limitado a una sola sucursal **no autoriza** una corrección `MASTER_FIELD`; requerirá autorización corporativa explícita. La creación de un artículo maestro nuevo en `UNREGISTERED_FIND` tendrá la misma restricción; la vinculación con un artículo ya existente podrá evaluarse por sucursal en el servicio posterior.

**Independencia:** incluso el autorizador corporativo no podrá decidir solicitudes creadas por su propia cuenta. Las solicitudes #1/#2 registradas por ADMICORP requerirán otro aprobador habilitado y competente, nunca un bypass administrativo.

El guard aquí propuesto solo determinará elegibilidad; aprobar, rechazar y modificar maestro o existencias seguirán inactivos hasta implementar el servicio atómico y cerrar los QA de E2.

## 3.1. Alta de acción E3 — catálogo sin concesiones

La consulta de producción del 26/10/2026 confirmó que el módulo `inventory` solo contiene `inventory.read`, `inventory.master_write` e `inventory.movement_write`. También se consultaron grants de Inventarios para cuentas corporativas, mantenimiento, coordinación y regionales: **0 filas**. Esto demuestra ausencia de grants explícitos dentro del alcance consultado, **no** denegación de todos los permisos legacy.

Se agregó a este PR draft una migración Alembic **separada** `v2e3a1102626` (encadenada a `v2e3p2102626`) que registra solo `inventory.correction_approve` con riesgo `critical` y sin crear grants de usuario, rol o sucursal. `is_active` describe la disponibilidad de la **acción del catálogo**, no concede autorización de ejecución.

El backend seguirá denegando por defecto mientras no existan y se validen tanto el guard efectivo como los grants explícitos aprobados. El permiso de rechazar solicitudes será evaluado en el contrato del endpoint E3; no se hereda automáticamente autorización de `inventory.master_write` ni de `inventory.movement_write`.

**No ejecutar la migración en producción mientras el PR permanezca draft y los gates sigan abiertos.** El downgrade se bloquea si la acción ya tiene referencias en grants, ruta o configuración base del módulo.

## 4. Tratamiento por tipo

- **QUANTITY_DIFFERENCE:** ajuste oficial auditable con stock anterior/nuevo y delta firmada, sin registrar una `entrada/salida` falsa en V1.
- **MASTER_FIELD:** corrección de maestro compartido con validación global, unicidad de código y auditoría antes/después. Si es código interno, también conservar el journal V1 existente.
- **NOT_LOCATED:** no autorizar a cero sin `resolucion` expresa de baja/ajuste, facultad suficiente y evidencia; si no, dejar PENDING.
- **UNREGISTERED_FIND:** autorizar solo alta canónica completa o vinculación a artículo existente, validando categoría, tipo, identidad, cantidad y sucursal. Nombre por sí solo no basta.

## 5. Gates antes de endpoints y rollout

1. Documentar QA E2 completo: controles visuales ya verificados; completar prueba autenticada de rol/sucursal y comparar invariancia V1 contra registros de prueba.
2. Verificar grants, alcance por usuario-sucursal, departamento y responsabilidad sin modificar cuentas productivas.
3. Acordar criterios de `NOT_LOCATED`, `UNREGISTERED_FIND` y categorías maestros de impacto global.
4. Ensayar DDL de PR draft #1134 en PostgreSQL efímero. No desplegar migración mientras los gates 1–3 estén abiertos.
5. Implementar servicio transaccional (PR separado), luego endpoints/QA negativo y finalmente botones E3. `GERENTE_ROLLOUT=OFF` hasta E5.

**Estado actual:** PR #1134 no contiene endpoints, ajustes aplicados ni permisos. Solicitudes de ULTRA DEMO #1 y #2 permanecen `PENDING` hasta una decisión futura legítima.
