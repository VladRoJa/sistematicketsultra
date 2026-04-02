Contrato global de Warehouse — Suite Ultra
1. Propósito

Warehouse es la plataforma interna de datos de Suite Ultra para:

capturar información desde múltiples fuentes
preservarla documentalmente
estructurarla de forma trazable
normalizarla por dominio de negocio
servirla para reportes, consultas, dashboards e IA

En términos simples:

Warehouse debe convertirse en el depósito consultable de información corporativa de Ultra, para que la inteligencia de negocio viva dentro de Suite y no dispersa entre excels, sistemas externos y procesos manuales.

2. Visión norte

La visión final no es solo “guardar reportes”.

La visión final es:

que Ultra pueda consultar su operación desde Suite, generar reportes como el Track bajo demanda, consumir dashboards sin depender de descargas manuales y, más adelante, hacer preguntas en lenguaje natural a una capa de datos curada y gobernada.

Eso incluye eventualmente:

generación de reportes desde Suite
dashboards operativos y ejecutivos
capa de consultas por query
IA tipo J.A.R.V.I.S. que traduzca preguntas a consultas seguras
3. Principios rectores
3.1 Raw first, structured later

Siempre se preserva primero el artifact documental o contractual fuente, y después se estructura.

3.2 Trazabilidad total

Todo dato estructurado debe poder amarrarse a:

source
report_type
upload documental
fecha de negocio
snapshot estructurado
3.3 Sin magia

Nada debe depender de lógica escondida o atajos frágiles. Cada capa debe tener responsabilidad clara.

3.4 Reuso antes que reinvención

Si ya existe un pipeline validado, se extiende. No se abre framework nuevo por reporte.

3.5 Capas separadas

Warehouse debe distinguir claramente entre:

documental/raw
estructurado por reporte
curado de negocio
consumo
IA
3.6 La IA no consulta raw directo

La IA futura debe consultar datasets/marts curados, no excels crudos ni tablas ambiguas.

4. Alcance global de Warehouse
4.1 Capa documental / raw

Responsable de:

recibir artifacts internos o manuales
conservar archivo fuente o artifact contractual
registrar catálogo y metadata
auditar uploads
permitir descarga/revisión
4.2 Capa estructurada por reporte

Responsable de:

parsear reportes específicos
crear snapshots estructurados
insertar rows de negocio
garantizar idempotencia por upload
resolver canonicalidad por scope
4.3 Capa curada / marts de negocio

Responsable de:

unificar múltiples reportes estructurados
normalizar métricas y dimensiones
exponer datasets estables para negocio
servir consultas corporativas
4.4 Capa de consumo

Responsable de:

generar reportes como el Track
alimentar dashboards
exponer consultas dentro de Suite
evitar dependencia de descargas manuales
4.5 Capa IA

Responsable de:

traducir preguntas a consultas seguras
usar solo datasets aprobados
responder con trazabilidad
respetar permisos y gobierno del dato
5. Contrato técnico por capa
5.1 Documental

Cada upload documental debe tener:

report_type
archivo o artifact contractual
periodo documental resuelto
auditoría
vínculo a fuente
5.2 Estructurado

Cada reporte estructurado debe tener:

parser puro
snapshots header + rows
idempotencia por warehouse_upload_id
policy de canonicalidad
repository
ingestion service
dispatch desde orquestador
5.3 Curado

Cada mart/dataset curado debe tener:

definición semántica estable
fuentes estructuradas explícitas
reglas de negocio claras
versionado lógico de métricas si cambia semántica
5.4 Consumo

Cada módulo consumidor debe consultar:

snapshots canónicos
o marts curados
nunca lógica ad hoc sobre raw sin contrato
5.5 IA

Toda capa IA futura debe usar:

esquemas aprobados
catálogo de métricas/dimensiones
trazabilidad de consultas
guardrails
6. Estado actual real del contrato

Aquí ya no hablo de aspiración, sino de estado real.

6.1 Lo que ya está cerrado
F1 — Capa documental/raw

Cerrada.

Ya existe:

catálogo de reportes
uploads documentales
storage
loader
audit
trazabilidad básica
Patrón estructurado reusable

Cerrado.

Ya existe el carril completo:

parser
modelos
migración
repository
ingestion service
runtime hooks
dispatch estructurado
validación en BD
idempotencia
Reportes estructurados ya integrados

Cerrados funcionalmente:

reporte_direccion
kpi_desempeno
kpi_ventas_nuevos_socios
Canonicalidad inicial diaria para KPIs

Ya definida y validada:

scope por report_type_key + business_date + snapshot_kind
política: latest successful daily snapshot wins
6.2 Lo que aún no está cerrado
Cobertura mínima del Track

No está cerrada.

Faltan todavía 3 reportes crudos por integrar para poder decir que Warehouse ya puede alimentar el Track completo.

Mart del Track

No toca todavía, porque aún no existe cobertura mínima de insumos.

Consumo dentro de Suite

Todavía no existe:

módulo “Generar Track”
dashboards sobre marts
consulta unificada dentro de Suite
IA/J.A.R.V.I.S.

Todavía no existe:

capa semántica aprobada
query service de negocio
traducción NL → query segura
7. Diagnóstico actual del proyecto

Hoy Warehouse ya no es una idea abstracta.

Hoy Warehouse ya es:

una base documental sólida + una plataforma real de estructuración reusable por reporte

Eso es muchísimo avance.

Pero todavía no es:

lago curado de negocio completo
motor del Track
módulo de consulta
IA corporativa

Entonces el estado correcto es:

Ya logramos
fundación
patrón
primeros pipelines productivos
Falta lograr
cobertura mínima del dominio Track
capa curada
consumo
IA
8. Roadmap maestro actualizado
Etapa A — Fundación de Warehouse

Objetivo:

raw/documental
catálogo
uploads
audit
loaders

Estado: cerrada

Etapa B — Patrón estructurado reusable

Objetivo:

demostrar que un reporte puede pasar de raw a snapshot estructurado con trazabilidad e idempotencia

Estado: cerrada

Validado con:

reporte_direccion
kpi_desempeno
kpi_ventas_nuevos_socios
Etapa C — Cobertura mínima del Track

Objetivo:

integrar todos los reportes crudos necesarios para alimentar el Track

Estado: en progreso

Ya cubierto:

reporte_direccion
kpi_desempeno
kpi_ventas_nuevos_socios

Pendiente:

3 reportes crudos más
Etapa D — Mart / capa curada del Track

Objetivo:

construir el dataset canónico que permita generar el Track desde Suite

Estado: pendiente
No toca todavía

Etapa E — Consumo dentro de Suite

Objetivo:

generar Track desde UI
dashboards sin descargar excels
consultas de negocio

Estado: pendiente

Etapa F — IA / J.A.R.V.I.S.

Objetivo:

preguntas en lenguaje natural
generación segura de queries
respuestas trazables sobre datasets curados

Estado: pendiente

9. Orden correcto de trabajo desde hoy

Con el contrato ya actualizado, el orden correcto es:

cerrar cobertura mínima del Track
luego mart/capa curada del Track
luego consumo dentro de Suite
luego IA

No al revés.

10. Regla de fragmentación futura en features

A partir de ahora, las features se deberían fragmentar así:

Tipo 1 — Feature de integración de reporte crudo

Para cada reporte faltante:

contrato documental
parser
modelos
migración
repository
ingestion service
hooks
orquestador
validación BD
idempotencia
canonicalidad si aplica
Tipo 2 — Feature de capa curada

Cuando ya exista cobertura suficiente:

contrato del mart
definición de métricas
consolidación de snapshots canónicos
querys/vistas/datasets
Tipo 3 — Feature de consumo
endpoint o módulo “Generar Track”
dashboard
consultas UI
Tipo 4 — Feature de IA
semantic layer
query generation segura
auditoría
guardrails
11. Qué sí cuenta como progreso real

Para la bitácora, yo mediría avance así:

Progreso fuerte
un reporte nuevo queda integrado end-to-end
un mart nuevo queda definido y consultable
una vista de negocio deja de depender de excel manual
una pregunta de negocio puede responderse desde Suite
Progreso débil
renombres
refactors cosméticos
wiring sin cierre funcional
12. Bitácora actual resumida
Cerrado
F1 documental/raw
reporte_direccion estructurado
kpi_desempeno estructurado
kpi_ventas_nuevos_socios estructurado
idempotencia F3/F4
canonicalidad diaria inicial para KPIs
En progreso
cobertura mínima del Track
Pendiente
3 reportes crudos del Track
mart del Track
módulo “Generar Track”
dashboards
IA/J.A.R.V.I.S.