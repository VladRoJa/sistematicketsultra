Bitácora maestra — Etapa C
Cobertura mínima del Track de Ventas
Objetivo de la etapa

Completar la integración estructurada de todos los reportes crudos mínimos necesarios para poder construir después el mart del Track.

Regla de cierre de la etapa

La Etapa C solo se considera cerrada cuando:

todos los reportes mínimos del Track estén integrados end-to-end
cada reporte tenga:
upload documental
parser
snapshot + rows
repository
ingestion service
dispatch
validación en BD
idempotencia
ya sea posible empezar a diseñar el mart del Track sin huecos funcionales
Estado actual de la Etapa C
Ya integrados
C1 — reporte_direccion

Estado: cerrado

C2 — kpi_desempeno

Estado: cerrado

C3 — kpi_ventas_nuevos_socios

Estado: cerrado

Pendientes
C4 — Reporte faltante 1 del Track

Estado: pendiente

C5 — Reporte faltante 2 del Track

Estado: pendiente

C6 — Reporte faltante 3 del Track

Estado: pendiente

Formato de feature reusable para cada reporte faltante

Cada una de las features C4, C5 y C6 debería seguir este contrato.

Alcance

Integrar un reporte crudo nuevo al pipeline estructurado de Warehouse.

Entregables mínimos
contrato documental cerrado
parser puro
modelos ORM
migración
repository
ingestion service
runtime hooks
dispatch en orquestador
prueba end-to-end
validación en BD
prueba de idempotencia
canonicalidad si aplica
Criterio de cierre

El reporte nuevo debe terminar en:

job_status = ingested
snapshot persistido
rows persistidas
idempotencia validada
Tablero de progreso sugerido
C4 — Reporte faltante 1 del Track
Objetivo

Integrar el siguiente reporte crítico del Track.

Subpasos
contrato documental
decisión del artifact contractual
parser
modelos
migración
repository
ingestion service
hooks
orquestador
validación BD
idempotencia
Estado actual

Pendiente

C5 — Reporte faltante 2 del Track
Objetivo

Integrar el siguiente reporte necesario para completar cobertura del Track.

Estado actual

Pendiente

C6 — Reporte faltante 3 del Track
Objetivo

Completar la cobertura mínima restante del Track.

Estado actual

Pendiente

Qué viene después de cerrar C4-C6
Etapa D — Mart del Track

Solo empieza cuando C4, C5 y C6 estén cerradas.

Objetivo

Construir la capa curada/canónica del Track a partir de snapshots estructurados.

Etapa E — Consumo dentro de Suite
generar Track desde UI
dashboards
consultas sin descargar
Etapa F — IA / J.A.R.V.I.S.
preguntas en lenguaje natural
generación segura de querys
respuestas trazables