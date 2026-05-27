Sí, **cerramos contrato**. Ya no veo un bloqueo conceptual grande. Lo que queda son dudas operativas para implementación, pero ya pueden resolverse dentro de F1.1 sin reabrir el diseño general.

Abajo te dejo el **contrato final completo v1.0**.

---

# Suite Ultra — Contrato Funcional v1.0

## Módulo de Planeación Comercial, Proyecciones, Tendencias y Metas Futuras

## 0. Decisión de cierre

Este contrato queda cerrado como base funcional para el módulo de **Planeación Comercial / Proyecciones / Tendencias / Metas Futuras**.

No se inicia programando todavía.
El siguiente paso correcto será abrir una nueva conversación de implementación para **F1.1 — Auditoría técnica y contrato de modelo DB/backend**.

Este contrato parte de la definición inicial del frente #7: analizar histórico, calcular tendencias, proyectar metas, simular escenarios, justificar ajustes y aprobar metas oficiales/canónicas con trazabilidad. 

---

# 1. Objetivo del módulo

Crear dentro de Suite Ultra un módulo formal de **Planeación Comercial** que permita transformar el proceso actual basado en Excel/Perico, criterio de junta y carga manual hacia Track en un flujo sostenible, auditable y controlado.

El módulo debe permitir:

* analizar histórico;
* calcular tendencias;
* simular escenarios;
* proyectar metas futuras;
* justificar ajustes manuales/contextuales;
* proponer metas;
* aprobar metas oficiales;
* versionar cambios;
* auditar decisiones;
* configurar parámetros del modelo;
* publicar metas aprobadas hacia Track.

La meta no es copiar el Excel.

La meta es convertir el proceso actual en una capacidad formal de Suite Ultra.

La filosofía correcta es:

```text
Suite no reemplaza la junta.
Suite prepara mejor la junta, explica los números, documenta los criterios y convierte la decisión en una meta oficial trazable.
```

---

# 2. Contexto actual

Suite Ultra ya cuenta con:

* Warehouse;
* Track;
* snapshots;
* canonicalidad;
* alias de sucursal;
* daily mart;
* ingreso real base;
* ingreso real agregadora;
* ingreso real total;
* metas FAYCGO;
* clientes nuevos;
* sucursales;
* regiones;
* datos diarios/mensuales.

Actualmente existe un Excel conocido informalmente como **Perico**.

Por lo que comentaste, “Perico” probablemente no es una entidad formal del negocio. Parece más bien un nombre interno/informal, posiblemente por los colores o por costumbre.

Por eso, dentro de Suite el módulo no debe llamarse “Perico”.

Nombres recomendados:

```text
Planeación Comercial
Proyecciones y Metas
Metas Comerciales
Planeación Track
Forecast & Targets
```

---

# 3. Proceso actual detectado

El proceso actual funciona conceptualmente así:

```text
Histórico + datos operativos
→ Excel / Perico
→ revisión y ajustes en junta
→ archivo de metas para Track
→ ingesta a Track
→ Track usa metas mensuales
```

Los ajustes manuales no son arbitrarios.

Representan drivers reales del negocio, como:

* vacaciones;
* campañas;
* escuelas cercanas;
* COBACH detrás de Villa Verde;
* público objetivo cercano;
* condiciones locales;
* capacidad comercial;
* competencia;
* cambio de gerente;
* CAPEX;
* eventos;
* riesgos operativos.

Los ajustes los define una junta entre:

```text
Edmundo
Julián
Fabián
```

Esto es importante porque la herramienta no debe presentar los ajustes como caprichos, sino como **criterios de negocio documentados**.

---

# 4. Qué ya existe técnicamente

Ya existe infraestructura para metas mensuales de Track.

Actualmente tienes servicios para:

* parsear archivo de metas mensuales;
* validar columnas requeridas;
* convertir enteros y decimales;
* validar `sucursal_canon`;
* validar que la sucursal exista en `track_branch_catalog`;
* validar duplicados;
* ingerir desde archivo o desde `warehouse_upload_id`;
* guardar en `TrackMonthlyTargetORM`;
* hacer upsert individual/bulk;
* manejar `is_active` para desactivar una meta anterior y activar una nueva por mes+sucursal.   

Campos actuales del target mensual:

```text
target_month
sucursal_canon
m2_sin_circulaciones
usuarios_inicio_mes
proyeccion_usuarios_cierre_mes
meta_faycgo_mes
meta_clientes_nuevos_mes
meta_reactivaciones_mes
meta_bajas_mes
meta_nuevos_domiciliados_mes
meta_arpu_mes
meta_venta_tienda_mes
notes
is_active
```

Conclusión:

```text
El problema ya no es “cómo subir metas a Track”.
El problema nuevo es “cómo nacen, se explican, se aprueban, se versionan y se publican esas metas”.
```

---

# 5. Principio rector

Las metas oficiales son información sensible.

Una meta oficial no debe:

* editarse silenciosamente;
* sobrescribirse sin historial;
* modificarse sin permisos;
* mezclarse con escenarios simulados;
* aprobarse sin contexto;
* depender de fórmulas escondidas;
* quedar quemada en código;
* perder trazabilidad.

Toda meta aprobada debe registrar:

* mes;
* sucursal o paquete mensual;
* valor exacto aprobado;
* escenario base;
* variables usadas;
* parámetros del modelo usados;
* ajustes manuales;
* motivo/contexto;
* usuario que propone;
* usuario que aprueba;
* fecha/hora;
* versión;
* si reemplaza una versión anterior;
* fuente;
* evento de auditoría.

La regla crítica inicial era justamente que las metas oficiales no se editen silenciosamente, no se sobrescriban sin historial y tengan permisos, confirmación, auditoría, trazabilidad y versionado. 

---

# 6. Concepto central del módulo

El módulo debe separar claramente estas capas:

```text
Configuración del modelo
→ Histórico
→ Tendencias
→ Escenarios
→ Ajustes
→ Propuesta
→ Revisión
→ Aprobación
→ Meta canónica
→ Publicación a Track
```

La diferencia conceptual es obligatoria:

```text
Escenario = simulación
Propuesta = posible meta
Meta aprobada = decisión formal
Meta canónica = valor oficial que consume Track
```

Track no debe consumir escenarios ni borradores.

Track solo debe consumir metas aprobadas/canónicas.

---

# 7. Decisión UX principal

El módulo tendrá **dos experiencias separadas**.

No será una sola pantalla responsiva intentando servir para todo.

## 7.1 Escritorio

La versión de escritorio será para análisis y construcción.

Aquí viven:

* tabla por sucursal;
* histórico;
* tendencias;
* escenarios;
* variables;
* fórmulas/reglas visibles;
* parámetros del modelo;
* ajustes manuales;
* gráficos;
* comparativos;
* comentarios;
* simulación;
* preparación de junta;
* generación de propuesta;
* revisión completa.

La computadora es para:

```text
analizar → simular → justificar → proponer
```

## 7.2 Móvil

La versión móvil será solo para aprobación ejecutiva.

No será simulador.

No permitirá edición avanzada.

Debe responder esta pregunta:

```text
¿Apruebas esta meta oficial, sí o no?
```

Pero con contexto suficiente para no aprobar a ciegas.

Ejemplo:

```text
Meta propuesta — Villa Verde
Mes: Junio 2026

Meta ingreso total: $872,432.18
Vs mes anterior: +8.4%
Vs escenario realista: +3.1%
Escenario usado: Ajustado

Ajustes relevantes:
+60 ventas nuevas por vacaciones + COBACH cercano

Riesgo:
Meta agresiva si no hay campaña activa.

Propuesto por: Vladimir
Aprobación requerida: Fabián

[Autorizar] [Rechazar]
```

La vista móvil no debe mostrar todo el simulador. Debe mostrar solo lo necesario para decidir: sucursal, mes, meta propuesta, diferencia vs mes anterior, diferencia vs escenario, ajustes relevantes, riesgos, proponente, autorizar, rechazar y comentario obligatorio si rechaza. 

---

# 8. Alcance MVP

Como ya existe ingesta operativa de metas hacia Track, el MVP no debe empezar por “subir el Excel”.

El MVP debe empezar por la **capa de gobierno de metas**.

## F1 — Governance de metas comerciales

El MVP debe incluir:

1. Crear paquete mensual de metas.
2. Importar o tomar metas desde la infraestructura existente.
3. Agrupar metas por mes.
4. Mostrar resumen por sucursal.
5. Permitir ajustes manuales con motivo.
6. Permitir guardar parámetros usados por el modelo.
7. Permitir enviar paquete a revisión.
8. Permitir aprobación mensual global.
9. Permitir rechazo con comentario obligatorio.
10. Permitir cambios puntuales por sucursal.
11. Versionar cada aprobación/cambio.
12. Auditar todo el flujo.
13. Publicar metas aprobadas hacia `TrackMonthlyTargetORM`.
14. Mantener Track consumiendo una sola meta activa/canónica por mes+sucursal.

---

# 9. Qué NO entra en MVP

No entra en F1:

* simulador avanzado con sliders complejos;
* machine learning;
* predicción automática cerrada;
* sustitución total del Excel desde el día uno;
* integración completa de usuarios TotalPass;
* aprobaciones multi-nivel demasiado complejas;
* notificaciones avanzadas;
* edición móvil de variables;
* fórmulas libres tipo Excel;
* cambios estructurales sin versión;
* publicación automática sin aprobación;
* dashboards ejecutivos altamente visuales.

F1 debe ser gobierno, trazabilidad y publicación controlada.

---

# 10. Datos disponibles para tendencias

Se tienen datos desde **septiembre 2025**.

Eso sí permite construir tendencias útiles para corto plazo.

Sí se puede analizar:

* ingreso real base;
* ingreso real agregadora;
* ingreso real total;
* clientes nuevos;
* reactivaciones;
* bajas;
* domiciliados;
* usuarios activos;
* usuarios inicio/cierre;
* ARPU;
* venta tienda;
* ocupación;
* cumplimiento contra meta.

Pero no se debe vender como estacionalidad anual completa.

Con datos desde septiembre 2025 se puede decir:

```text
Esta sucursal viene subiendo.
Esta sucursal viene cayendo.
Esta sucursal está estable.
Esta sucursal tiene ARPU fuerte.
Esta sucursal tiene bajas altas.
Esta meta está muy arriba de su tendencia reciente.
```

Pero todavía no se puede afirmar con fuerza:

```text
Todos los junios se comportan así.
```

Para eso harían falta más años.

---

# 11. Motor de tendencias inicial

El módulo deberá usar el histórico disponible desde septiembre 2025 como insumo para escenarios.

La tendencia no aprueba metas automáticamente.

La tendencia informa la propuesta.

## Tendencias iniciales recomendadas

```text
Promedio últimos 3 meses cerrados
Promedio últimos 6 meses cerrados
Variación mes contra mes
Cumplimiento contra meta
Crecimiento neto de usuarios
Tendencia de bajas
Tendencia de ARPU
Tendencia de venta nueva
```

## Clasificación simple

```text
POSITIVA
ESTABLE
NEGATIVA
VOLÁTIL
SIN_HISTÓRICO_SUFICIENTE
```

## Ejemplo de lectura

```text
Sucursal: Villa Verde

Ingreso real:
Promedio 3M: $812,000
Último mes cerrado: $830,000
Meta propuesta: $872,432
Diferencia vs promedio 3M: +7.4%

Usuarios:
Promedio cierre 3M: 1,420
Proyección propuesta: 1,505
Diferencia: +85 usuarios

Bajas:
Promedio 3M: 142
Meta bajas propuesta: 130
Riesgo: depende de mejorar retención

Clasificación:
Tendencia positiva
Riesgo medio
```

---

# 12. Parámetros configurables del modelo

Esta es una decisión cerrada.

Los parámetros que afectan la estructura de las proyecciones **no deben vivir quemados en código**.

Deben ser editables desde Suite, de forma sencilla, con permisos, versión, explicación e impacto.

Regla:

```text
Fácil de ajustar.
Difícil de romper.
```

## 12.1 Parámetros editables

Ejemplos:

```text
Ventana de tendencia:
- últimos 3 meses
- últimos 6 meses
- meses cerrados solamente

ARPU usado:
- último mes cerrado
- promedio 3M
- promedio 6M
- manual

Bajas esperadas:
- promedio histórico por sucursal
- promedio regional
- valor manual
- porcentaje fijo

Reactivaciones:
- histórico
- manual
- por campaña

Nuevos domiciliados:
- porcentaje de clientes nuevos
- valor manual
- regla por sucursal

Agregadoras:
- incluir ingreso agregadoras
- excluir agregadoras
- mostrar separadas
- incluir solo dinero
- no incluir usuarios hasta tener fuente confiable

Riesgo:
- meta > X% sobre promedio 3M
- cumplimiento histórico < X%
- bajas > X%
- crecimiento requerido > X usuarios

Sucursal nueva:
- promedio regional
- sucursal comparable
- meta manual
```

## 12.2 Parámetros operativos

Estos pueden ser fáciles de editar:

```text
ventana de tendencia
porcentaje esperado de bajas
porcentaje de domiciliados
escenario base
incluir/excluir agregadoras
driver de campaña
comentario contextual
```

## 12.3 Parámetros estructurales

Estos también deben ser editables, pero no como fórmulas libres.

Deben controlarse con opciones predefinidas y versionadas:

```text
fórmula principal de usuarios proyectados
fórmula de ingreso proyectado
regla de ocupación
regla de cumplimiento
regla de riesgo
qué campos alimentan Track
qué escenario puede convertirse en meta oficial
```

No se permitirá una caja libre tipo Excel para que cualquiera escriba fórmulas.

---

# 13. Versionado de parámetros

Cada cambio importante en configuración debe crear una nueva versión del modelo.

Ejemplo:

```text
Modelo comercial base v1.0
- tendencia 3M
- ARPU promedio 3M
- bajas promedio histórico
- domiciliados 75%

Modelo comercial base v1.1
- tendencia 6M
- ARPU último mes cerrado
- bajas promedio histórico
- domiciliados 80%
```

Cada propuesta debe guardar con qué versión fue calculada:

```text
Meta junio 2026 — Villa Verde
Modelo usado: Comercial base v1.1
Tendencia: 6M
ARPU: último mes cerrado
Bajas: promedio histórico
Domiciliados: 80%
```

Así, si después preguntan por qué cambió una meta, Suite puede explicar qué versión del modelo se usó.

---

# 14. Preview de impacto

Antes de guardar cambios en parámetros importantes, Suite debe mostrar impacto estimado.

Ejemplo:

```text
Este cambio afectaría:
- 26 sucursales
- meta total mensual: +$420,000
- clientes nuevos: +180
- bajas estimadas: -90

[Guardar como nueva versión] [Cancelar]
```

Esto evita cambios accidentales y ayuda a que Dirección confíe más.

---

# 15. Agregadoras

Las agregadoras no están consideradas actualmente dentro del Perico, pero sí deben considerarse en Suite.

Se manejarán por separado.

Motivo:

```text
TotalPass actualmente entrega dinero, pero todavía no usuarios.
```

Por lo tanto:

* ingreso agregadoras puede integrarse;
* usuarios agregadoras queda como frente posterior;
* Wellhub y TotalPass deben tratarse como fuentes separadas;
* Track debe seguir distinguiendo:

  * ingreso base;
  * ingreso agregadoras;
  * ingreso real total;
  * usuarios base;
  * usuarios agregadoras cuando exista fuente confiable.

No se debe contaminar la meta base con agregadoras incompletas.

---

# 16. Aprobación mensual global y cambios por sucursal

El flujo normal será aprobar un paquete mensual completo.

Ejemplo:

```text
Metas oficiales junio 2026 — versión 1 — todas las sucursales
```

Pero también debe soportar cambios puntuales por sucursal.

Ejemplo:

```text
Cambio puntual Villa Verde junio 2026 — versión 2 — reemplaza solo esa sucursal
```

Por eso el modelo debe tener dos niveles:

```text
TargetBatch mensual
  └── TargetBranch por sucursal
```

El batch representa el paquete global.

La fila por sucursal representa el detalle modificable/versionable.

---

# 17. Estados

## 17.1 Estados del paquete mensual

```text
BORRADOR
PROPUESTA
EN_REVISION
APROBADA
RECHAZADA
REEMPLAZADA
CANCELADA
PUBLICADA
```

## 17.2 Estados por sucursal

```text
SIN_CAMBIOS
PROPUESTA
APROBADA
RECHAZADA
OVERRIDE_PROPUESTO
OVERRIDE_APROBADO
OVERRIDE_RECHAZADO
REEMPLAZADA
PUBLICADA
```

## 17.3 Estados de escenario

```text
AGRESIVO
REALISTA
AJUSTADO
APROBADO
```

## 17.4 Estados de modelo/parámetros

```text
BORRADOR
ACTIVO
REEMPLAZADO
ARCHIVADO
```

---

# 18. Flujo funcional

## 18.1 Flujo mensual normal

```text
1. Usuario autorizado crea paquete mensual.
2. Sistema toma datos históricos y/o metas importadas actuales.
3. Sistema usa configuración activa del modelo.
4. Sistema muestra tendencias por sucursal.
5. Usuario revisa escenarios.
6. Usuario agrega ajustes manuales con motivo.
7. Usuario genera propuesta.
8. Usuario envía a revisión.
9. Aprobador revisa resumen.
10. Aprobador autoriza o rechaza.
11. Si autoriza:
    - paquete pasa a APROBADA;
    - se publica a TrackMonthlyTargetORM;
    - se marca como activo/canónico;
    - se registra auditoría.
12. Si rechaza:
    - paquete pasa a RECHAZADA;
    - comentario obligatorio;
    - no afecta Track.
```

## 18.2 Flujo de override por sucursal

```text
1. Ya existe paquete mensual aprobado/publicado.
2. Usuario propone cambio para una sucursal.
3. Captura motivo/contexto.
4. Sistema muestra diferencia vs valor aprobado anterior.
5. Aprobador autoriza o rechaza.
6. Si autoriza:
    - crea nueva versión para esa sucursal;
    - desactiva versión anterior;
    - publica nuevo valor activo a Track;
    - conserva historial.
7. Si rechaza:
    - no cambia Track;
    - queda auditoría del intento.
```

## 18.3 Flujo de cambio de parámetros

```text
1. Usuario autorizado entra a configuración.
2. Modifica parámetro de negocio.
3. Sistema muestra impacto estimado.
4. Usuario guarda como nueva versión.
5. Sistema registra auditoría.
6. Nuevas propuestas usan nueva versión.
7. Propuestas/metas anteriores conservan la versión usada originalmente.
```

---

# 19. Roles y permisos

## 19.1 Roles mínimos

```text
PLANNING_VIEWER
PLANNING_EDITOR
PLANNING_PROPOSER
PLANNING_APPROVER
PLANNING_ADMIN
MODEL_CONFIG_ADMIN
```

## PLANNING_VIEWER

Puede ver:

* paquetes aprobados;
* histórico;
* resumen;
* metas vigentes.

No puede editar ni aprobar.

## PLANNING_EDITOR

Puede:

* crear borradores;
* editar variables en borrador;
* agregar comentarios;
* preparar simulaciones.

No puede proponer oficialmente ni aprobar.

## PLANNING_PROPOSER

Puede:

* convertir borrador en propuesta;
* enviar a revisión;
* justificar ajustes;
* proponer cambios por sucursal.

No debe aprobar su propia propuesta si se aplica doble validación.

## PLANNING_APPROVER

Puede:

* aprobar paquete mensual;
* rechazar paquete mensual;
* aprobar override por sucursal;
* rechazar override por sucursal.

Debe capturar comentario obligatorio al rechazar.

## PLANNING_ADMIN

Puede:

* administrar flujo;
* cancelar paquetes;
* ver auditoría completa;
* corregir errores operativos con trazabilidad.

No debe borrar historial sensible.

## MODEL_CONFIG_ADMIN

Puede:

* editar parámetros del modelo;
* crear nuevas versiones de configuración;
* activar o archivar versiones;
* ver impacto estimado;
* revisar historial de cambios.

---

# 20. Reglas de negocio

## 20.1 Canonicalidad

Solo una meta puede estar activa/canónica por:

```text
target_month + sucursal_canon
```

## 20.2 No sobrescritura silenciosa

Toda modificación a una meta aprobada crea nueva versión.

## 20.3 Publicación controlada

Track no consume borradores, propuestas ni rechazados.

Solo consume aprobadas/publicadas.

## 20.4 Rechazo con comentario

Todo rechazo requiere comentario obligatorio.

## 20.5 Ajuste manual con motivo

Todo ajuste manual debe tener:

```text
variable afectada
valor
driver/contexto
justificación
usuario
fecha/hora
```

## 20.6 Aprobación mensual

El flujo normal aprueba el paquete mensual completo.

## 20.7 Override por sucursal

Un cambio después de aprobación debe versionar solo la sucursal afectada.

## 20.8 Agregadoras separadas

Ingreso agregadoras puede integrarse.

Usuarios agregadoras no deben forzarse hasta tener fuente confiable.

## 20.9 Tendencia como insumo

La tendencia no decide automáticamente.

Solo informa.

## 20.10 Parámetros versionados

Todo parámetro estructural debe estar versionado y auditable.

## 20.11 Backend como fuente de permisos

El frontend puede ocultar botones, pero el backend debe validar permisos reales.

---

# 21. Modelo conceptual de datos

Esto no es todavía migración final. Es contrato conceptual.

## 21.1 `planning_model_configs`

Configuración del modelo de proyección.

```text
id
name
version
status
description
trend_window_months
trend_closed_months_only
arpu_strategy
bajas_strategy
reactivaciones_strategy
domiciliados_strategy
aggregators_strategy
new_branch_strategy
risk_rules_json
parameters_json
created_by_user_id
created_at
activated_by_user_id
activated_at
replaced_by_config_id
notes
```

## 21.2 `planning_target_batches`

Paquete mensual.

```text
id
target_month
version
status
scope
source_type
source_upload_id
model_config_id
scenario_base
proposed_by_user_id
proposed_at
approved_by_user_id
approved_at
rejected_by_user_id
rejected_at
rejection_comment
published_at
is_canonical
notes
created_at
updated_at
```

`scope`:

```text
MONTHLY_BATCH
BRANCH_OVERRIDE
```

`source_type`:

```text
EXCEL_PERICO
MANUAL
SIMULATOR
MIXED
```

## 21.3 `planning_target_branch_rows`

Detalle por sucursal.

```text
id
batch_id
target_month
sucursal_canon
m2_sin_circulaciones
usuarios_inicio_mes
proyeccion_usuarios_cierre_mes
meta_faycgo_mes
meta_clientes_nuevos_mes
meta_reactivaciones_mes
meta_bajas_mes
meta_nuevos_domiciliados_mes
meta_arpu_mes
meta_venta_tienda_mes
ingreso_agregadoras_estimado
usuarios_agregadoras_estimado
scenario_used
trend_classification
risk_level
status
previous_branch_row_id
notes
created_at
updated_at
```

## 21.4 `planning_target_adjustments`

Ajustes manuales/contextuales.

```text
id
branch_row_id
variable_key
adjustment_value
adjustment_type
driver_type
justification
created_by_user_id
created_at
```

`driver_type`:

```text
VACACIONES
CAMPAÑA
ESCUELA_CERCANA
COMPETENCIA
CAMBIO_GERENTE
CAPACIDAD_COMERCIAL
CAPEX
CONDICION_LOCAL
EVENTO
RIESGO_OPERATIVO
OTRO
```

## 21.5 `planning_target_approval_events`

Auditoría de decisiones.

```text
id
batch_id
branch_row_id nullable
event_type
from_status
to_status
actor_user_id
comment
metadata_json
created_at
```

`event_type`:

```text
CREATED
UPDATED
SUBMITTED
APPROVED
REJECTED
OVERRIDE_CREATED
OVERRIDE_APPROVED
OVERRIDE_REJECTED
MODEL_CONFIG_CHANGED
PUBLISHED_TO_TRACK
CANCELLED
```

## 21.6 Relación con `TrackMonthlyTargetORM`

`TrackMonthlyTargetORM` sigue siendo la tabla operativa consumida por Track.

La nueva capa de planeación publica hacia esa tabla.

```text
planning_target_batches
planning_target_branch_rows
planning_target_adjustments
planning_target_approval_events
        ↓
publicación aprobada
        ↓
TrackMonthlyTargetORM
        ↓
Track daily mart
```

---

# 22. Pantallas necesarias

## 22.1 Escritorio — Home de Planeación

Debe mostrar:

* mes seleccionado;
* paquete vigente;
* estado;
* versión;
* última aprobación;
* número de sucursales;
* resumen total;
* acciones disponibles según permiso.

Acciones:

```text
Crear paquete
Ver paquete
Enviar a revisión
Aprobar
Rechazar
Ver histórico
Configurar modelo
```

## 22.2 Escritorio — Paquete mensual

Tabla por sucursal con:

* sucursal;
* usuarios inicio;
* usuarios cierre proyectados;
* meta FAYCGO;
* clientes nuevos;
* reactivaciones;
* bajas;
* nuevos domiciliados;
* ARPU;
* venta tienda;
* ingreso agregadoras estimado;
* escenario usado;
* tendencia;
* riesgo;
* ajustes;
* estado;
* diferencia vs mes anterior;
* diferencia vs meta anterior.

## 22.3 Escritorio — Detalle sucursal

Debe mostrar:

* histórico;
* tendencia;
* metas anteriores;
* cumplimiento;
* variables base;
* ajustes;
* comentarios;
* riesgos;
* cambios de versión.

## 22.4 Escritorio — Configuración del modelo

Debe mostrar parámetros editables en lenguaje de negocio.

Ejemplo:

```text
Modelo activo:
Comercial base v1.0

Tendencia:
[Últimos 3 meses cerrados]

ARPU:
[Promedio 3 meses]

Bajas:
[Promedio histórico por sucursal]

Domiciliados:
[75% de clientes nuevos]

Agregadoras:
[Mostrar separadas, no sumar usuarios]

Riesgo alto si:
[Meta > 15% sobre promedio 3M y cumplimiento < 90%]

[Guardar nueva versión]
```

## 22.5 Escritorio — Panel de ajustes

Debe permitir registrar:

* variable afectada;
* valor;
* driver;
* justificación;
* impacto estimado.

## 22.6 Móvil — Aprobación ejecutiva

Debe mostrar:

* paquete o sucursal;
* mes;
* meta propuesta;
* diferencia vs mes anterior;
* diferencia vs escenario;
* escenario usado;
* ajustes relevantes;
* riesgos;
* quién propone;
* botón autorizar;
* botón rechazar;
* comentario obligatorio si rechaza.

No debe permitir edición avanzada.

## 22.7 Auditoría

Debe mostrar:

* evento;
* usuario;
* fecha/hora;
* estado anterior;
* estado nuevo;
* comentario;
* valores afectados;
* versión del modelo usada.

---

# 23. Backend propuesto

## 23.1 Blueprint

```text
backend/app/routes/planning_targets_routes.py
```

## 23.2 Services

```text
backend/app/warehouse/services/planning_model_config_service.py
backend/app/warehouse/services/planning_targets_service.py
backend/app/warehouse/services/planning_targets_publish_service.py
backend/app/warehouse/services/planning_targets_adjustments_service.py
backend/app/warehouse/services/planning_targets_approval_service.py
backend/app/warehouse/services/planning_trends_service.py
```

## 23.3 Endpoints conceptuales

```text
GET    /api/planning/model-configs
POST   /api/planning/model-configs
GET    /api/planning/model-configs/:id
POST   /api/planning/model-configs/:id/activate
GET    /api/planning/model-configs/:id/impact-preview

GET    /api/planning/targets/batches
POST   /api/planning/targets/batches
GET    /api/planning/targets/batches/:id
POST   /api/planning/targets/batches/:id/submit
POST   /api/planning/targets/batches/:id/approve
POST   /api/planning/targets/batches/:id/reject
POST   /api/planning/targets/batches/:id/publish-to-track

POST   /api/planning/targets/batches/:id/branch-rows/:rowId/adjustments
POST   /api/planning/targets/batches/:id/branch-rows/:rowId/override
POST   /api/planning/targets/batches/:id/branch-rows/:rowId/approve-override
POST   /api/planning/targets/batches/:id/branch-rows/:rowId/reject-override

GET    /api/planning/trends
GET    /api/planning/trends/:sucursalCanon

GET    /api/planning/mobile/pending-approvals
GET    /api/planning/mobile/pending-approvals/:id
POST   /api/planning/mobile/pending-approvals/:id/approve
POST   /api/planning/mobile/pending-approvals/:id/reject
```

---

# 24. Frontend propuesto

Reglas de proyecto:

* componentes separados en `.ts`, `.html`, `.css`;
* lógica en `.ts`;
* HTML solo estructura visual, bindings simples y llamadas a métodos/propiedades;
* sin templates inline;
* sin estilos inline;
* servicios por dominio consumen endpoints REST.

## Rutas

```text
/#/planeacion/metas
/#/planeacion/metas/:batchId
/#/planeacion/metas/:batchId/sucursal/:sucursalCanon
/#/planeacion/modelo
/#/planeacion/aprobaciones
/#/m/aprobaciones/metas/:approvalId
```

## Componentes

```text
frontend/src/app/planning/targets/planning-targets-home/
frontend/src/app/planning/targets/planning-target-batch-detail/
frontend/src/app/planning/targets/planning-target-branch-detail/
frontend/src/app/planning/targets/planning-target-adjustment-dialog/
frontend/src/app/planning/targets/planning-model-config/
frontend/src/app/planning/targets/planning-target-approval-mobile/
frontend/src/app/planning/services/planning-targets.service.ts
frontend/src/app/planning/services/planning-model-config.service.ts
frontend/src/app/planning/services/planning-trends.service.ts
```

---

# 25. Criterios de aceptación

## CA1 — Crear paquete mensual

Dado un usuario con permiso, cuando crea un paquete mensual, entonces el sistema genera un batch en estado `BORRADOR`.

## CA2 — Importar metas existentes

El sistema puede tomar metas existentes/importadas como base de propuesta.

## CA3 — Validar sucursales

Si una sucursal no existe en catálogo Track, el sistema bloquea publicación.

## CA4 — Enviar a revisión

Solo usuarios con permiso pueden cambiar de `BORRADOR` a `EN_REVISION`.

## CA5 — Aprobar paquete

Un aprobador autorizado puede aprobar un paquete mensual completo.

## CA6 — Rechazar paquete

Un aprobador autorizado puede rechazar, pero con comentario obligatorio.

## CA7 — Publicar a Track

Solo paquetes aprobados pueden publicar a `TrackMonthlyTargetORM`.

## CA8 — No publicar borradores

Borradores, propuestas o rechazados no afectan Track.

## CA9 — Override por sucursal

Si cambia una sucursal después de aprobar el mes, se crea nueva versión solo para esa sucursal.

## CA10 — Historial

El sistema conserva valores anteriores.

## CA11 — Auditoría

Toda acción relevante genera evento de auditoría.

## CA12 — Vista móvil

La vista móvil permite aprobar/rechazar con contexto mínimo suficiente.

## CA13 — Parámetros configurables

Los parámetros del modelo pueden editarse desde Suite con permisos y versionado.

## CA14 — Preview de impacto

Cambios estructurales de configuración muestran impacto estimado antes de guardarse.

## CA15 — Tendencias

El sistema calcula tendencias por sucursal usando histórico disponible.

## CA16 — Permisos backend

El backend valida permisos aunque el frontend oculte acciones.

---

# 26. Riesgos y mitigaciones

## Riesgo 1 — Copiar el caos del Excel

Mitigación:

```text
No replicar hojas.
Separar inputs, escenarios, ajustes, aprobación y publicación.
```

## Riesgo 2 — Falsa precisión

Mitigación:

```text
Escenarios = estimaciones.
Meta aprobada = valor exacto oficial.
```

## Riesgo 3 — Ajustes sin explicación

Mitigación:

```text
Todo ajuste requiere driver y justificación.
```

## Riesgo 4 — Aprobar metas incorrectas

Mitigación:

```text
Resumen ejecutivo, comparación histórica, riesgos y confirmación explícita.
```

## Riesgo 5 — Modificación silenciosa

Mitigación:

```text
Versionado, auditoría y no sobrescritura directa.
```

## Riesgo 6 — Dirección no confía

Mitigación:

```text
Mostrar de dónde sale cada número y qué parámetro/modelo lo generó.
```

## Riesgo 7 — UX compleja

Mitigación:

```text
Escritorio para análisis.
Móvil para decisión.
```

## Riesgo 8 — Permisos débiles

Mitigación:

```text
Validación backend obligatoria.
```

## Riesgo 9 — Mezclar simulación con meta canónica

Mitigación:

```text
Estados separados.
Track solo consume aprobadas.
```

## Riesgo 10 — Agregadoras incompletas

Mitigación:

```text
Modelarlas separadas.
Integrar ingreso primero.
Usuarios después.
```

## Riesgo 11 — Parámetros opacos

Mitigación:

```text
Configuración editable, versionada, auditable y con preview de impacto.
```

## Riesgo 12 — Cambios de modelo rompen confianza

Mitigación:

```text
Toda propuesta guarda la versión del modelo usada.
```

## Riesgo 13 — Ingesta actual destructiva

La ingesta actual tiene un flujo que reemplaza filas del mes eliminando registros previos en `_replace_target_month_rows`; eso puede servir para ingesta operativa, pero no debe ser el flujo oficial de metas sensibles si queremos historial completo. 

Mitigación:

```text
Para el flujo oficial usar publicación versionada.
No borrar historial de planeación.
```

---

# 27. Orden de implementación

## F1.1 — Auditoría técnica de base actual

Objetivo:

* revisar `TrackMonthlyTargetORM`;
* revisar migraciones existentes;
* confirmar campos actuales;
* revisar ingesta actual;
* revisar upsert actual;
* decidir cómo publicar sin pérdida de historial;
* definir migración exacta de governance.

No tocar frontend todavía.

## F1.2 — Modelo DB de governance

Crear migración Alembic para:

```text
planning_model_configs
planning_target_batches
planning_target_branch_rows
planning_target_adjustments
planning_target_approval_events
```

## F1.3 — Backend de batch mensual

Crear endpoints para:

* crear batch;
* listar;
* detalle;
* enviar a revisión;
* aprobar;
* rechazar.

## F1.4 — Publicación hacia Track

Crear servicio único:

```text
publish_approved_batch_to_track()
```

Debe:

* validar estado aprobado;
* publicar a `TrackMonthlyTargetORM`;
* desactivar anteriores si aplica;
* registrar auditoría;
* no borrar historial de planeación.

## F1.5 — Configuración del modelo

Crear:

* modelo de parámetros;
* CRUD controlado;
* activar versión;
* preview de impacto;
* auditoría.

## F1.6 — Frontend escritorio mínimo

Crear:

* home;
* detalle paquete;
* tabla por sucursal;
* acciones básicas;
* estados visibles.

## F1.7 — Ajustes manuales

Agregar:

* modal;
* driver;
* justificación;
* impacto;
* auditoría.

## F1.8 — Vista móvil ejecutiva

Crear:

* resumen compacto;
* aprobar;
* rechazar;
* comentario obligatorio.

## F1.9 — Override por sucursal

Agregar:

* propuesta puntual;
* comparación contra valor anterior;
* aprobación;
* publicación.

## F2 — Tendencias y simulador inicial

Agregar:

* tendencia 3M/6M;
* clasificación por sucursal;
* riesgo;
* comparativos;
* escenarios simples.

## F3 — Simulador avanzado

Agregar:

* sensibilidad;
* gráficos;
* inputs más visuales;
* escenarios más finos;
* análisis por región/sucursal.

---

# 28. Decisiones cerradas

Quedan cerradas estas decisiones:

```text
1. El módulo no se llamará Perico formalmente.
2. El Excel actual es referencia, no especificación final.
3. La junta sigue siendo parte del proceso.
4. Suite gobierna, explica y audita.
5. Track solo consume metas aprobadas/canónicas.
6. Móvil es aprobación, no simulador.
7. Escritorio es análisis/simulación.
8. Agregadoras se manejan separadas.
9. TotalPass usuarios queda pendiente hasta tener fuente confiable.
10. Se soporta aprobación mensual global.
11. Se soporta override por sucursal.
12. Los parámetros del modelo son editables, versionados y auditados.
13. Tendencias desde septiembre 2025 sirven como insumo.
14. No habrá fórmulas libres tipo Excel en MVP.
15. No se debe borrar historial oficial.
```

---

# 29. Pendientes no bloqueantes

Estos puntos no bloquean el contrato. Se pueden resolver durante implementación:

```text
1. Confirmar campos exactos actuales de TrackMonthlyTargetORM.
2. Confirmar si meta_faycgo_mes incluye o no venta tienda.
3. Confirmar tratamiento exacto de meta_venta_tienda_mes.
4. Confirmar por qué algunas sucursales pueden venir en cero.
5. Confirmar si el archivo siempre vendrá con sucursal_canon.
6. Definir nombre final del módulo en menú.
7. Definir qué usuarios tendrán PLANNING_APPROVER.
8. Definir si Edmundo/Julián/Fabián aprueban dentro de Suite o solo se documenta la junta.
9. Definir si la primera versión móvil entra en F1.8 o después.
```

---

# 30. Prompt para la siguiente conversación

Este es el prompt que yo usaría para abrir la conversación de implementación:

```text
Vamos a implementar F1.1 del módulo Planeación Comercial / Proyecciones / Tendencias / Metas Futuras de Suite Ultra.

Ya cerramos contrato funcional v1.0.

No vamos a tocar frontend todavía.
No vamos a tocar simulador todavía.
No vamos a tocar vista móvil todavía.
Primero vamos a auditar y preparar la base técnica.

Objetivo F1.1:
- revisar TrackMonthlyTargetORM;
- revisar migraciones existentes;
- revisar track_monthly_targets_ingestion_service.py;
- revisar track_monthly_targets_service.py;
- confirmar campos actuales de auditoría/versionado;
- identificar riesgo del flujo _replace_target_month_rows;
- definir cómo publicar metas aprobadas hacia TrackMonthlyTargetORM sin perder historial;
- preparar contrato técnico exacto para migración Alembic de:
  - planning_model_configs;
  - planning_target_batches;
  - planning_target_branch_rows;
  - planning_target_adjustments;
  - planning_target_approval_events.

Reglas de trabajo:
- un cambio a la vez;
- primero explicar archivo, función, objetivo y motivo;
- no hacks;
- cambios DB siempre con Alembic;
- backend valida permisos;
- frontend no se toca todavía;
- no editar código en servidor;
- no romper Track actual;
- Track debe seguir consumiendo metas activas/canónicas.

Contexto clave:
Ya existe infraestructura para metas mensuales Track:
- parser Excel;
- validación de columnas;
- validación sucursal_canon;
- ingesta desde Warehouse upload;
- TrackMonthlyTargetORM;
- upsert individual/bulk;
- is_active.

El nuevo módulo no empieza como otro Excel.
Empieza como capa de governance:
configuración del modelo → tendencias/escenarios → ajustes justificados → propuesta → aprobación → meta canónica → publicación a Track.
```

---

# 31. Cierre ejecutivo

El contrato queda cerrado así:

```text
Suite Ultra no va a copiar el Perico.
Suite Ultra va a gobernar el proceso de metas.
```

La primera victoria del módulo no es predecir perfecto.

La primera victoria es poder decir:

```text
Esta meta es oficial.
Sabemos quién la propuso.
Sabemos quién la aprobó.
Sabemos qué versión del modelo usó.
Sabemos qué ajustes tuvo.
Sabemos por qué cambió.
Sabemos qué versión reemplazó.
Y sabemos por qué Track está usando ese número.
```

Eso ya es un salto enorme de Excel operativo a inteligencia comercial gobernada.
