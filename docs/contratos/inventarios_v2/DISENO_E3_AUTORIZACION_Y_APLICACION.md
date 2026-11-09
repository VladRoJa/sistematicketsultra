# Inventarios V2 · E3 — Diseño de autorización con aplicación inmediata

**Fecha:** 2026-10-26  
**Estado:** DISEÑO TÉCNICO / NO IMPLEMENTADO / NO HABILITADO  
**Fuente normativa:** `CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md`, §7.  
**Regla aclarada por el responsable:** la autorización formal de un revisor competente **aplica el cambio al inventario oficial y registra su movimiento o auditoría en la misma transacción**. No existe una segunda aprobación posterior.

## 1. Evidencia verificada en `main`

| Elemento | Estado real | Consecuencia E3 |
|---|---|---|
| `InventarioSolicitudCorreccionORM` | Tabla E2 con cuatro tipos, estados `PENDING/APPROVED/REJECTED`, creador, sucursal, baseline y valores. No campos de aprobador/fecha de decisión. | Se requiere historial adicional de transición y relación a los efectos oficiales. |
| `inventario_solicitudes_routes.py` | Solo POST crear y GET lista/detalle. Guard E2 de piloto; `GERENTE`, `GERENTE_REGIONAL`, `COORDINADOR_MANTENIMIENTO` bloqueados. | Crear un guard **E3 separado** de leer/proponer E2; no heredar su allowlist ni abrir E5. |
| `MovimientoInventario` | Enum PostgreSQL `tipo_movimiento_enum` permite **solo `entrada` y `salida`**. Detalles positivos y anulación V1 limitada a esos dos tipos. | Un ajuste de conteo físico **no debe disfrazarse** como entrada/salida; preservar historial V1 y definir ajuste auditado E3 propio. |
| `corregir_codigo_interno()` | Controla unicidad, locks, valor anterior y guarda `InventarioCodigoCorreccionORM` en un commit. | Extraer/reutilizar validaciones en servicio interno transaccional; **no llamar al endpoint desde otro endpoint**. |
| `editar_inventario()` | Actualiza maestro, valida familia; no hay historial universal por cada campo. | Un cambio autorizado a nombre/marca/familia/categoría necesita auditoría específica anterior/nuevo y alcance global. |
| `crear_inventario()` | Un maestro nuevo exige, entre otros, nombre, categoría y código válido en determinados tipos. | `UNREGISTERED_FIND` de E2 solo tiene nombre y opcionales: **no autorizar creación canónica incompleta**. |
| `usuario_sucursal` | Tabla M:N por usuario/sucursal; `UserORM.sucursal_id` primario y `department_id`. | Alcance E3 debe verificarse en DB por rol/capacidad/sucursal/tipo de activo. |
| `permissions_catalog_routes.py` | Proyección diagnóstica; no es guard efectivo. | Crear control explícito backend de decisión. |

## 2. Semántica de decisión ratificada

```text
Solicitud PENDING
  ├── Rechazar (revisor habilitado + motivo)
  │     └── REJECTED + evento de rechazo; inventario oficial sin cambios
  └── Autorizar (revisor habilitado + revalidación con locks)
        ├── todo válido: cambio canónico + ajuste/auditoría + evento + APPROVED
        │              (UN SOLO COMMIT; visibles juntos)
        └── conflicto: ROLLBACK + 409; solicitud permanece PENDING
```

**Sin estado "aprobada pero por aplicar".** Si la aplicación oficial no es posible, **no** se debe escribir `APPROVED`, ni crear un evento de aprobación ficticio. Prohibido aprobar la solicitud propia, aunque el creador tenga facultades administrativas. No borrar la propuesta original ni reescribir el valor observado.

### 2.1 Tratamiento por tipo

| Tipo E2 | Aplicación E3 prevista | Reglas especiales |
|---|---|---|
| `QUANTITY_DIFFERENCE` | Ajustar `InventarioSucursal.stock` al conteo físico aprobado; evento de ajuste con cantidad firmada, antes/después, referencia y aprobador. | Bloquear fila y comparar baseline; stock resultante no negativo. **No** registrar `entrada` o `salida` falsa. |
| `MASTER_FIELD` | Actualizar **maestro compartido**; guardar evento de atributo anterior/nuevo. Código interno conserva el control de unicidad y auditoría existente. | Exigir facultad para modificar maestro global, validar tipo/categoría/familia y efecto sobre otras sucursales; coordinación local no adquiere facultad global implícita. |
| `NOT_LOCATED` | No presumir automáticamente que una ausencia física equivale a dar de baja el activo. La decisión debe especificar ajuste oficial **a cero** si esa es la política aprobada, con movimiento de conciliación y evidencia. | Mantener pendiente autorización si falta confirmación expresa de la disposición; no ajustar a cero ni eliminar maestro por el simple reporte. |
| `UNREGISTERED_FIND` | Al autorizar, el revisor debe **identificar un maestro existente y vincularlo** o completar un alta canónica válida + existencia asociada, todo auditado. | E2 admite hallazgos con solo nombre. Nunca crear maestro con valores inventados; exigir categoría, tipo/código cuando proceda, identidad sin duplicados y cantidad/custodia antes de aplicar. |

**Regla de integridad:** no marcar `APPROVED` a `NOT_LOCATED` / `UNREGISTERED_FIND` cuando no exista una resolución aplicable e inequívoca; devolver error validado o `409`, conservando `PENDING`.

## 3. Roles y alcance: no confundir solicitud con aprobación

El contrato §7 fija **competencias objetivo**: administración corporativa, mantenimiento autorizado, coordinación de mantenimiento (Yuliana) y regional autorizado, cada uno solo según las capacidades reales, sucursales y tipo de activo.

**No se comprobó ningún grant individual en la DB de producción desde GitHub. No presuponer que esos perfiles ya pueden aprobar.**

- **Administración corporativa:** candidato a global, siempre con capacidad backend explícita `inventory.correction_approve` y política de clase de activo.
- **Mantenimiento/coord. Yuliana:** acceso sujeto a `department_id`, sucursales efectivas y tipo de activo; `COORDINADOR_MANTENIMIENTO` **no** hereda por defecto lectura E2.
- **Regional:** el §7 lo plantea como futuro revisor, pero **E5 prohíbe abrir V2 a `GERENTE_REGIONAL` antes de E1–E4 y liberación expresa**. Por tanto permanece **denegado hasta resolver formalmente el gate E5**; no abrirlo mediante una ruta E3 alternativa.
- **`SR_MANTENIMIENTO`, `AUX_MANTENIMIENTO`, `TECNICO` o `SISTEMAS`:** poder solicitar o registrar movimientos V1 **no equivale** a competencia para aprobar correcciones E3.
- **`GERENTE`:** sin lectura/propuesta/aprobación V2 hasta E5; no aprobar por pertenecer a una sucursal.
- Verificar por solicitud: actor autenticado en DB, capacidad, alcance de sucursal, clase de activo, independencia respecto al creador y ausencia de conflictos de interés.

**Acción previa obligatoria:** reconciliar tabla real de usuarios/grants de aprobadores piloto, en especial alcance de Yuliana y manejo de categoría global, antes de habilitar escrituras.

## 4. Propuesta de esquema Alembic, únicamente como diseño

PR de migración E3 posterior, en cadena con el `head` efectivo al momento de implementarse:

1. `inventario_correccion_decisiones`: `id`, `solicitud_id` UNIQUE FK restrictiva, `decision` (`APPROVED/REJECTED`), `actor_usuario_id` FK, `decidido_en_utc` timestamptz, `motivo_decision`, `payload_resolucion` JSONB, `resultado_antes` JSONB, `resultado_despues` JSONB. Correlación con evento físico o maestro, `request_id` único de operación. No usar cascade-delete.
2. `inventario_ajustes_auditoria`: `solicitud_id` UNIQUE FK restrictiva, `inventario_id`, `sucursal_id`, `stock_anterior`, `stock_nuevo`, `delta_firmada`, `actor_usuario_id`, `ocurrido_en_utc`, `motivo`, referencia a decisión. CHECK `stock_nuevo >= 0` y `stock_anterior + delta_firmada = stock_nuevo`; FK compuesta de sucursal+inventario, bloqueo `FOR UPDATE`.
3. `inventario_maestro_cambios_auditoria`: `solicitud_id`, `inventario_id`, `campo` allowlist, valores JSONB antes/después, `actor_usuario_id`, `ocurrido_en_utc`, decisión relacionada. Si `campo=codigo_interno`, generar **también** el historial vigente `InventarioCodigoCorreccionORM` en la misma transacción, sin duplicar la regla de unicidad.
4. Caso hallazgo aplicado: evento de `alta/vinculación` con IDs de maestro y existencia, cantidad positiva o no negativa explícita, actor y fuente. La solicitud conserva `inventario_id=NULL` original, aun si el maestro creado se enlaza desde el evento.

No modificar o reinterpretar el enum V1 para resolver rápido una diferencia de conteo: rompería semántica y anulación. No alterar columnas de solicitud histórica para guardar el resultado en lugar de eventos adicionales.

## 5. Contratos API candidatos (no implementados)

- `POST /api/inventario/solicitudes/decisiones/lote`: cuerpo `{decision:"APPROVE"|"REJECT",solicitud_ids:[...],motivo_decision:"...",resoluciones_por_id:{...},idempotency_key:"uuid"}`. Límite inicial 10 IDs, válidos, únicos, misma competencia del actor.
- `GET /api/inventario/solicitudes/<id>/historial`: solo al alcance autorizado, entrega propuesta y eventos de resolución; no filtra por el lado del navegador.
- Lectura de acciones E3 disponibles/capacidades derivadas del backend para habilitar botones de manera informativa en Angular; el backend revalida independientemente en POST.

**Semántica de lote inicial sugerida: todo o nada.** Bloquear solicitudes por ID ascendente; después referencias oficiales en orden estable; validar todas y aplicar todas dentro del mismo commit. Si una falla: `409` con IDs/reason, ninguna autorizada. Evita mezcla oculta de éxitos y fracasos. Idempotencia de operación persistida: mismo UUID/payload regresa resultado previo, UUID reutilizado con otros datos `409`.

En E2 los botones continúan `disabled`; E3 debe activarlos **solo después** de guard, migración, transacción y QA, nunca por CSS.

## 6. QA mínimo antes de cambiar un registro oficial

- Actor sin JWT/rol/grant, GERENTE, GERENTE_REGIONAL, rol equivocado, sucursal ajena, clase de activo ajena: 401/403/404 sin filtración.
- Denegar **autoaprobación** incluso a administrador; rechazos requieren motivo y no cambian stock.
- Dos aprobaciones concurrentes de la misma solicitud; doble clic, mismo UUID/diferente payload; una sola transición y un solo ajuste.
- Lote con una solicitud obsoleta: rollback íntegro. Baseline de stock/maestro revalidado **después** de bloquear filas.
- Lote con decisiones sobre misma referencia: rechazar conflicto o computar validaciones determinísticas antes de aplicar; no sobrescribir el primer efecto.
- Auditoría demuestra aprobador, creador independiente, antes/después, fecha UTC, referencia, motivo y evento resultante.
- `QUANTITY_DIFFERENCE` 3→2: evento ajuste `-1`, stock final 2; **ninguna entrada/salida V1 falsa**.
- Código repetido (incluidos duplicados históricos), categoría/familia incompatible y maestro compartido sin autorización global: rechazo completo, sin cambios.
- `NOT_LOCATED` sin resolución explícita / `UNREGISTERED_FIND` sin metadatos suficientes: **no aprobado**, `PENDING` intacto.
- PostgreSQL real temporal con rollback, constraints/índices, migración up/down y regresiones Inventarios V1/E2, Tickets/PM según vínculo.
- Piloto únicamente en sucursal de QA autorizada; reconciliar datos y verificar trazabilidad antes de despliegue general.

## 7. Orden de implementación sin saltar gates

0. **Gate E2:** comprobar en UI el despliegue de PR #1117 (lista con checks), autorizar solo E2 como aceptado con QA visual de usuario; hasta entonces E3 solo documental.
1. **E3-P1:** cerrar matriz efectiva de permisos/competencia, resolver contradicción regional §7 vs E5, política de `NOT_LOCATED` y alta/vinculación para `UNREGISTERED_FIND`.
2. **E3-P2:** añadir tablas/historial de decisiones y ajustes con Alembic, ORM, índices, pruebas PostgreSQL. Sin endpoint de aplicar.
3. **E3-P3:** servicio de aplicación atómica por tipo + guard independiente + endpoints; pruebas de concurrencia/autoaprobación/regresión. Sin habilitar UI.
4. **E3-P4:** conectar los dos botones a prevalidación, confirmación y resultado del lote; QA visual y despliegue piloto controlado. `GERENTE_ROLLOUT=OFF`.
5. **E3-P5:** auditoría de QA y aceptación E3 antes de iniciar E4.

**No cambia código, BD, API, grants o frontend por este documento.** Mantenerlo en PR draft hasta ratificar las decisiones pendientes.
