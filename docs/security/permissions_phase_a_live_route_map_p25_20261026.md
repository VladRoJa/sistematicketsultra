# Suite Ultra — Fase A P25: conciliación del mapa de rutas VIGENTE
**Corte de código:** 2026-10-26, `main` base `2a3069d61ee42f4eb1910daf35b3bf70acbffe14`.

## Problema que resuelve

Las pruebas [P21](../../backend/tests/routes/test_permissions_phase_a_route_coverage.py) y [P22](../../backend/tests/routes/test_permissions_phase_a_unmapped_mutations_p22.py) comparan `Flask.app.url_map` contra la **migración semilla histórica** `7b8c9d0e1f2a`. P22 señaló **350 identidades sin coincidencia exacta con el seed**: 241 GET y 109 mutaciones (95 POST, 13 PUT, 1 PATCH). No significa que 350 rutas estén públicas, sin JWT, sin guard o ausentes de la base vigente. Tampoco significa que una fila del catálogo sea enforcement.

La pregunta pendiente es distinta: **¿cuánto coincide el mapa actual almacenado en PostgreSQL con los handlers que registra esta versión de Flask?**

## Entrega de P25

`backend/app/utils/permission_route_inventory.py` es un diagnóstico opcional **solo de ejecución manual**, no tiene endpoints, background jobs, escritura SQL ni cambios en `permissions_catalog_routes.py`.

- Censa `app.url_map` con GET/POST/PUT/PATCH/DELETE (ignora OPTIONS automático y rutas no `/api/`).
- Abre una conexión SQLAlchemy a PostgreSQL y ejecuta **`SET TRANSACTION READ ONLY` como primera instrucción** antes del `SELECT` de las columnas descriptivas de `permission_route_map`.
- Ejecuta `ROLLBACK` y cierra la conexión incluso ante error; no lee `users`, grants, roles o PII, no modifica una fila de la base.
- Compara por método + regla de ruta + nombre de endpoint Flask. Si el endpoint registrado tiene un alias, compara contra el nombre de la función real, tal como P21 documentó para `admin_put_sucursales_usuario`.
- Produce JSON con estadísticas por módulo/familia, método y clasificación, lista priorizada de mutaciones no conciliadas y filas sin método/ruta vigente.

| Clasificación | Significado técnico (NO permiso) |
|---|---|
| `exact` | Método, ruta y endpoint del catálogo activo coinciden |
| `handler_alias` | Coincide la función Python pero Flask registró otro alias de endpoint |
| `handler_mismatch` | Método y ruta existen en catálogo activo, pero el handler registrado difiere |
| `catalog_inactive` | Método y ruta Flask existen; solo hay entradas inactivas en el catálogo |
| `not_cataloged` | El método+ruta Flask no tiene entrada en `permission_route_map` vigente |
| `catalog_only_method_routes` | Entrada de catálogo para un método+ruta que no existe en el registro Flask |

**Importante:** `current_guard`, `review_status` y `current_scope` son **anotaciones del catálogo**, no evidencia de que un guard sea ejecutado. Incluso un registro `exact` exige pruebas de autorización por actor/recurso antes de afirmar paridad. La ausencia en el mapa tampoco demuestra bypass. P25 **no añade automáticamente acciones ni mapeos** y no habilita un resolvedor global.

## Cómo obtener una fotografía de producción después de aprobar el PR

Primero fusionar el PR por el flujo normal del repo y preparar una imagen `backend` que incluya el nuevo módulo. No editar código manualmente en el servidor. Este milestone no requiere migraciones; actualizar/reconstruir `backend` se realiza solo bajo la autorización de despliegue habitual.

Con la imagen correspondiente ejecutándose y desde el directorio de Compose:

```bash
# Solo lee el mapa; no invoca HTTP ni mutaciones.
docker compose exec -T backend python -m app.utils.permission_route_inventory > /tmp/permissions-route-map-p25.json
```

La salida es un JSON con **metadatos técnicos de rutas**, sin usuarios ni contraseñas; aun así debe resguardarse internamente. El script falla sin PostgreSQL y exige transacción READ ONLY. Ejecutarlo una vez es suficiente para obtener una fotografía reproducible; repetirlo tras cambios de rutas o migraciones puede detectar divergencias.

Interpretar `by_classification`, `by_family`, `unreviewed_mutations` y `catalog_only_method_routes`. La lista de prioridad se ordena primero por familias como Requisiciones, Marketing, Contact Center y Tickets, **solo para revisar**, no para afirmar que esas rutas son más inseguras.

## Validación y límites de este PR

`backend/tests/routes/test_permissions_phase_a_live_map_reconcile_p25.py` prueba clasificaciones, alias reales, entradas inactivas, handler drift, identidades duplicadas, que el inventario no ejecute handlers y que la lectura del catálogo exija PostgreSQL y ejecute la transacción read-only y rollback aun ante errores. El workflow incluye las regresiones P21/P22.

**CI no se conecta a producción.** Las cifras del mapa vigente NO están conocidas hasta que se ejecute el comando autorizado sobre el entorno final. No se presumirá que el seed antiguo sea la DB actual. El próximo trabajo de Fase A sería revisar cada discrepancia de alto impacto contra el guard real (incluidas rutas delegadas a servicios) y proponer cambios de catálogo mediante su propia migración revisada, nunca desde este reporte.

### Estado Fase A

Issue [#1053](https://github.com/VladRoJa/sistematicketsultra/issues/1053) permanece abierto. El contrato general continúa en PR documental [#1058](https://github.com/VladRoJa/sistematicketsultra/pull/1058). Resolvedor global y grants como enforcement siguen OFF. No se autoriza modificación de permisos productivos por el mero resultado del diagnóstico.
