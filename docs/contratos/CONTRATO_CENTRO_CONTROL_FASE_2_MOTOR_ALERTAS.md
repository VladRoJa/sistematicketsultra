# CONTRATO — CENTRO DE CONTROL SUITE ULTRA — FASE 2

## Motor de Alertas Operativas y de Negocio

**Estado:** Aprobado como contrato funcional para implementación  
**Versión:** 2.0  
**Fecha:** 2026-09-18  
**Producto:** Suite Ultra — Centro de Control  
**Alcance:** motor de alertas, expected pace, configuración/calibración, persistencia, trazabilidad, permisos e integración con Control V1  
**Predecesor:** docs/contratos/CONTRATO_CENTRO_CONTROL_V1.md  
**Contratos relacionados:** docs/track/operational-forecast-contract.md y docs/contratos/Contrato alertas track.md

---

# 0. REGLAS DE NEGOCIO MAESTRAS

> Esta sección debe permanecer al inicio del documento.  
> Cualquier revisión futura de Fase 2 debe respetar estas reglas o documentar explícitamente el cambio de contrato.

## 0.1 Una sola realidad

Centro de Control no crea una segunda versión de Track, Funnel, Retención, Tickets, Mantenimiento, Warehouse ni otros dominios.

El módulo propietario calcula el indicador. Control interpreta su resultado dentro de un contexto ejecutivo.

Ejemplos:

- Track / Forecast es propietario del forecast.
- KPI / Retención es propietario de reactivaciones y bajas cuando corresponda.
- Funnel es propietario de lead -> venta.
- Tickets / Maintenance Planner es propietario de compromisos y vencimientos.
- Warehouse conserva canonicalidad, versiones y snapshots fuente.

Control no debe duplicar fórmulas de esos módulos.

## 0.2 El backend decide si existe una alerta

Angular no determina:

- si una situación es favorable o desfavorable;
- si una desviación merece alerta;
- la severidad;
- la persistencia;
- el expected pace;
- el umbral;
- la deduplicación;
- la resolución;
- la prioridad.

Angular presenta el contrato ya evaluado por backend.

## 0.3 Toda alerta debe ser explicable

No se permite una alerta que únicamente diga:

> Riesgo elevado.

Toda alerta deberá poder reconstruirse con:

- valor real;
- referencia;
- tipo de referencia;
- desviación absoluta;
- desviación porcentual cuando aplique;
- regla usada;
- versión de regla;
- fecha de corte;
- alcance;
- fuente;
- evidencia.

Regla conceptual:

~~~text
Señal -> Por qué -> Dónde -> Fuente -> Evidencia
~~~

## 0.4 Una alerta representa una situación, no una corrida

Si una misma condición continúa en evaluaciones sucesivas no se crearán alertas duplicadas.

Ejemplo:

~~~text
18 sep 06:00  Reactivaciones Región X  -11%
18 sep 12:00  Reactivaciones Región X  -13%
19 sep 06:00  Reactivaciones Región X  -15%
~~~

Debe existir una sola alerta activa cuya evidencia evoluciona.

## 0.5 Los parámetros de negocio no se hardcodean

Todo parámetro razonablemente susceptible de cambiar por decisión de negocio debe poder administrarse desde Suite sin modificar código ni desplegar.

Ejemplos:

- umbrales de severidad;
- tolerancias;
- persistencia mínima;
- ventana de tendencia;
- historia mínima;
- activación/desactivación de reglas;
- cantidad máxima de focos;
- prioridad/peso ejecutivo.

## 0.6 Toda configuración activa es versionada

Editar una regla no modifica retroactivamente las alertas históricas.

Cada alerta debe recordar con qué versión de configuración fue evaluada.

## 0.7 No se inventa evidencia

Si no existe historia suficiente, referencia válida, cobertura suficiente o fuente canónica, el motor no fabricará una comparación.

Debe poder producir estados explícitos como:

~~~text
INSUFFICIENT_HISTORY
INSUFFICIENT_COVERAGE
SOURCE_UNAVAILABLE
NOT_APPLICABLE
~~~

## 0.8 El motor es determinístico

Fase 2 no depende de IA generativa ni de un modelo opaco para decidir que una alerta existe.

Mismos datos + misma regla + misma versión + mismo contexto = mismo resultado.

La IA podrá utilizarse posteriormente para redactar narrativa, nunca como única fuente de decisión.

## 0.9 El backend define seguridad

Los filtros de la UI no constituyen autorización.

Todo endpoint deberá intersectar el alcance solicitado con el alcance autorizado por backend.

Un usuario regional nunca puede ampliar su universo manipulando parámetros del navegador.

## 0.10 El contexto temporal es parte del dato

Toda evaluación debe declarar:

- fecha de corte;
- periodo evaluado;
- zona horaria de negocio;
- versión/snapshot cuando aplique;
- modo de generación.

Para Suite Ultra la zona horaria operativa permanece America/Tijuana salvo contrato explícito distinto.

## 0.11 Preview y evaluación oficial no son equivalentes

Una evaluación manual o de preview puede simular el motor, pero no debe abrir, cerrar ni modificar alertas oficiales persistidas.

Solo una evaluación oficial autorizada puede modificar lifecycle productivo.

## 0.12 La configuración debe ser segura de editar

No se permitirán fórmulas Python, SQL, JavaScript ni expresiones arbitrarias introducidas desde Angular.

La UI editará parámetros tipados y validados contra una definición conocida de regla.

## 0.13 La complejidad crece hacia abajo

La portada de Control sigue siendo ejecutiva.

Fase 2 no convierte la primera pantalla en una matriz de semáforos ni en una tabla extensa.

El motor puede conocer muchas alertas; Atención hoy presenta solamente las de mayor prioridad.

---

# 1. PROPÓSITO

Fase 2 transforma Centro de Control de una superficie que muestra indicadores y focos calculados localmente a un sistema capaz de detectar automáticamente situaciones que requieren atención.

Control debe responder:

1. ¿Qué está pasando?
2. ¿Por qué requiere atención?
3. ¿Dónde ocurre?
4. ¿Desde cuándo ocurre?
5. ¿Está mejorando o empeorando?
6. ¿Qué evidencia sostiene la alerta?
7. ¿De qué módulo y corte proviene?
8. ¿Dónde puedo profundizar?

Frase de producto:

> Control V2 convierte métricas confiables en situaciones explicables que requieren atención.

---

# 2. RELACIÓN CON CONTROL V1

Fase 2 extiende, no reemplaza, el contrato de Centro de Control V1.

Se preservan:

- contexto efectivo;
- scopes GLOBAL / REGION / BRANCH_POOL / BRANCH;
- permisos backend;
- lectura ejecutiva;
- Resumen / Por qué / Dónde / Fuente;
- drill-down;
- módulo propietario como fuente;
- consistencia vertical;
- preservación de contexto;
- claridad de Nivel 0.

Fase 2 agrega:

- motor centralizado de alertas;
- expected pace como referencia formal;
- reglas configurables;
- severidad;
- deduplicación;
- lifecycle;
- persistencia;
- trazabilidad;
- auditoría;
- simulación de calibración;
- selección priorizada de Atención hoy.

---

# 3. ESTADO ACTUAL Y DEUDA QUE FASE 2 DEBE ABSORBER

Al momento de aprobar este contrato, Centro de Control ya dispone de backend propio bajo:

~~~text
/api/control/context
/api/control/retention
/api/control/operational-forecast
~~~

También existe contrato oficial de Forecast Operativo para:

- ingreso;
- venta nueva;
- reactivaciones;
- bajas;
- tienda.

Sin embargo, la selección de Atención hoy todavía se calcula en frontend dentro de:

~~~text
frontend/src/app/control-center/control-center.component.ts
~~~

El getter attentionItems:

- decide si la brecha es adversa;
- contiene conocimiento de que Bajas tiene dirección inversa;
- ordena por severidad relativa;
- limita los focos;
- genera textos de alerta;
- agrega reglas particulares de Retención, Mantenimiento y Conversión.

Esto se considera deuda explícita de Fase 2.

Objetivo de migración:

~~~text
ANTES
Angular obtiene métricas -> Angular decide focos

DESPUÉS
Backend evalúa reglas -> Alert Engine produce alertas -> Angular presenta
~~~

Angular podrá conservar funciones puramente visuales o de formato, pero no reglas críticas de negocio.

---

# 4. ALCANCE FUNCIONAL DE FASE 2

Fase 2 incluye cuatro familias iniciales de detección.

## 4.1 TARGET_GAP

Compara el resultado contra una meta, límite o benchmark explícito.

Ejemplos:

- Venta nueva proyectada debajo de meta.
- Reactivaciones proyectadas debajo de meta.
- Bajas proyectadas sobre límite.
- Tienda proyectada debajo de meta.
- Ingresos proyectados debajo de meta.

## 4.2 EXPECTED_PACE

Compara el valor observado contra el comportamiento esperado para ese punto del periodo.

Ejemplo:

~~~text
Reactivaciones reales al día 18: 412
Esperado comparable al día 18: 475
Desviación: -63
Desviación: -13.3%
~~~

No se permite utilizar por defecto:

~~~text
día_del_mes / días_del_mes
~~~

como expected pace si existe un comportamiento histórico más representativo.

## 4.3 TREND_DETERIORATION

Detecta deterioro sostenido incluso antes de cruzar una meta absoluta.

Ejemplo:

~~~text
día 14  -2%
día 15  -4%
día 16  -7%
día 17  -9%
día 18  -12%
~~~

El objetivo es encontrar señales tempranas.

## 4.4 OPERATIONAL_BREACH

Representa incumplimientos operativos que no requieren necesariamente una curva histórica.

Ejemplos:

- compromisos de mantenimiento vencidos;
- tickets sin fecha;
- PM fuera de tiempo;
- tareas con SLA incumplido;
- entidades operativas pendientes más allá del límite permitido.

---

# 5. FUERA DE ALCANCE DE FASE 2

No forman parte del objetivo de esta fase:

- WhatsApp automático;
- SMS automático;
- correo automático;
- asignación de responsables como workflow completo;
- comentarios colaborativos avanzados;
- chat sobre alertas;
- IA decidiendo si una alerta existe;
- machine learning opaco;
- recomendaciones automáticas no explicables;
- penalizaciones;
- acciones destructivas desde Control;
- reemplazar los módulos propietarios;
- convertir Control en herramienta genérica de BI externo.

La arquitectura no debe impedir estas evoluciones, pero no condicionan la aceptación de Fase 2.

---

# 6. FLUJO LÓGICO

~~~text
FUENTES CANÓNICAS / MÓDULOS PROPIETARIOS
                |
                v
        INDICADORES NORMALIZADOS
                |
                v
      REFERENCIA / EXPECTED PACE
                |
                v
          REGLA + CONFIG
                |
                v
           ALERT ENGINE
                |
      +---------+----------+
      |                    |
      v                    v
 PERSISTENCIA        RESULTADO PREVIEW
      |
      v
  CONTROL API
      |
      v
ATENCIÓN HOY / DETALLE
      |
      v
Resumen -> Por qué -> Dónde -> Fuente
~~~

---

# 7. REGISTRO DE INDICADORES

Cada indicador alertable debe registrarse explícitamente.

Contrato conceptual:

~~~text
indicator_key
domain
title
unit
direction
supported_rule_types
source_contract
source_module
supports_scope
supports_expected_pace
supports_trend
~~~

## 7.1 Dirección

Valores permitidos:

~~~text
HIGHER_IS_BETTER
LOWER_IS_BETTER
NEUTRAL_TARGET
BREACH_BOOLEAN
~~~

Ejemplos:

~~~text
INGRESO                 HIGHER_IS_BETTER
VENTA_NUEVA             HIGHER_IS_BETTER
REACTIVACIONES          HIGHER_IS_BETTER
CONVERSION              HIGHER_IS_BETTER
BAJAS                   LOWER_IS_BETTER
MANTENIMIENTO_VENCIDO   LOWER_IS_BETTER
~~~

La dirección debe vivir en backend/configuración del indicador, nunca dispersa en condiciones de Angular.

---

# 8. CONTRATO DE REGLA

Una regla define cómo evaluar un indicador, no cómo calcular el indicador.

Contrato conceptual:

~~~text
rule_key
indicator_key
rule_type
enabled
direction
reference_kind
scope_level
priority_weight
active_version_id
~~~

Ejemplos:

~~~text
reactivaciones.expected_pace
bajas.monthly_limit
venta_nueva.target_gap
maintenance.overdue_commitments
reactivaciones.trend_deterioration
~~~

Una regla puede tener múltiples versiones de configuración a lo largo del tiempo.

---

# 9. CONFIGURACIÓN Y CALIBRACIÓN EDITABLE

## 9.1 Requisito obligatorio

Fase 2 debe incluir una superficie administrativa dentro de Suite:

~~~text
Control
  -> Configuración
      -> Alertas
~~~

Modificar parámetros de calibración no debe requerir:

- cambiar Python;
- cambiar TypeScript;
- editar HTML;
- hacer commit;
- reconstruir contenedores;
- desplegar.

## 9.2 Parámetros configurables mínimos

Según el tipo de regla, la UI debe poder administrar:

- regla activa/inactiva;
- umbral INFO;
- umbral WARNING;
- umbral HIGH;
- umbral CRITICAL;
- tolerancia;
- cantidad mínima de días o corridas antes de abrir;
- cantidad mínima de corridas normales antes de resolver;
- ventana de tendencia;
- historia mínima requerida;
- periodos comparables mínimos;
- cobertura mínima;
- peso/prioridad ejecutiva;
- cantidad máxima de focos globales de Atención hoy;
- observación/motivo del cambio.

No todos los parámetros aplican a todas las reglas.

## 9.3 Parámetros tipados

Tipos permitidos conceptualmente:

~~~text
PERCENT
NUMBER
COUNT
DAYS
RUNS
RATIO
BOOLEAN
ENUM
~~~

No se permiten scripts ni fórmulas arbitrarias.

## 9.4 Ejemplo: Reactivaciones

~~~text
Indicador: REACTIVACIONES
Regla: EXPECTED_PACE
Dirección: HIGHER_IS_BETTER
Activo: Sí

WARNING: -5%
HIGH: -10%
CRITICAL: -20%

Persistencia para abrir: 2 corridas oficiales
Corridas normales para resolver: 2
Ventana tendencia: 5 días
Historia mínima: 6 periodos comparables
Cobertura mínima: 80%
Prioridad: 80
~~~

## 9.5 Ejemplo: Bajas

~~~text
Indicador: BAJAS
Regla: TARGET_GAP
Dirección: LOWER_IS_BETTER
Activo: Sí

WARNING: +5%
HIGH: +10%
CRITICAL: +20%
~~~

La UI puede mostrar valores positivos de exceso aunque internamente el motor normalice la adversidad.

## 9.6 Alcance de configuración

Configuración GLOBAL es obligatoria en la primera entrega.

El modelo debe quedar preparado para:

~~~text
GLOBAL
REGION
BRANCH
~~~

con precedencia:

~~~text
BRANCH override
  -> REGION override
      -> GLOBAL
~~~

Los overrides regionales o de sucursal podrán habilitarse posteriormente sin rediseñar persistencia.

## 9.7 Validaciones

El backend deberá rechazar configuraciones inválidas.

Ejemplos:

- thresholds fuera de rango;
- historia mínima negativa;
- ventana cero;
- cobertura > 100%;
- prioridades fuera del rango permitido;
- secuencias de severidad incoherentes;
- parámetros incompatibles con el tipo de regla;
- indicador que no soporta expected pace configurado como expected pace.

La UI puede prevenir errores, pero la validación definitiva vive en backend.

---

# 10. VERSIONADO DE CONFIGURACIÓN

## 10.1 Inmutabilidad histórica

Una versión activa no se modifica en sitio.

Editar produce una nueva versión.

Ejemplo:

~~~text
reactivaciones.expected_pace
v7  HIGH = -10%
v8  HIGH = -15%
~~~

Las alertas creadas con v7 conservan v7 como referencia histórica.

## 10.2 Estados de versión

Conceptualmente:

~~~text
DRAFT
ACTIVE
RETIRED
~~~

Solo una versión ACTIVE por regla y alcance efectivo para una fecha dada.

## 10.3 Activación

Activar una nueva versión debe ser una operación explícita y auditada.

No debe existir un estado intermedio donde media aplicación use una versión y media aplicación otra.

## 10.4 Vigencia

Cada versión debe registrar al menos:

~~~text
version_id
rule_key
scope_type
scope_id
effective_from
effective_to
created_at
created_by
activated_at
activated_by
change_reason
parameters_json
~~~

---

# 11. PREVIEW DE CALIBRACIÓN

Antes de activar una nueva versión, Suite debe permitir simular su efecto sin mutar alertas oficiales.

Ejemplo de UX:

~~~text
Configuración actual
11 alertas HIGH
3 alertas CRITICAL

Nueva configuración
6 alertas HIGH
2 alertas CRITICAL

Cambios:
5 dejarían de ser HIGH
1 cambiaría de HIGH a WARNING
~~~

El preview puede ejecutarse contra:

- corte actual;
- uno o más cortes históricos;
- scope permitido.

Requisito crítico:

> Preview nunca abre, resuelve, escala ni modifica una alerta oficial.

---

# 12. AUDITORÍA DE CONFIGURACIÓN

Todo cambio debe registrar:

- regla;
- versión anterior;
- versión nueva;
- usuario;
- fecha/hora;
- motivo;
- parámetros anteriores;
- parámetros nuevos;
- alcance;
- activación/desactivación.

Debe existir historial consultable desde la superficie administrativa.

---

# 13. CONTRATO DE ALERTA

Entidad conceptual mínima:

~~~text
alert_id
identity_key
as_of_date
period_key

indicator_key
rule_key
rule_version_id
alert_type

scope_type
scope_id
scope_name

severity
status

actual_value
reference_value
reference_kind

deviation_value
deviation_pct

headline
explanation

started_at
last_seen_at
resolved_at

source_module
source_contract
source_reference

evidence
created_at
updated_at
~~~

Campos pueden ser nulos cuando el tipo de regla no los requiera.

---

# 14. IDENTIDAD Y DEDUPLICACIÓN

Una identidad lógica debe ser estable mientras la situación sea la misma.

Base conceptual:

~~~text
rule_key
+ indicator_key
+ scope_type
+ scope_id
+ period_key
~~~

Podrá agregarse una dimensión adicional únicamente cuando sea necesaria para distinguir situaciones de negocio reales.

No debe incluir timestamp de corrida.

---

# 15. LIFECYCLE

Estados mínimos obligatorios:

~~~text
OPEN
RESOLVED
~~~

La arquitectura debe permitir posteriormente:

~~~text
ACKNOWLEDGED
DISMISSED
~~~

sin rediseño mayor.

## 15.1 Apertura

Una regla puede exigir persistencia antes de abrir.

Ejemplo:

~~~text
open_after_runs = 2
~~~

Una única lectura adversa no necesariamente abre alerta.

## 15.2 Actualización

Mientras la condición continúe:

- se conserva alert_id;
- se actualiza last_seen_at;
- se actualizan valores actuales;
- se conserva historial mediante eventos/run/evidencia;
- puede cambiar severidad.

## 15.3 Escalamiento

Si la situación empeora:

~~~text
WARNING -> HIGH -> CRITICAL
~~~

se actualiza la alerta existente y se registra evento.

## 15.4 Mejora

Si la situación mejora sin resolverse:

~~~text
CRITICAL -> HIGH
~~~

se conserva la misma alerta y se registra la mejora.

## 15.5 Resolución

Cuando la condición deja de cumplirse y satisface la regla de estabilidad para resolver:

~~~text
status = RESOLVED
resolved_at = timestamp
~~~

La alerta no se elimina.

---

# 16. ANTI-FLAPPING

Para evitar abrir/cerrar una alerta alrededor del umbral, las reglas deberán poder definir:

- persistencia mínima para abrir;
- persistencia mínima para resolver;
- tolerancia/histeresis;
- ventana de evaluación.

Ejemplo:

~~~text
abrir HIGH debajo de -10%
resolver solo cuando permanezca arriba de -7% por 2 corridas
~~~

La implementación exacta se definirá en contrato técnico, pero el modelo funcional debe soportarlo.

---

# 17. SEVERIDAD

Niveles mínimos:

~~~text
INFO
WARNING
HIGH
CRITICAL
~~~

La severidad la produce backend.

No depende únicamente de color.

Puede considerar:

~~~text
magnitud de desviación
+ persistencia
+ tendencia
+ impacto
+ alcance
~~~

La fórmula exacta debe permanecer determinística y auditable.

---

# 18. PRIORIDAD DE ATENCIÓN

Severidad y prioridad no son exactamente lo mismo.

Una alerta HIGH de alto impacto puede aparecer antes que otra HIGH de menor impacto.

Orden conceptual reproducible:

~~~text
severity
+ priority_weight
+ magnitude
+ persistence
+ scope_impact
~~~

No se utilizará un ranking opaco.

El response deberá poder incluir priority_score y/o razones de prioridad suficientemente auditables.

---

# 19. EXPECTED PACE

## 19.1 Rol

Expected Pace es una referencia consumida por el Motor de Alertas.

No sustituye al forecast de cierre.

No debe construirse dentro de Angular.

## 19.2 Contrato mínimo

~~~text
indicator_key
scope_type
scope_id
as_of_date
period_key

actual_value
expected_value

sample_periods
comparable_entities
coverage_ratio
confidence
method
source_version
status
~~~

## 19.3 Métodos

Puede utilizar:

- curva histórica propia;
- curva regional;
- curva nacional;
- benchmark contractual existente;
- otro método documentado por dominio.

La selección debe ser explícita en method.

## 19.4 Historia insuficiente

Si no existe muestra suficiente:

~~~text
status = INSUFFICIENT_HISTORY
~~~

El motor no genera una alerta EXPECTED_PACE basada en un dato inventado.

Podrá evaluar otro tipo de regla válida para ese indicador.

## 19.5 Sucursales nuevas

Una sucursal nueva no debe ser juzgada con una curva histórica inexistente.

El contrato técnico deberá definir fallback permitido por indicador y debe quedar visible en evidence.

---

# 20. COHORTES COMPARABLES

Cuando la comparación histórica requiera entidades comparables, se utilizará cohorte común.

Ejemplo:

~~~text
sep 2026 = 26 sucursales operativas
sep 2025 = 22 sucursales comparables
~~~

La comparación debe declarar:

- universo actual;
- universo histórico;
- cohorte común;
- exclusiones;
- cobertura.

No se penaliza ni mejora artificialmente una métrica por aperturas/cierres de sucursales sin explicarlo.

---

# 21. FUENTES Y CANONICALIDAD

Para Track/Warehouse se prioriza:

- versión efectiva;
- snapshot canónico;
- business_date / track_date;
- report_type_key;
- is_canonical;
- generation_mode.

Para fuentes OLTP se prioriza:

- ID estable;
- estado actual;
- timestamps de negocio;
- historial cuando exista.

Control no debe ocultar una inconsistencia de fuente mediante un cálculo alternativo silencioso.

---

# 22. GENERATION MODE Y PERSISTENCIA OFICIAL

El backend actual distingue:

~~~text
manual_preview
official_closed_day
~~~

Fase 2 conserva esa semántica.

## 22.1 manual_preview

Puede:

- evaluar reglas;
- mostrar alertas simuladas;
- probar calibración;
- comparar escenarios.

No puede:

- abrir alertas oficiales;
- cerrar alertas oficiales;
- alterar started_at;
- alterar resolved_at;
- modificar lifecycle productivo.

## 22.2 official_closed_day

Puede:

- crear;
- actualizar;
- escalar;
- mejorar;
- resolver;
- persistir evidencia;
- registrar run.

Esta regla evita que una consulta manual cambie el historial del negocio.

---

# 23. EVIDENCIA

evidence debe ser estructurada.

Ejemplo:

~~~json
{
  "actual": 412,
  "expected": 475,
  "deviation": -63,
  "deviation_pct": -0.1326,
  "period_start": "2026-09-01",
  "period_end": "2026-09-18",
  "sample_periods": 8,
  "comparable_branches": 24,
  "coverage_ratio": 0.923,
  "method": "historical_expected_pace"
}
~~~

La evidencia debe ser suficiente para reconstruir Por qué sin recalcular la regla en frontend.

---

# 24. DÓNDE — CONTRIBUCIÓN

Cuando sea técnicamente posible, una alerta agregada debe poder identificar qué entidades explican su desviación.

Ejemplo:

~~~text
Región Mexicali / San Luis
Brecha: -63 reactivaciones

Centro Cívico      -24
Justo Sierra       -18
Nuevo Mexicali     -11
Resto              -10
~~~

Esto alimenta directamente la pestaña Dónde.

No se exige contribución artificial cuando el dominio no permite atribución válida.

---

# 25. SCOPE

Scopes compatibles con Control V1:

~~~text
GLOBAL
REGION
BRANCH_POOL
BRANCH
~~~

Las alertas persistidas deben declarar el scope real evaluado.

La API deberá filtrar por el universo autorizado del usuario.

Ejemplos:

- Dirección puede consultar GLOBAL y profundizar.
- GERENTE_REGIONAL ve únicamente región/pool autorizado y sus sucursales.
- GERENTE ve únicamente su sucursal.

---

# 26. PERMISOS DE CONFIGURACIÓN

Ver Control y administrar Control son permisos distintos.

Capacidades conceptuales:

~~~text
control.view
control.alerts.view
control.alert_rules.view
control.alert_rules.manage
control.alert_rules.activate
control.alerts.debug
~~~

Los nombres definitivos se cerrarán contra el esquema real de permisos.

Requisito:

> El backend debe validar cada capacidad; ocultar un menú en Angular no es seguridad.

---

# 27. UI — ATENCIÓN HOY

La estructura actual de la pantalla puede conservarse.

Atención hoy deja de construir focos localmente y pasa a consumir el Motor de Alertas.

Ejemplo de response:

~~~json
{
  "active_count": 17,
  "focus_count": 4,
  "items": [
    {
      "alert_id": 938,
      "indicator_key": "reactivaciones",
      "severity": "HIGH",
      "headline": "Reactivaciones debajo del ritmo esperado",
      "summary": "13.3% debajo del esperado al corte.",
      "scope": {
        "type": "REGION",
        "id": "MXL_SL",
        "name": "Mexicali / San Luis"
      }
    }
  ]
}
~~~

La UI puede mostrar cuatro focos aunque existan más alertas activas.

Debe existir evolución natural hacia Ver todas las alertas.

---

# 28. UI — DETALLE DE ALERTA

Debe poder responder las cuatro capas existentes de Control.

## 28.1 Resumen

- estado;
- severidad;
- valor real;
- referencia;
- brecha;
- desde cuándo;
- evolución.

## 28.2 Por qué

- regla;
- versión;
- método;
- actual;
- esperado/meta/límite;
- desviación;
- historial mínimo;
- tendencia;
- evidencia relevante.

## 28.3 Dónde

- regiones/sucursales/entidades contribuyentes;
- magnitud de contribución;
- ranking únicamente cuando tenga sentido de negocio.

## 28.4 Fuente

- módulo propietario;
- contrato fuente;
- fecha de corte;
- versión/snapshot;
- cobertura;
- calidad;
- enlace Abrir módulo.

---

# 29. UI — CONFIGURACIÓN DE ALERTAS

La vista administrativa mínima debe contener:

## 29.1 Catálogo

Columnas sugeridas:

- indicador;
- regla;
- tipo;
- activa;
- severidades configuradas;
- persistencia;
- prioridad;
- versión activa;
- última modificación;
- usuario.

## 29.2 Editor

Debe presentar solamente los parámetros válidos para la regla.

No campos libres de código.

## 29.3 Preview

Antes de activar:

- alertas actuales;
- alertas con nueva regla;
- altas;
- bajas;
- cambios de severidad;
- cortes evaluados.

## 29.4 Historial

Debe permitir consultar:

- versiones;
- cambios;
- usuario;
- motivo;
- vigencia.

---

# 30. API CONCEPTUAL — ALERTAS

Los nombres exactos podrán ajustarse en contrato técnico conservando semántica.

## 30.1 Listado

~~~text
GET /api/control/alerts
~~~

Filtros típicos:

- cutoff_date;
- scope_type;
- region_key;
- branch_id;
- status;
- severity;
- indicator_key;
- rule_type.

## 30.2 Detalle

~~~text
GET /api/control/alerts/<alert_id>
~~~

Devuelve:

- alerta;
- evidencia;
- lifecycle;
- rule/version;
- contribución;
- fuente.

## 30.3 Atención hoy

Puede resolverse dentro de overview o mediante:

~~~text
GET /api/control/alerts/focus
~~~

Debe devolver selección priorizada ya resuelta por backend.

---

# 31. API CONCEPTUAL — CONFIGURACIÓN

## 31.1 Catálogo

~~~text
GET /api/control/alert-rules
~~~

## 31.2 Detalle

~~~text
GET /api/control/alert-rules/<rule_key>
~~~

## 31.3 Crear versión draft

~~~text
POST /api/control/alert-rules/<rule_key>/versions
~~~

## 31.4 Preview

~~~text
POST /api/control/alert-rules/<rule_key>/preview
~~~

## 31.5 Activar

~~~text
POST /api/control/alert-rules/<rule_key>/activate
~~~

## 31.6 Historial

~~~text
GET /api/control/alert-rules/<rule_key>/history
~~~

Toda mutación debe exigir autorización backend.

---

# 32. API CONCEPTUAL — EVALUACIÓN

Para debug/admin puede existir:

~~~text
POST /api/control/alerts/evaluate-preview
~~~

Una corrida oficial no debería depender de que un usuario abra Control.

Debe poder ser invocada por pipeline/job programado después de que las fuentes necesarias estén listas.

---

# 33. PERSISTENCIA CONCEPTUAL

Los nombres definitivos requieren contrato técnico y migración Alembic.

Entidades candidatas:

~~~text
control_alert_rules
control_alert_rule_versions
control_alerts
control_alert_events
control_alert_runs
~~~

Puede existir almacenamiento de evidence como JSON estructurado o entidad separada según volumen/auditoría.

## 33.1 control_alert_rules

Identidad estable de regla.

## 33.2 control_alert_rule_versions

Configuración inmutable y auditada.

## 33.3 control_alerts

Estado actual/histórico de cada situación.

## 33.4 control_alert_events

Cambios de lifecycle/severidad.

## 33.5 control_alert_runs

Trazabilidad de cada evaluación oficial/preview.

Todo cambio DB debe ir mediante Alembic.

---

# 34. RUN DE EVALUACIÓN

Cada corrida debe registrar:

~~~text
run_id
mode
as_of_date
started_at
finished_at
status
rules_evaluated
alerts_opened
alerts_updated
alerts_resolved
alerts_unchanged
errors
source_versions
~~~

Una falla parcial no debe ocultarse.

Si una regla no pudo evaluarse por fuente ausente, debe quedar explícito.

---

# 35. ORDEN DE EVALUACIÓN

Flujo recomendado:

~~~text
1. Resolver fecha/corte y modo.
2. Resolver reglas activas y versiones vigentes.
3. Obtener indicador desde provider propietario.
4. Validar calidad/cobertura.
5. Obtener referencia necesaria.
6. Evaluar regla.
7. Calcular severidad.
8. Aplicar persistencia/histeresis.
9. Resolver identidad.
10. Crear/actualizar/resolver.
11. Persistir evidencia/evento.
12. Registrar resultado del run.
~~~

---

# 36. PROVIDERS Y FRONTERA DE DOMINIO

El Motor de Alertas no debe importar indiscriminadamente todos los modelos ORM.

Debe consumir providers/adapters explícitos.

Interfaz conceptual:

~~~python
class ControlAlertMetricProvider:
    indicator_key: str

    def get_value(self, context): ...
    def get_reference(self, context, rule): ...
    def get_breakdown(self, context): ...
    def get_source(self, context): ...
~~~

Los providers traducen contratos existentes; no reimplementan negocio.

---

# 37. PRIMER CASO VERTICAL — REACTIVACIONES

Reactivaciones será el caso piloto para cerrar el ciclo completo.

Debe demostrar:

~~~text
fuente canónica
-> indicador
-> expected pace
-> regla
-> configuración editable
-> preview
-> alerta
-> persistencia
-> dedupe
-> actualización
-> resolución
-> Atención hoy
-> Por qué
-> Dónde
-> Fuente
~~~

Ejemplo:

~~~text
Regla:
reactivaciones.expected_pace

Scope:
REGION MXL_SL

Real:
412

Esperado:
475

Desviación:
-63

Desviación:
-13.3%

Severidad:
HIGH

Desde:
2026-09-14

Última evaluación:
2026-09-18
~~~

---

# 38. MIGRACIÓN DE FOCOS ACTUALES

Después de cerrar Reactivaciones de punta a punta, migrar los focos actuales de Control.

Orden sugerido:

1. Reactivaciones — EXPECTED_PACE.
2. Venta nueva — TARGET_GAP y posteriormente EXPECTED_PACE si aplica.
3. Bajas — TARGET_GAP / límite.
4. Tienda — TARGET_GAP.
5. Ingresos — TARGET_GAP.
6. Mantenimiento — OPERATIONAL_BREACH.
7. Conversión — regla cuando exista benchmark/expected pace contractualmente válido.
8. TREND_DETERIORATION donde haya series confiables.

Durante la migración se conservará paridad visible de Control V1.

---

# 39. COMPATIBILIDAD CON FORECAST OPERATIVO

El contrato de Forecast Operativo ya define:

- actual_mtd;
- projected_close;
- benchmark;
- projected_gap;
- method;
- cobertura.

El Motor de Alertas debe consumir estos resultados para TARGET_GAP cuando corresponda.

No debe volver a proyectar.

Especialmente:

~~~text
scope_projected_close = SUM(branch_projected_close)
~~~

si ésa es la regla oficial del contrato propietario.

---

# 40. CONSISTENCIA VERTICAL

Para una misma fecha, versión y cohorte:

~~~text
GLOBAL -> drill-down REGION X
==
usuario REGION X -> vista inicial
~~~

La alerta agregada y su explicación deben respetar la misma fuente y contexto.

No se permite que el usuario regional vea una severidad distinta por recalcular con otra fórmula.

---

# 41. CALIDAD Y COBERTURA

Cada evaluación debe considerar calidad del dato.

Estados conceptuales:

~~~text
AVAILABLE
PARTIAL
UNAVAILABLE
~~~

Una regla puede definir cobertura mínima.

Ejemplo:

~~~text
minimum_coverage_ratio = 0.80
~~~

Si no se alcanza:

~~~text
evaluation_status = INSUFFICIENT_COVERAGE
~~~

No se deberá presentar una alerta cuantitativa como si fuera completa.

---

# 42. ORDEN Y NÚMERO DE FOCOS

Atención hoy debe permanecer breve.

Parámetro global configurable:

~~~text
max_focus_items
~~~

Valor inicial puede definirse durante calibración; no queda hardcodeado por contrato.

Selección:

- solamente alertas OPEN;
- autorizadas para el usuario;
- ordenadas por prioridad backend;
- sin duplicados semánticos;
- con diversidad razonable de dominio cuando la priorización lo permita.

No se debe degradar una alerta crítica solamente para “dar variedad”.

---

# 43. HISTORIAL DE ALERTAS

Fase 2 conserva alertas resueltas.

Esto permitirá posteriormente responder:

- ¿qué problemas se repiten?;
- ¿qué sucursal entra más veces en desviación?;
- ¿cuánto duran las alertas?;
- ¿qué reglas generan demasiado ruido?;
- ¿qué severidades se resuelven solas?;
- ¿qué cambios de configuración mejoraron la señal?

El historial es producto de la trazabilidad, no un requisito de UI ejecutiva pesada en primera entrega.

---

# 44. OBSERVABILIDAD

El backend debe poder registrar y diagnosticar:

- tiempo por regla;
- errores de provider;
- datos insuficientes;
- cantidad evaluada;
- cantidad alertada;
- cambios de lifecycle;
- regla/version;
- source_version.

No se deben tragar excepciones y producir “sin alertas” como si fuera un estado sano.

---

# 45. PERFORMANCE

No se recalculará historia pesada en cada render de Angular.

Expected pace y fuentes costosas deberán resolverse mediante una estrategia apropiada:

- snapshot;
- mart;
- precálculo;
- job;
- cache controlado;
- combinación.

La elección final se cierra en contrato técnico.

Principio:

> Abrir Centro de Control no debe disparar una reconstrucción histórica completa.

---

# 46. SEGURIDAD DE CONFIGURACIÓN

La pantalla de calibración es de alto impacto.

Debe cumplir:

- JWT;
- autorización backend;
- CSRF según arquitectura vigente cuando aplique;
- validación de payload;
- auditoría;
- no ejecutar código enviado por cliente;
- no aceptar IDs de scope no autorizados;
- no permitir activar dos versiones incompatibles simultáneamente.

---

# 47. PRUEBAS OBLIGATORIAS

## 47.1 Determinismo

Mismos inputs y misma versión producen mismo resultado.

## 47.2 Dedupe

Dos corridas oficiales con la misma condición no crean dos alertas.

## 47.3 Update

Una condición que empeora actualiza alerta existente.

## 47.4 Resolución

Una condición recuperada según configuración pasa a RESOLVED.

## 47.5 Versionado

Cambiar HIGH de -10% a -15% no altera el rule_version de alertas históricas.

## 47.6 Preview

Preview no modifica alertas oficiales.

## 47.7 Seguridad

Usuario sin permiso de configuración recibe 403 aunque llame endpoint manualmente.

## 47.8 Scope

Regional no obtiene alertas fuera de sus sucursales.

## 47.9 Calidad

Historia/cobertura insuficiente no produce expected inventado.

## 47.10 Propiedad de fórmula

TARGET_GAP de Forecast consume projected_gap oficial, no lo recalcula con fórmula divergente.

## 47.11 Frontend

No existe lógica de severidad/regla crítica en HTML.

El TypeScript de Control no debe decidir direcciones de indicadores ni thresholds después de la migración.

---

# 48. CRITERIOS DE ACEPTACIÓN DE CONFIGURACIÓN

La calibración se considera implementada cuando un usuario autorizado puede:

1. abrir Configuración de alertas;
2. seleccionar una regla;
3. ver versión activa;
4. modificar parámetros permitidos;
5. recibir validación;
6. ejecutar preview;
7. ver impacto estimado;
8. guardar nueva versión;
9. activarla;
10. consultar auditoría;
11. confirmar que el siguiente run oficial usa la nueva versión;
12. hacer todo lo anterior sin cambio de código ni deploy.

---

# 49. CRITERIOS DE ACEPTACIÓN DE FASE 2

Fase 2 se considera terminada cuando:

1. existe Motor de Alertas backend independiente de Angular;
2. al menos Reactivaciones completa el ciclo vertical;
3. las reglas están persistidas/versionadas;
4. los parámetros se editan desde Suite;
5. preview no modifica producción;
6. existe deduplicación;
7. existe lifecycle OPEN/RESOLVED;
8. existe auditoría de configuración;
9. existe auditoría de evaluación;
10. toda alerta puede explicar real, referencia y brecha;
11. toda alerta identifica scope;
12. toda alerta identifica fuente;
13. Atención hoy consume alertas backend;
14. el frontend ya no decide qué es adverso;
15. el frontend ya no asigna severidad de negocio;
16. permisos se aplican en backend;
17. datos insuficientes se declaran;
18. expected pace no se inventa;
19. alertas históricas conservan su rule_version;
20. cambios DB están respaldados por Alembic;
21. pruebas cubren dedupe, lifecycle, permisos y versionado;
22. Control V1 conserva paridad funcional durante la migración.

---

# 50. ORDEN DE IMPLEMENTACIÓN PROPUESTO

## 50.1 F2A — Fundación

- modelos de reglas/versiones;
- modelo de alerta;
- modelo de run/evento;
- permisos;
- API de configuración;
- UI Configuración de alertas;
- preview;
- migraciones Alembic.

## 50.2 F2B — Reactivaciones vertical

- provider;
- expected pace;
- regla;
- persistencia;
- dedupe;
- lifecycle;
- detalle;
- integración con Atención hoy.

## 50.3 F2C — Migrar focos V1

- venta nueva;
- bajas;
- tienda;
- ingresos;
- mantenimiento.

Eliminar progresivamente decisiones equivalentes de control-center.component.ts.

## 50.4 F2D — Tendencia y endurecimiento

- TREND_DETERIORATION;
- hysteresis;
- optimización de performance;
- observabilidad;
- calibración con datos reales;
- casos borde de historia/cobertura.

---

# 51. DECISIONES CERRADAS

Quedan cerradas por este contrato:

1. Fase 2 es Motor de Alertas, no rediseño del dashboard.
2. El motor vive en backend.
3. Angular no decide alertas.
4. Reactivaciones es el primer caso vertical.
5. Las alertas son persistentes y deduplicadas.
6. El lifecycle mínimo es OPEN / RESOLVED.
7. Expected Pace es referencia formal cuando aplica.
8. Datos insuficientes no generan referencias inventadas.
9. Los thresholds son configurables.
10. La configuración se edita desde Suite.
11. Cambiar calibración no requiere deploy.
12. Configuración se versiona.
13. Alertas guardan rule_version.
14. Toda modificación se audita.
15. Debe existir preview antes de activar cambios.
16. Preview no muta alertas oficiales.
17. Los focos actuales se migran al motor.
18. Atención hoy seguirá siendo breve.
19. El backend continúa siendo fuente real de permisos.
20. IA no decide la existencia de alertas.

---

# 52. PARÁMETROS PENDIENTES DE CALIBRACIÓN

No bloquean implementación arquitectónica:

- thresholds iniciales por indicador;
- open_after_runs;
- resolve_after_runs;
- ventanas de tendencia;
- historia mínima;
- cobertura mínima;
- prioridad por indicador;
- max_focus_items;
- tolerancias/histeresis;
- fallback permitido por expected pace.

Estos valores se decidirán y ajustarán usando la propia pantalla de configuración.

Precisamente por eso no deben quedar hardcodeados.

---

# 53. REGLA FINAL

Centro de Control Fase 2 no debe convertirse en un tablero con más números.

Debe convertirse en una capa de detección reproducible, explicable y configurable encima de los datos confiables de Suite Ultra.

La condición final es:

> Suite Control puede detectar, conservar, explicar, localizar, priorizar y resolver automáticamente desviaciones relevantes, mientras negocio puede calibrar sus parámetros desde Suite con autorización, preview, versionado y auditoría, sin cambiar código ni desplegar.
