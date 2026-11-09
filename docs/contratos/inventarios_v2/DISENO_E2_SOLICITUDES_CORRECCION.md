# Inventarios V2 — E2: diseño técnico de solicitudes de corrección

**Fecha:** 2026-10-23  
**Versión:** propuesta técnica 0.1; **no equivale a E2 implementado ni aceptado**.  
**Contrato rector:** [CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md](./CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md), secciones 2, 4, 6, 7, 9, 11, 12 y 14.  
**Estado de acceso:** `GERENTE_ROLLOUT = OFF`. No cambiar roles, menús, guards ni bases por este documento.

## 1. Resultado de inspección de `main`

| Archivo | Evidencia / decisión para E2 |
|---|---|
| `backend/app/models/inventario.py::InventarioGeneral` | Los campos `codigo_interno`, `nombre`, `marca`, `categoria_inventario_id`, `familia_equipo_id`, etc. pertenecen al maestro potencialmente compartido. No son atributos exclusivos de sucursal. |
| `backend/app/models/inventario.py::InventarioSucursal` | El stock es por sucursal, con unicidad `(inventario_id, sucursal_id)` y PK `id`; inventario_id **solo** no identifica una discrepancia física por sucursal. |
| `backend/app/models/inventario_codigo_correccion.py` y `backend/app/routes/inventarios.py::corregir_codigo_interno()` | La corrección V1 de código **aplica** inmediatamente el cambio oficial y deja historial. E2 no debe invocar ese endpoint ni actualizar el maestro. Su integración autorizada corresponde a E3. |
| `backend/app/routes/inventarios.py::_resolve_inventory_read_sucursal_ids()` | Actualmente la lectura V1 puede reconocer otros roles con `sucursal_id`; no equivale a autorizar E2. Requiere hardening/QA por separado antes de exponer V2. |
| `backend/app/routes/inventarios.py::_require_inventory_movement_write()` | Los permisos de movimientos no autorizan automáticamente crear solicitudes. `SR_MANTENIMIENTO` usa `usuario_sucursal`; `AUX_MANTENIMIENTO` usa sucursal primaria. |
| `backend/app/models/user_model.py::UserORM` | El usuario real está en `users.id`, con `rol`, `sucursal_id` y relación `usuario_sucursal`; el creador efectivo se obtiene de la sesión autenticada y se contrasta en DB. |
| `backend/app/routes/permissions_catalog_routes.py` y `backend/tests/routes/test_permissions_phase_a_inventory_parity.py` | Existe catálogo diagnóstico de `inventory.read`/`inventory.master_write`/`inventory.movement_write`. Los tests demuestran falsos alcances para SR/AUX cuando el catálogo combina primaria + M:N. **No usar la proyección diagnóstica como guard de autorización E2.** |
| `frontend/src/app/inventario/existencias/existencias.component.ts` | E1 dispone de lectura piloto y datos `inventario_id`, `sucursal_id`, stock, categoría, familia. En E2 se reutiliza el contexto sin inventar autorizaciones desde Angular. |

Esta revisión es estática del repositorio; **no es QA autenticado de producción ni auditoría de grants reales de DB**.

## 2. Objetivo, separación e invariantes

E2 recibe y conserva una **propuesta**: no cambia `inventario_general`, `inventario_sucursal`, existencias, códigos, movimientos, ni catálogos. Ninguna propuesta `PENDING` es una corrección aplicada ni una verificación física aprobada.

Casos mínimos:

1. `MASTER_FIELD`: atributo maestro incorrecto; campo propuesto desde una **allowlist** (no nombre arbitrario). Advertir alcance compartido antes de enviar.
2. `QUANTITY_DIFFERENCE`: cantidad encontrada distinta del stock lógico; conservar `stock_original` y `cantidad_fisica`. No fabricar una salida.
3. `NOT_LOCATED`: referencia registrada que no pudo localizarse; observación física, **sin poner stock a cero**.
4. `UNREGISTERED_FIND`: equipo/artículo hallado que no existe en la sucursal; identidad **provisional**, sin `inventario_id` inventado ni alta automática.

No confundir `UNREGISTERED_FIND` con un artículo existente en otro local: E3 decidirá si corresponde un maestro existente, nueva referencia, asociación o revisión.

## 3. Modelo de persistencia propuesto — para PR posterior con Alembic

**Tabla propuesta:** `inventario_correccion_solicitudes`; modelo `backend/app/models/inventario_solicitud_correccion.py::InventarioSolicitudCorreccionORM`.

| Campo | Tipo propuesto | Regla |
|---|---|---|
| `id` | BIGINT PK | Identidad estable de solicitud. |
| `tipo` | VARCHAR(40) | CHECK con los cuatro casos anteriores. |
| `estado` | VARCHAR(24) | DEFAULT/CHECK `PENDING` para E2; `APPROVED`/`REJECTED` reservados a E3, no publicarlos como acciones E2. |
| `sucursal_id` | INTEGER NOT NULL FK | Sucursal efectiva; el backend verifica el alcance antes de insertar o leer. |
| `inventario_id` | INTEGER NULL FK | Referencia existente; NULL solo para hallazgo no registrado. |
| `inventario_sucursal_id` | INTEGER NULL FK | Vincula la fila oficial por sucursal; validar consistencia con el par `(sucursal_id, inventario_id)`. |
| `campo` | VARCHAR(64) NULL | Para `MASTER_FIELD`, exclusivamente allowlist de atributos seguros, con revisión explícita de alcance global. |
| `valor_original` | JSONB NULL | Copia inmutable del valor oficial leído de DB, no del payload cliente. |
| `valor_propuesto` | JSONB NULL | Valor/observación propuesta por el usuario, validado según tipo. Nunca aplicar directamente. |
| `hallazgo_provisional` | JSONB NULL | Datos descriptivos de `UNREGISTERED_FIND`; no crea maestro. |
| `baseline_canonico` | JSONB NOT NULL | Identidad y valores oficiales observados al registrar: par de referencia, stock y/o campo maestro relevante; para nuevo hallazgo, ausencia de referencia. |
| `fecha_observacion_local` | DATE NULL | Fecha de observación física interpretada en `America/Tijuana`; distinta de la creación. |
| `motivo` | TEXT NOT NULL | Explicación humana obligatoria; longitud acotada desde backend. |
| `evidencia_descriptiva` | TEXT NULL | Nota física inicial; política de fotos/archivos aún pendiente. |
| `creado_por_usuario_id` | INTEGER NOT NULL FK a `users.id` | Fijado exclusivamente desde JWT + consulta a usuario DB. |
| `creado_en_utc` | TIMESTAMPTZ NOT NULL | Tiempo de persistencia inequívoco en UTC. |
| `idempotency_key` | UUID NOT NULL | Identificador único de intento; UNIQUE por creador, evita dobles POST/red/reintentos. |

**Constraints e índices de la migración:** `CHECK` para tipo/estado; integridad de referencia existente vs hallazgo provisional; índices por `(sucursal_id, estado, creado_en_utc)`, `(inventario_id, estado)`, `(creado_por_usuario_id, creado_en_utc)`; UNIQUE `(creado_por_usuario_id, idempotency_key)`; FKs con `ON DELETE RESTRICT` donde corresponda. No asumir que índices de JSONB sustituyen validación de payload.

**Límite del modelo:** `InventarioGeneral` y `InventarioSucursal` no tienen un `version` canónico explícito. Guardar valores/base del registro y, al abrir una propuesta, cotejar `valor_original` enviado por la UI con DB; devolver 409 si ya cambió. E3 deberá volver a comparar bajo bloqueo transaccional antes de aplicar cualquier propuesta. Un snapshot E2 **no congela** stock vivo. El requisito de cut/version físico formal corresponde a E4.

**Auditoría futura:** la fila de propuesta y su payload original no se editan en E2; E3 agrega registro de transiciones y autorización por separado, sin borrar/reemplazar historia. Decidir si este log nace con el esquema de E2 o con la migración de E3 según QA de trazabilidad; **nunca** actualizar estado silenciosamente.

## 4. Matriz de autorización propuesta (NO grants efectivos)

Cada endpoint E2 necesita una autorización **propia y fail-closed** (acción conceptual `inventory.correction_request`), además de JWT, usuario DB y alcance de sucursal. **No heredar** `inventory.read`, `inventory.master_write` ni `inventory.movement_write` como sustitutos. El catálogo global de permisos está en transición: registrar la nueva acción/ruta según su política cuando se implemente; una previsualización de catálogo no reemplaza el guard del endpoint.

| Rol | Leer/crear propuestas E2, cuando se implemente | Aprobar/aplicar en E2 |
|---|---|---|
| `ADMIN`, `ADMINISTRADOR`, `SUPER_ADMIN` | Piloto: sucursales autorizadas globalmente, sujetas a guard E2 expreso | **NO** |
| `MANTENIMIENTO`, `SISTEMAS`, `TECNICO` | Piloto: global por política actual de E1, con guard E2 expreso | **NO** |
| `SR_MANTENIMIENTO` | Solo `usuario_sucursal` efectivo de DB; **no** agregar sucursal primaria no asignada | **NO** |
| `AUX_MANTENIMIENTO` | Solo `sucursal_id` primaria efectiva de DB | **NO** |
| `GERENTE`, `GERENTE_REGIONAL` | **DENEGADO**, incluso con URL/API directa, hasta E5 + autorización explícita | **NO** |
| `COORDINADOR_MANTENIMIENTO`, `COMPRAS`, `LECTOR_GLOBAL`, otros | **DENEGADO por defecto**; coord. puede ser futura revisora en E3 solo tras verificación DB/grants y matriz de competencia | **NO** |

Antes de implementación verificar roles/grants **reales** y el gate de seguridad de V1. No usar username (p. ej. `ADMICORP`) como regla. Los `sucursal_id`, `inventario_id`, `creado_por_usuario_id`, `estado`, `valor_original` y `baseline_canonico` no son autoridad por venir del cliente.

En lecturas y escrituras comprobar por separado:

- Rol/capacidad E2 explícitos; usuario activo/autenticado; sucursal efectiva autorizada.
- Referencia `(sucursal_id, inventario_id)` existe y la fila `inventario_sucursal` corresponde a ella. Para `UNREGISTERED_FIND`, admitir identidad provisional sin FK canónico.
- Listas filtradas en SQL; detalle por ID o consulta cruzada no revela registros de otra sucursal (403 o 404 según política de ocultación).
- Global **no** se infiere por enviar `sucursal_id=global` ni por pertenecer a otra pantalla/permiso.
- Las validaciones, idempotencia, persistencia y copia de valores canónicos se realizan dentro de transacción. Una falla no deja propuesta parcial.

## 5. API prevista — NO implementada

Se recomienda un blueprint E2 propio bajo `/api/inventario/solicitudes`:

- `POST /api/inventario/solicitudes`: validar caso, tipo/campo/identidad, motivo, sucursal efectiva y clave de idempotencia; capturar baseline oficial; insertar solo propuesta; responder 201 con ID y `PENDING`. Mismo intento repetido devuelve misma solicitud sin duplicar; mismo key con payload distinto devuelve 409.
- `GET /api/inventario/solicitudes`: paginación y filtros de sucursal/estado/tipo autorizados; jamás recuperar global y filtrar solo en Angular.
- `GET /api/inventario/solicitudes/<id>`: detalle de valor anterior/propuesto y trazabilidad; fail-closed ante ID ajeno.

**No** habrá `PUT/PATCH/DELETE`, aprobar, rechazar, aplicar stock, modificar código o crear artículo en E2. E3 definirá esas transiciones.

### Validación de duplicados y concurrencia

1. Bloquear reintentos de envío mediante `idempotency_key` y UNIQUE DB.
2. En casos de misma referencia/campo/tipo con otra solicitud abierta, presentar advertencia/posible conflicto en backend; concretar política de bloqueo antes del endpoint. No prohibir por similitud de nombre los hallazgos de activos distintos.
3. La comparación de `valor_original` contra valor actual es obligatoria para la propuesta asociada a referencia; si no coincide, responder 409/releer.
4. En E3 rechazar aplicación obsoleta y doble aprobación por control transaccional e historial; no construir esa lógica prematuramente.

## 6. UX objetivo, para PR posterior

En `/#/inventario/existencias`, botón `Solicitar corrección` por referencia **solo para rol E2 autorizado**. Modal con tipo, campo si aplica, **dato oficial solo lectura**, dato propuesto/observado, sucursal explícita, motivo y confirmación de que no afecta inventario oficial. Para `UNREGISTERED_FIND`, acción separada `Reportar artículo no registrado`, sin `inventario_id` falso. Bandeja sencilla `Mis solicitudes` / `Solicitudes de mi alcance` mostrará estado `PENDING`, creador y fecha; la bandeja de decisión E3 no forma parte de esta etapa.

Angular en archivos separados `.ts`, `.html`, `.css`; lógica y normalización en TS, backend autoridad de seguridad y datos.

## 7. QA obligatorio de E2 (posterior, no ejecutado aquí)

- Caso de cada uno de los cuatro tipos y registros sin `inventario_id`.
- Confirmación SQL antes/después: filas de `inventario_general`, `inventario_sucursal`, movimientos, código e historial V1 **inalterados** después de crear propuesta.
- Actor/sucursal originales confiables desde DB/JWT; payload falsificado no cambia dueño/rol/estado/stock/maestro.
- Denegación `GERENTE`/`GERENTE_REGIONAL`/coordinación no habilitada y alcance de otra sucursal (IDOR), incluyendo directo por API.
- Permisos SR por M:N sin heredar primaria; AUX solo primaria; global solo con guard explícito.
- Reintentos concurrentes de POST; idempotencia; validación de duplicados; 409 por formulario obsoleto; transacción y rollback.
- GET listado/detalle por alcance; estado de carga, filtros, vacío/error y E1 intacto.
- Migración Alembic con pruebas en PostgreSQL temporal; rollback planificado; regresión de QA V1/E1.

## 8. Orden de PRs y decisiones abiertas

**PR 0 (seguridad, separado):** validar con QA real el acceso V1 por ruta/API directa de roles no liberados; diseñar/ejecutar hardening apropiado que conserve capacidades V1 existentes, sin ampliar acceso. La nueva API E2 debe quedar cerrada aunque un endpoint V1 siga siendo legible por razones de compatibilidad.

**PR 1 (modelo):** SQLAlchemy + Alembic de solicitudes, restricciones y QA PostgreSQL, **sin endpoint de propuesta expuesto**.

**PR 2 (API):** guard E2 propio, creación y lecturas seguras, idempotencia, pruebas. Mapear nuevas rutas/acciones en catálogo de permisos observacional, sin asumir que lo vuelve enforcement automático.

**PR 3 (frontend):** modal y vista de solicitudes para usuarios piloto autorizados, con QA responsivo y regresión.

**Decisiones pendientes de validar con responsable antes de implementarlas:**

1. Campos maestros que el operador puede proponer, si un código compartido se muestra con advertencia especial y cómo distinguir corrección global vs local.
2. Política de evidencia: texto inicial vs foto/archivo, límites, retención, visibilidad; no crear almacenamiento de archivos sin definirla.
3. Duplicado semántico: advertir o bloquear otra solicitud PENDING sobre misma referencia/campo.
4. Qué roles del piloto E1 realmente podrán **crear** propuestas E2, considerando grants reales y permisos globales en transición (la matriz anterior es propuesta, no autorización).
5. Fecha física observada: opcional en solicitud E2 hasta que E4 defina el ciclo formal; si se vuelve obligatoria, usar día de negocio `America/Tijuana`.

**Gate:** E2 seguirá `NO IMPLEMENTADO / NO ACEPTADO` tras este documento. GERENTES no se habilitan hasta E5 y aprobación explícita.
