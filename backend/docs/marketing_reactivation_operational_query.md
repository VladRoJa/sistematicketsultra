# Consulta operativa de Marketing > Reactivación

## Semántica

`socios_vencidos_cartera` continúa siendo el histórico inmutable de episodios.
El universo operativo selecciona primero una sola fila por
`(sucursal_key, pin)` mediante:

```sql
row_number() over (
  partition by sucursal_key, pin
  order by fecha_vencimiento_date desc, id desc
)
```

Sólo después de conservar `episode_rank = 1` se aplican `date_from` y
`date_to`. Por eso consultar un rango antiguo no revive un episodio cuando el
mismo miembro y sucursal tienen uno globalmente posterior.

La consulta reusable está en
`app/services/marketing_reactivation_candidate_query.py`. Sucursal, tarifa,
grupo tarifario y búsqueda se componen en SQL. El estado operativo se aplica
después del resolver porque depende del snapshot activo y de la evidencia del
run canónico iVentas seleccionado. `NO_MATCH_CURRENT_IVENTAS_RUN` conserva su
significado: no apareció en ese run; no significa que nunca haya sido
contactado.

## Índice

La migración `f7c9a2d4e6b1_add_reactivation_operational_index.py` agrega:

```sql
create index ix_socios_vencidos_cartera_operational_latest
on socios_vencidos_cartera (
  sucursal_key,
  pin,
  fecha_vencimiento_date desc,
  id desc
);
```

El orden del índice coincide con la partición y desempate del window. Esto
permite al planificador recorrer los episodios ya agrupados/ordenados y evita
descubrir el episodio más reciente en Python. La consulta debe inspeccionarse
con datos representativos después de aplicar la migración; PostgreSQL puede
elegir un plan distinto según cardinalidad y estadísticas.

## Inspección con EXPLAIN ANALYZE

Ejecutar sólo en una base local o de pruebas con datos no sensibles. Sustituir
las fechas ficticias según la distribución que se quiera medir:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT c.*
FROM socios_vencidos_cartera AS c
JOIN (
  SELECT
    id AS episode_id,
    row_number() OVER (
      PARTITION BY sucursal_key, pin
      ORDER BY fecha_vencimiento_date DESC, id DESC
    ) AS episode_rank
  FROM socios_vencidos_cartera
) AS ranked ON ranked.episode_id = c.id
WHERE ranked.episode_rank = 1
  AND c.fecha_vencimiento_date BETWEEN DATE '2026-01-01' AND DATE '2026-12-31'
ORDER BY c.fecha_vencimiento_date DESC NULLS LAST, c.id DESC
LIMIT 50;
```

Antes de comparar tiempos, ejecutar `ANALYZE socios_vencidos_cartera` en esa
base de prueba. Verificar en el plan el uso del índice
`ix_socios_vencidos_cartera_operational_latest`, filas leídas, buffers y si hay
un sort externo. No copiar al repositorio valores de socios ni planes que
incluyan datos internos.

## Orden soportado

La allowlist acepta `nombre`, `pin`, `sucursal`, `fecha_vencimiento`,
`fecha_ultimo_pago`, `tarifa` y `telefono`, siempre con `id DESC` como desempate.
`status` y `latest_outbound_at_utc` no se aceptan como sort: son valores
derivados durante la resolución por lotes y ordenarlos globalmente exigiría
materializar todo el resultado o persistir un mart. El frontend los muestra
sin control de orden.

## Escalabilidad y límites

Hay tres flujos deliberadamente separados:

1. `GET /api/marketing/reactivation/candidates` devuelve filas interactivas.
   Con `operational_status=ALL` ejecuta un `COUNT(*)` exacto sobre la relación
   SQL, aplica `LIMIT/OFFSET` y resuelve Activos/iVentas sólo para la página.
   Para conservar `DUPLICATE_VENCIDO_PHONE`, toma únicamente los teléfonos
   MX10 de filas visibles que quedaron `NOT_FOUND`, busca posibles pares por
   `telefono_digits` en sus formas MX10, `52 + MX10` y `521 + MX10`, y resuelve
   Activos sólo para esos pares.
2. `GET /api/marketing/reactivation/candidates/summary` calcula los agregados
   del segmento completo. Puede hacer dos recorridos streaming: el primero
   cuenta teléfonos de filas `NOT_FOUND` y el segundo resuelve y acumula
   `status_counts` y `reason_counts`. No conserva una lista de N filas
   serializadas y no depende de página, tamaño ni orden.
3. Preview, creación y exportación de campañas usan un flujo completo propio.
   Recorren todo el segmento porque deben preservar duplicados y cooldown
   globales, decidir todos los destinatarios y congelarlos. Nunca dependen de
   la página o cursor visibles.

`yield_per()` limita memoria, pero no reduce la cantidad de filas evaluadas.
Por eso ya no se usa un escaneo completo dentro del GET normal: sirve sólo en
summary y campañas, donde el trabajo O(N) es parte del resultado solicitado.

Los filtros derivados (`WORK_PENDING`, estados de contacto, revisión y
activos) usan cursor. Cada consulta parte de un cursor opaco ligado al
segmento, periodo iVentas y orden; lee lotes acotados en orden estable
`sort, id DESC`, resuelve el lote y se detiene al reunir `page_size` o agotar
el universo. `next_cursor` continúa después de la última coincidencia de la
página, de modo que no se omiten filas ya leídas dentro del mismo lote. En
este flujo `pagination.total` y `total_pages` son `null`: el total exacto viene
del endpoint de summary. `has_next` indica que existe un cursor de
continuación; el summary es la fuente exacta para habilitar la navegación.
No se soporta salto aleatorio eficiente a páginas profundas de un estado
derivado.

El snapshot Activos se sigue cargando completo una vez por request para
construir los índices Python del matcher actual. Esto conserva exactamente la
semántica de cardinalidad y conflicto vigente. Es un costo conocido que debe
medirse con el volumen real; no se agregó cache ni tabla materializada sin esa
evidencia.

Después de cargar datos representativos se recomienda ejecutar `EXPLAIN
ANALYZE` para el `COUNT`, la página ordenada, la continuación por cursor y la
búsqueda de variantes telefónicas. Deben revisarse filas leídas, buffers,
sorts externos y uso de los índices, sin registrar datos internos en el
repositorio.
