# Inventarios V2 — E3 · Matriz de competencias por clase de activo

**Fecha:** 2026-10-27  
**Estado:** COMPETENCIA FUNCIONAL RATIFICADA EN CONVERSACIÓN; **AÚN SIN GRANTS NI ROLLOUT**.  
**PR:** #1134 (DRAFT). **Gate:** §7 de `CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md`.  
**Objetivo:** no equiparar permiso de aprobar una corrección en una sucursal con competencia sobre *cualquier* clase de inventario.

## 1. Fuente de verdad e identificación de activos

- El modelo real `InventarioGeneral` tiene `tipo` como texto libre (no enum ni FK), además de `categoria_inventario_id`, `familia_equipo_id` y el texto legado `categoria`.
- El backend de Inventarios V1 diferencia departamentos: Mantenimiento (1) trabaja con **aparatos**, Sistemas (7) con **dispositivos**. El alta V1 reconoce `aparato/aparatos`, `sistema/sistemas`, `dispositivo/dispositivos` y, como valor por defecto, `producto`. **Consulta productiva de solo lectura comunicada el 27/10/2026:** `aparatos = 3,477` (2 sin familia), `dispositivos = 475` (475 sin familia); 3,952 referencias totales, sin otros tipos en el resultado recibido.
- Para una referencia existente se usará **exclusivamente `inventario_general.tipo` leído desde DB**, nunca el tipo/categoría enviados por el navegador, ni claims JWT. Comparar `trim + casefold/lower` con aliases explícitos.
- En E3, la clase `APARATO` comprende `aparato/aparatos` normalizados y corresponde a MANTENIMIENTO/COORDINADOR_MANTENIMIENTO (departamento 1). La clase `DISPOSITIVO` comprende `dispositivo/dispositivos/sistema/sistemas` normalizados y corresponde a SISTEMAS (departamento 7). Otro valor o tipo desconocido queda **sin competencia delegada** (solo corporativo). Cada rol operativo requiere grant explícito E3 y sucursal `usuario_sucursal` asignada; un grant `global` no amplía sus sucursales.
- `familia_equipo_id` y `categoria_inventario_id` sirven para clasificación y diagnóstico, **no** otorgan acceso por sí mismos; los aparatos legados sin familia deben continuar siendo aparatos si `tipo` es válido. Una categoría de catálogo no debe convertir implícitamente un dispositivo en aparato.
- Registro con `tipo` ambiguo, nuevo o inconsistente: **fail closed** para el revisor limitado, revisión corporativa con grant y corrección de clasificación por proceso oficial.

## 2. Matriz funcional ratificada (grants aún no habilitados)

| Clase real / tipo de solicitud | ADMICORP / administración con grant personal global | MANTENIMIENTO / COORDINADOR (depto. 1, grant + M:N) | SISTEMAS (depto. 7, grant + M:N) |
|---|---|---|---|
| APARATO · `QUANTITY_DIFFERENCE` | Sí | Sí, solo sucursal asignada | No |
| APARATO · `NOT_LOCATED` | Sí, con resolución explícita | Sí, con `AJUSTAR_A_CERO` y sucursal | No |
| APARATO · `UNREGISTERED_FIND` | Sí, con vinculación verificable | Sí, si provisional y destino oficial son aparatos | No |
| DISPOSITIVO · `QUANTITY_DIFFERENCE` | Sí | No | Sí, solo sucursal asignada |
| DISPOSITIVO · `NOT_LOCATED` | Sí, con resolución explícita | No | Sí, con `AJUSTAR_A_CERO` y sucursal |
| DISPOSITIVO · `UNREGISTERED_FIND` | Sí, con vinculación verificable | No | Sí, si provisional y destino oficial son dispositivos |
| Cualquier clase · `MASTER_FIELD` | Sí (maestro compartido) | No | No |
| Otra clase / tipo ausente o ambiguo | Sí (salvo solicitud propia) | No | No |
| Rechazo `REJECTED` de una solicitud | Misma competencia que aprobar, sin cambiar stock | Solo aparatos de su alcance | Solo dispositivos de su alcance |

**Controles acumulativos:** JWT firmado, rol y `department_id` leídos de DB, `inventory.correction_approve` con grant explícito vigente, deny prevalente, intersección con `usuario_sucursal` para todos los perfiles operativos, creador distinto del decisor, lote atómico, baseline/identidad física y auditoría. **SISTEMAS es autorizador candidato E3**, a diferencia de `TECNICO`, `SR_MANTENIMIENTO`, `AUX_MANTENIMIENTO`, `GERENTE` y `GERENTE_REGIONAL`, que permanecen denegados. No crear grants automáticos ni deducir facultades por poder escribir en V1.

## 3. Casos delicados

1. **Hallazgo sin registro (`UNREGISTERED_FIND`).** No existe `inventario_id` al presentar E2. Para incluirlo en la bandeja limitada, el campo provisional `tipo` debe declarar inequívocamente `aparatos` (Mantenimiento) o `dispositivos` (Sistemas). Si falta o es ambiguo, queda **solo en bandeja corporativa**. La etiqueta provisional no basta para aprobar: el `inventario_id` destino de `VINCULAR_EXISTENTE` se verifica bajo lock contra `inventario_general.tipo`, la coincidencia de clase y la identidad física/documental, en la misma sucursal. Nunca `CREAR_NUEVO`.
2. **Valor de maestro.** `MASTER_FIELD` permanece reservado a administración corporativa con grant personal global, sin importar sucursal, categoría ni tipo; no se filtra solo visualmente.
3. **Dos clases en un mismo lote.** Si alguna fila no es elegible, denegar/rollback **todo el lote**, sin efectos parciales. El tipo oficial se revalida dentro de la transacción, no solo en el listado.
4. **Cambio de clasificación posterior.** Reconsultar el tipo oficial al decidir y al replay sensible; un cambio de clase no puede servir para eludir la política. Error de clasificación se corrige con una nueva solicitud autorizada, nunca reescribiendo la clase silenciosamente.
5. **Bandeja E3.** `GET /revision`, `GET /revision/<id>` y totales paginados deben filtrar la **misma capacidad efectiva en SQL**, incluyendo clase de activo: una tarjeta no debe mostrar dispositivos a un revisor de Mantenimiento y luego fallar en POST. En `POST /decisiones/lote`, los IDs fuera de clase/alcance no deben poder enumerarse (404 uniforme frente a inexistente); 403 para actor sin capacidad E3 y autoaprobación propia según contrato.
6. **Identidad dudosa.** `codigo_interno`, familia y nombre no conceden una competencia aunque coincidan. El revisor no puede corregir el campo maestro `tipo` mediante una solicitud de cantidad.

## 4. Implementación preparada en PR DRAFT — SIN despliegue ni grants

- `backend/app/utils/inventory_correction_permissions.py`: política DB-backed por rol, departamento, sucursal M:N, clase del activo y grant, sin confiar en el JWT para competencia ni recibir una clase arbitraria del cliente.
- `backend/app/routes/inventario_solicitudes_routes.py`: `_query_revision()` filtra por clase del maestro o tipo provisional en SQL **antes** de paginar/contar/detallar; hallazgo sin tipo o ambiguo queda fuera de bandejas delegadas.
- `backend/app/services/inventario_correccion_decisiones_service.py`: decisión transaccional revalida clase de la referencia oficial (y del destino de vinculación) al autorizar/rechazar, antes y después de locks pertinentes; replay idempotente vuelve a verificar competencias y destino, sin doble aplicación.
- `backend/tests/routes/test_inventario_e3_decisiones_pg.py` y `backend/tests/utils/test_inventory_correction_e3_permissions_pg.py`: pruebas PostgreSQL temporal de aparatos y dispositivos sin familia, SISTEMAS depto. 7, grants/scope negativos, hallazgos declarados/sin tipo, clase cruzada, replay, lote mixto y filtrado de bandeja/detalle. Validar CI del último HEAD antes de concluir gate.
- Sin lógica de autorización en HTML; el esquema actual ya permite verificar rol/departamento, clase y grants, por lo que estos cambios no requieren migración nueva. **Ningún grant productivo concedido.**

## 5. Distribución productiva verificada y consulta adicional (solo lectura)

Ejecutar mediante una sesión PostgreSQL autorizada, sin alterar registros:

```sql
BEGIN TRANSACTION READ ONLY;

-- Distribución REAL de tipos canónicos y aparatos sin familia.
SELECT lower(btrim(coalesce(tipo, ''))) AS tipo_normalizado,
       count(*) AS referencias,
       count(*) FILTER (WHERE familia_equipo_id IS NULL) AS sin_familia
FROM inventario_general
GROUP BY 1
ORDER BY referencias DESC, tipo_normalizado;

-- Solicitudes E2 actualmente pendientes agrupadas por tipo y clase.
SELECT s.tipo AS clase_solicitud,
       CASE
         WHEN s.inventario_id IS NULL THEN lower(btrim(coalesce(s.hallazgo_provisional->>'tipo', '')))
         ELSE lower(btrim(coalesce(i.tipo, '')))
       END AS tipo_activo_normalizado,
       count(*) AS pendientes
FROM inventario_correccion_solicitudes s
LEFT JOIN inventario_general i ON i.id = s.inventario_id
WHERE s.estado = 'PENDING'
GROUP BY 1, 2
ORDER BY 1, 2;

COMMIT;
```

Resultado real comunicado: **3,477 aparatos (2 sin familia), 475 dispositivos (475 sin familia)**. No hay otros tipos en la distribución compartida; verificar de nuevo si cambia el catálogo. La segunda consulta de solicitudes PENDING por clase sigue siendo una verificación adicional opcional antes de habilitar grants. No subir datos sensibles, nombres o códigos de equipos al comentario si no hacen falta.

## 6. Ratificación y gate de implementación

**Competencia funcional confirmada el 27/10/2026:** aparatos → Mantenimiento/Coordinación; dispositivos → Sistemas; ambos → administración corporativa, siempre con grants E3 y sin autoaprobación.

**Política conservadora para la implementación:**
1. Mantenimiento/Coordinación (depto. 1) y Sistemas (depto. 7) requieren `usuario_sucursal` M:N, grant válido E3 y validación del tipo oficial en el backend.
2. El hallazgo provisional sin tipo o ambiguo es solo corporativo; vinculación permitida únicamente entre el tipo provisional y la clase oficial de destino (aparato con aparato, dispositivo con dispositivo).
3. Las correcciones `MASTER_FIELD` afectan el maestro global y siguen siendo corporativas; no se elevan por departamento ni por un grant global de un rol scoped.
4. Conservar PR DRAFT y sin grants productivos hasta QA PostgreSQL, auditoría final, ratificación de ajustes a cero y vinculación, y autorización explícita de rollout.
