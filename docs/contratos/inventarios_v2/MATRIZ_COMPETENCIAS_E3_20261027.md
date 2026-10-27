# Inventarios V2 — E3 · Matriz propuesta de competencias por clase de activo

**Fecha:** 2026-10-27  
**Estado:** PROPUESTA PARA RATIFICACIÓN, **NO IMPLEMENTADA / NO AUTORIZA GRANTS NI ROLLOUT**.  
**PR:** #1134 (DRAFT). **Gate:** §7 de `CONTRATO_INVENTARIOS_V2_AUDITORIA_GLOBAL.md`.  
**Objetivo:** no equiparar permiso de aprobar una corrección en una sucursal con competencia sobre *cualquier* clase de inventario.

## 1. Fuente de verdad e identificación de activos

- El modelo real `InventarioGeneral` tiene `tipo` como texto libre (no enum ni FK), además de `categoria_inventario_id`, `familia_equipo_id` y el texto legado `categoria`.
- El backend de Inventarios V1 diferencia departamentos: Mantenimiento (1) trabaja con **aparatos**, Sistemas (7) con **dispositivos**. El alta V1 reconoce `aparato/aparatos`, `sistema/sistemas`, `dispositivo/dispositivos` y, como valor por defecto, `producto`. **No se ha verificado el conjunto ni el volumen de valores presentes en la DB productiva.**
- Para una referencia existente se usará **exclusivamente `inventario_general.tipo` leído desde DB**, nunca el tipo/categoría enviados por el navegador, ni claims JWT. Comparar `trim + casefold/lower` con aliases explícitos.
- Para la primera fase de E3, la clase `APARATO` comprende solamente `aparato` y `aparatos` normalizados. El resto se considera **NO HABILITADO PARA REVISORES DE MANTENIMIENTO** hasta clasificación verificada. `sistema/sistemas/dispositivo/dispositivos` se tratan como dispositivos; `producto/productos` como productos; otros/sin tipo como **sin clasificar**.
- `familia_equipo_id` y `categoria_inventario_id` sirven para clasificación y diagnóstico, **no** otorgan acceso por sí mismos; los aparatos legados sin familia deben continuar siendo aparatos si `tipo` es válido. Una categoría de catálogo no debe convertir implícitamente un dispositivo en aparato.
- Registro con `tipo` ambiguo, nuevo o inconsistente: **fail closed** para el revisor limitado, revisión corporativa con grant y corrección de clasificación por proceso oficial.

## 2. Matriz funcional propuesta

| Clase real / tipo de solicitud | Administración corporativa con grant personal global | MANTENIMIENTO (dept 1) / COORDINADOR_MANTENIMIENTO (dept 1) con grant y sucursal M:N | Otros perfiles |
|---|---|---|---|
| APARATO · `QUANTITY_DIFFERENCE` | Sí | Sí, solo sucursal asignada | No |
| APARATO · `NOT_LOCATED` | Sí; `AJUSTAR_A_CERO` explícito | Sí, solo sucursal y `AJUSTAR_A_CERO` explícito | No |
| APARATO · `UNREGISTERED_FIND` | Sí; únicamente `VINCULAR_EXISTENTE` | Condicionado: provisional identifica clase aparato; destino oficial es aparato, con coincidencia física y sucursal asignada | No |
| Cualquier clase · `MASTER_FIELD` | Sí; competencia corporativa sobre maestro compartido | No, aun si el activo es aparato | No |
| DISPOSITIVO / SISTEMA · solicitudes de cantidad, ausencia o hallazgo | Sí | No; competencia ajena al departamento | No |
| PRODUCTO / otra clase / clase desconocida · solicitudes de cantidad, ausencia o hallazgo | Sí | No hasta política explícita | No |
| Cualquier clase · `REJECTED` | Según capacidad sobre esa solicitud y sin autoevaluarse | Solo si la **clase** corresponde a su competencia; rechazar tampoco da acceso general | No |

**Controles acumulativos**, incluso en celdas «Sí»: JWT firmado, usuario/rol/departamento leídos de DB, acción `inventory.correction_approve` y grant explícito vigente, deny prevalente, sucursal efectiva, autor distinto del decisor, límites de lote, baseline/identidad, locks y auditoría. `GERENTE`, `GERENTE_REGIONAL`, `SR_MANTENIMIENTO`, `AUX_MANTENIMIENTO`, `SISTEMAS`, `TECNICO` y otros roles **siguen sin aprobar E3** hasta contrato posterior. No crear grants automáticos por rol.

## 3. Casos delicados

1. **Hallazgo sin registro (`UNREGISTERED_FIND`).** No existe `inventario_id` al presentar E2. Para incluirlo en la bandeja limitada, el campo provisional `tipo` debe declarar inequívocamente aparato. Si falta o es ambiguo, queda **solo en bandeja corporativa**. Declarar aparato no basta para aprobar: el `inventario_id` destino de `VINCULAR_EXISTENTE` se verifica bajo lock contra `inventario_general.tipo` y la coincidencia física/documental, en la misma sucursal. Nunca `CREAR_NUEVO`.
2. **Valor de maestro.** `MASTER_FIELD` permanece reservado a administración corporativa con grant personal global, sin importar sucursal, categoría ni tipo; no se filtra solo visualmente.
3. **Dos clases en un mismo lote.** Si alguna fila no es elegible, denegar/rollback **todo el lote**, sin efectos parciales. El tipo oficial se revalida dentro de la transacción, no solo en el listado.
4. **Cambio de clasificación posterior.** Reconsultar el tipo oficial al decidir y al replay sensible; un cambio de clase no puede servir para eludir la política. Error de clasificación se corrige con una nueva solicitud autorizada, nunca reescribiendo la clase silenciosamente.
5. **Bandeja E3.** `GET /revision`, `GET /revision/<id>` y totales paginados deben filtrar la **misma capacidad efectiva en SQL**, incluyendo clase de activo: una tarjeta no debe mostrar dispositivos a un revisor de Mantenimiento y luego fallar en POST. En `POST /decisiones/lote`, los IDs fuera de clase/alcance no deben poder enumerarse (404 uniforme frente a inexistente); 403 para actor sin capacidad E3 y autoaprobación propia según contrato.
6. **Identidad dudosa.** `codigo_interno`, familia y nombre no conceden una competencia aunque coincidan. El revisor no puede corregir el campo maestro `tipo` mediante una solicitud de cantidad.

## 4. Implementación prevista — aún NO autorizada

- `backend/app/utils/inventory_correction_permissions.py`: ampliar política DB-backed para verificar clase del activo por solicitud, sin recibir «tipo de activo» arbitrario del cliente; conservar el comportamiento corporativo.
- `backend/app/routes/inventario_solicitudes_routes.py`: ampliar `_query_revision()` para aplicar la misma política de clase en SQL **antes** de paginar/contar. Para hallazgos provisionales, utilizar una expresión explícita sobre `hallazgo_provisional->>'tipo'` con fail closed.
- `backend/app/services/inventario_correccion_decisiones_service.py`: después de bloquear solicitudes y referencias, revalidar la clase del maestro original y destino vinculado, para `APPROVED` y `REJECTED`, incluidos los replays. Mantener transacción íntegra.
- `backend/tests/routes/test_inventario_e3_decisiones_pg.py` y `backend/tests/utils/test_inventory_correction_e3_permissions_pg.py`: fixture con APARATOS, DISPOSITIVOS, PRODUCTOS, tipo ambiguo, aparato sin familia, cambio posterior de clase, hallazgo declarado/indefinido, mezcla de lote e IDOR. Pruebas positivas y negativas en PostgreSQL temporal.
- No modificar HTML para lógica de permisos; no se requiere migración para esta **propuesta**, salvo que luego se ratifique modelar competencias como grants nuevos o catálogo formal.

## 5. Verificación de datos previa a ratificación (solo lectura, producción)

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

La consulta debe informar cuántas referencias activas reales serían excluidas por ambigüedad (no asumir valores basándose solo en fixtures). No subir datos sensibles, nombres o códigos de equipos al comentario si no hacen falta.

## 6. Ratificación requerida antes de escribir guard de clase

**Propuesta operativa para decidir:**
1. Mantenimiento y coordinación solo aprueban/rechazan ajustes de **aparatos** en sus sucursales; no autorizan dispositivos ni productos.
2. Hallazgos con tipo provisional ausente/ambiguo van a revisión corporativa; aparatos identificados requieren destino físico canónico también de tipo aparato.
3. ADMICORP puede revisar cualquier clase con grant personal global, salvo solicitudes propias; la revisión `MASTER_FIELD` es exclusivamente corporativa.
4. Reconfirmar que esta política describe las competencias reales con responsables de Mantenimiento y Sistemas. Hasta esa ratificación, **no habilitar grants, no hacer merge, no desplegar E3 y mantener PR DRAFT**.
