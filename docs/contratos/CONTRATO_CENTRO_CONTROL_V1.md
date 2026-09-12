# CONTRATO — CENTRO DE CONTROL SUITE ULTRA V1

**Estado:** Aprobado para implementación  
**Versión:** 1.0  
**Producto:** Suite Ultra — Centro de Control  
**Propósito:** contrato funcional, de datos, permisos, navegación y arquitectura para la capa ejecutiva de Suite Ultra.

---

## 1. Propósito

Centro de Control es la capa ejecutiva de Suite Ultra.

No es un dashboard adicional ni un reemplazo de Track, Tickets, Mantenimiento, Marketing, Warehouse u otros módulos. Su función es comprimir el estado de Ultra en señales accionables y permitir profundizar desde cada señal hasta su explicación, ubicación y evidencia fuente.

Control debe responder, en este orden:

1. ¿Cómo estamos?
2. ¿Cómo vamos a terminar?
3. ¿Qué se está desviando?
4. ¿Por qué?
5. ¿Dónde?
6. ¿Qué estamos haciendo al respecto?

Principio rector:

> La complejidad crece hacia abajo, nunca hacia arriba.

Mientras más información exista dentro de Suite Ultra, más simple debe sentirse la primera pantalla de Control.

---

## 2. Invariantes del producto

Estas reglas son obligatorias para cualquier implementación V1 o posterior compatible.

### 2.1 Una sola realidad

Existe un solo Centro de Control y un solo contrato de métricas.

No se crearán dashboards independientes para Dirección, LECTOR_GLOBAL, GERENTE_REGIONAL o GERENTE con definiciones diferentes del mismo KPI.

La perspectiva cambia por alcance autorizado y dominios permitidos; la verdad no cambia.

### 2.2 Consistencia vertical

Un usuario situado en un nivel inferior debe observar exactamente el mismo resultado que un usuario superior obtendría al profundizar hasta ese mismo nivel bajo:

- el mismo periodo;
- el mismo corte;
- la misma definición de KPI;
- la misma versión o snapshot fuente;
- los mismos filtros de negocio aplicables.

Ejemplo:

Si Dirección consulta `Ultra -> Región Mexicali / San Luis` y obtiene Forecast `$X`, el GERENTE_REGIONAL autorizado para esa misma región debe obtener `$X` para el mismo corte.

Una diferencia implica un bug, una diferencia de versión/corte explícitamente visible o la existencia de contratos incompatibles.

### 2.3 El backend define seguridad

El frontend nunca es fuente de autorización.

Todo alcance solicitado debe intersectarse con el alcance autorizado resuelto por backend.

Conceptualmente:

```text
scope_efectivo = scope_solicitado ∩ scope_autorizado
```

Nunca:

```text
scope_efectivo = scope_solicitado
```

Modificar parámetros, rutas o requests desde navegador no debe permitir ampliar el universo autorizado.

### 2.4 Control no duplica lógica de dominio

El módulo propietario calcula; Control interpreta y presenta.

Ejemplos:

- Track/Forecast es propietario del forecast.
- El módulo de Conversión es propietario de lead -> venta.
- Track/KPI es propietario de venta nueva, reactivaciones y bajas cuando corresponda.
- Maintenance Planner/Tickets es propietario de compromisos y estado operativo de mantenimiento.

Control no debe reimplementar esas fórmulas mediante queries ORM paralelos salvo que el cálculo sea, por definición, una métrica propia de Control y esté versionado como tal.

### 2.5 Ningún número termina en Control

Todo KPI ejecutivo debe poder responder:

```text
Señal -> Por qué -> Dónde -> Evidencia
```

Cuando exista operación asociada:

```text
Señal -> Por qué -> Dónde -> Evidencia -> Abrir módulo propietario
```

### 2.6 Preservación de contexto

Al profundizar y regresar se conservan, cuando apliquen:

- periodo;
- fecha de corte;
- alcance;
- región;
- sucursal;
- indicador seleccionado;
- filtros válidos.

### 2.7 Información por excepción

Nivel 0 no intenta exhibir todos los KPI disponibles.

Prioriza:

- desviaciones;
- brechas;
- riesgos;
- concentraciones anormales;
- compromisos vencidos;
- eventos que requieren conversación o acción.

Control no debe convertirse en una colección de semáforos ni en una pared de tarjetas.

---

## 3. Modelo de alcance organizacional

Jerarquía base:

```text
ULTRA
  -> REGIÓN
      -> SUCURSAL
          -> ENTIDAD OPERATIVA
```

La entidad operativa depende del dominio y puede ser, entre otras:

- ticket;
- equipo;
- lead;
- venta;
- socio;
- campaña;
- snapshot;
- reporte;
- responsable.

### 3.1 Tipos de scope V1

```text
GLOBAL
REGION
BRANCH_POOL
BRANCH
```

`BRANCH_POOL` representa un conjunto explícito de sucursales autorizadas cuando todavía no existe una única región canónica o cuando el usuario tiene una asignación operativa particular.

### 3.2 Regla de inicio

Cada usuario inicia en el nivel máximo que puede observar.

Ejemplos esperados:

- ADMIN / ADMINISTRADOR / SUPER_ADMIN / LECTOR_GLOBAL: GLOBAL.
- GERENTE_REGIONAL: REGION cuando sus sucursales autorizadas resuelven de forma consistente a una región; en caso contrario BRANCH_POOL explícito.
- GERENTE: BRANCH.

Los roles exactos por dominio siguen sujetos a autorización de backend; este contrato no convierte automáticamente a todos los roles en lectores de todos los dominios.

### 3.3 Alcance regional

GERENTE_REGIONAL no es global por definición.

Su universo se deriva de asignaciones autorizadas (`sucursales_ids` y/o gobernanza regional canónica) y nunca de un selector del frontend.

Si no existe una asignación válida, la respuesta correcta es denegar o devolver un estado explícito de configuración incompleta; no ampliar silenciosamente a GLOBAL.

---

## 4. Permisos por dominio

Scope responde:

> ¿Sobre qué parte de Ultra puedo consultar?

Domain access responde:

> ¿Qué información puedo consultar?

Ambos son independientes.

Ejemplo conceptual:

```json
{
  "role": "GERENTE_REGIONAL",
  "scope": {
    "type": "REGION",
    "region_keys": ["MXL_SL"],
    "branch_ids": [1, 2, 3, 4]
  },
  "domains": {
    "commercial": true,
    "conversion": true,
    "retention": true,
    "maintenance": true,
    "corporate_finance": false,
    "confidential_hr": false
  }
}
```

Control debe omitir o marcar como no autorizado un dominio no permitido; no debe filtrar únicamente la navegación visual.

---

## 5. Modelo de profundidad

### Nivel 0 — Ejecutivo

Vista inicial utilizable durante una junta.

Debe responder rápidamente:

- estado;
- tendencia/proyección;
- brecha;
- focos prioritarios.

Recomendación visual V1: entre 4 y 6 señales principales simultáneas más una sección breve de `Atención hoy`.

### Nivel 1 — Explicación

Responde:

> ¿Por qué está pasando?

Presenta variables explicativas relevantes, no todos los datos disponibles.

Ejemplo:

```text
Forecast debajo de meta
- Leads: +8%
- Conversión: -1.2 pp
- Reactivaciones: -11%
- Venta promedio: estable
```

### Nivel 2 — Ubicación

Responde:

> ¿Dónde está pasando?

Permite bajar por las dimensiones válidas para el dominio:

```text
Ultra -> Región -> Sucursal -> entidad
```

Un usuario cuyo máximo scope sea REGION inicia directamente en región y no obtiene navegación hacia GLOBAL.

### Nivel 3 — Evidencia

Responde:

> ¿De dónde salió este número?

Debe identificar como mínimo:

- módulo propietario;
- contrato/versión del cálculo;
- fecha/corte;
- snapshot, versión, corrida o entidad fuente cuando exista;
- cobertura/calidad del dato cuando aplique.

Desde este nivel puede aparecer `Abrir en módulo`.

---

## 6. Contrato mínimo de KPI

Todo KPI presentado por Control debe normalizarse a un contrato equivalente al siguiente.

```json
{
  "metric_key": "commercial.forecast",
  "contract_version": "commercial_forecast.v1",
  "title": "Forecast de cierre",
  "value": 18700000,
  "unit": "MXN",
  "period": {
    "type": "MONTH",
    "from": "2026-09-01",
    "to": "2026-09-30",
    "cutoff": "2026-09-12"
  },
  "comparison": {
    "type": "TARGET",
    "value": 20000000,
    "label": "Meta mensual"
  },
  "delta": {
    "value": -1300000,
    "unit": "MXN"
  },
  "status": "ATTENTION",
  "explanation": "La conversión y reactivaciones están debajo del ritmo esperado.",
  "source": {
    "module": "track",
    "contract": "commercial_forecast.v1",
    "updated_at": "2026-09-12T08:05:00-07:00",
    "version_id": null,
    "snapshot_id": null
  },
  "quality": {
    "status": "AVAILABLE",
    "eligible_entities": 26,
    "included_entities": 26,
    "notes": []
  },
  "drilldown": {
    "available": true,
    "next_dimension": "REGION",
    "allowed_dimensions": ["REGION", "BRANCH", "SOURCE"]
  }
}
```

### 6.1 Campos obligatorios

- `metric_key`: identificador estable y único.
- `contract_version`: versión semántica del cálculo/adapter.
- `title`: nombre ejecutivo.
- `value`: valor actual; puede ser null si calidad/estado lo exige.
- `unit`: unidad explícita.
- `period`: periodo y corte efectivo.
- `comparison`: referencia significativa cuando exista.
- `delta`: diferencia contra referencia cuando exista.
- `status`: estado semántico.
- `source.module`: módulo propietario.
- `source.contract`: contrato fuente.
- `source.updated_at`: corte real cuando esté disponible.
- `quality`: cobertura/calidad del cálculo.
- `drilldown`: capacidades de profundización.

### 6.2 Estados semánticos V1

```text
NORMAL
ATTENTION
CRITICAL
INFORMATIONAL
UNAVAILABLE
```

Los colores son una representación del estado, no el estado mismo.

### 6.3 Calidad de dato V1

```text
AVAILABLE
PARTIAL
UNAVAILABLE
```

Un valor parcial o no disponible debe explicarlo. Control no inventa sustitutos silenciosos.

---

## 7. Contrato de contexto de Control

Todo response principal de Control debe declarar el contexto efectivo utilizado.

Ejemplo:

```json
{
  "context": {
    "requested_scope": {
      "type": "GLOBAL"
    },
    "effective_scope": {
      "type": "REGION",
      "region_keys": ["MXL_SL"],
      "branch_ids": [1, 2, 3, 4]
    },
    "max_scope": "REGION",
    "domains": ["commercial", "conversion", "retention", "maintenance"],
    "period": {
      "from": "2026-09-01",
      "to": "2026-09-30",
      "cutoff": "2026-09-12"
    }
  }
}
```

La UI debe presentar el `effective_scope`, nunca asumir que el scope solicitado fue aceptado.

---

## 8. Registro de métricas / adapters

Control debe integrar dominios mediante adapters explícitos y no mediante imports directos indiscriminados de modelos ORM.

Interfaz conceptual:

```python
class ControlMetricProvider:
    domain: str

    def get_summary(self, context): ...
    def get_explanation(self, metric_key, context): ...
    def get_breakdown(self, metric_key, dimension, context): ...
    def get_source(self, metric_key, context): ...
```

Registro conceptual:

```text
Control Metric Registry
  -> Commercial / Track adapter
  -> Conversion adapter
  -> Retention / KPI adapter
  -> Maintenance adapter
  -> futuros adapters
```

Un adapter traduce el contrato nativo de un módulo al contrato común de Control sin apropiarse de su lógica de negocio.

---

## 9. API pública propuesta V1

Los nombres exactos pueden variar durante implementación si se documenta la razón, pero la semántica debe mantenerse.

### 9.1 Contexto

```text
GET /api/control/context
```

Devuelve:

- role público relevante;
- max_scope;
- effective/authorized scope;
- dominios habilitados;
- dimensiones navegables.

### 9.2 Overview

```text
GET /api/control/overview
```

Parámetros típicos:

- `cutoff_date`
- `scope_type`
- `region_key`
- `branch_id`

Devuelve:

- context efectivo;
- principales métricas normalizadas;
- sección `attention_items`;
- metadata de corte.

### 9.3 Drill-down de métrica

```text
GET /api/control/metrics/<metric_key>
```

Puede aceptar:

- `level=explanation`
- `level=breakdown`
- `dimension=region|branch|source`
- contexto/filtros válidos.

### 9.4 Regla de no duplicación

Los endpoints de Control pueden orquestar providers existentes, pero no deben convertirse en una segunda implementación de Track, Forecast, Funnel o Maintenance Planner.

---

## 10. Navegación frontend

### 10.1 Regla principal

Seleccionar un KPI no debe expulsar inmediatamente al usuario a otro módulo.

Primero se profundiza dentro de Control.

Solo cuando se necesita consultar u operar la entidad fuente aparece `Abrir en módulo`.

### 10.2 Breadcrumb obligatorio

Ejemplos:

```text
Ultra > Comercial > Forecast > Región MXL / SL > Tecnológico
```

```text
Región MXL / SL > Mantenimiento > Tecnológico > Ticket #4812
```

El breadcrumb nunca debe ofrecer un ancestro superior al `max_scope` autorizado.

### 10.3 Filtros

Los filtros son contexto de consulta, no seguridad.

Un usuario global puede manipular alcance entre Ultra, regiones y sucursales autorizadas.

Un regional puede manipular sucursales dentro de su universo.

Un gerente puede manipular dimensiones internas de su sucursal pero no cambiar a otra sucursal no autorizada.

---

## 11. Atención ejecutiva

Control diferencia cuatro conceptos:

```text
INFORMACIÓN
DESVIACIÓN
ATENCIÓN
ACCIÓN
```

Nivel 0 prioriza `ATENCIÓN` y `ACCIÓN`.

Cada attention item debe permitir identificar:

- qué ocurre;
- impacto o magnitud;
- dominio;
- scope afectado;
- KPI relacionado;
- siguiente drill-down disponible.

Estado futuro deseado:

```text
Señal -> explicación -> responsable -> acción -> fecha compromiso -> resultado
```

V1 puede iniciar sin gestionar todas las acciones, pero no debe bloquear esta evolución arquitectónica.

---

## 12. Dominios iniciales V1

### 12.1 Comercial

Objetivo: responder cómo vamos y cómo vamos a terminar.

Candidatos iniciales:

- ingreso real MTD;
- meta;
- ritmo esperado;
- forecast de cierre;
- brecha proyectada;
- cobertura/calidad del forecast.

Fuente principal esperada: Track/Forecast y sus fuentes canónicas.

### 12.2 Conversión

Objetivo: explicar si el problema comercial está en generación o transformación de demanda.

Cadena objetivo:

```text
Lead -> contacto -> visita/intención -> venta
```

Métricas candidatas:

- leads válidos;
- ventas atribuidas;
- conversión lead -> venta;
- conversiones intermedias disponibles;
- comparación temporal;
- concentración regional/sucursal.

La definición de lead y atribución de venta debe pertenecer al módulo de Conversión, no a Control.

### 12.3 Retención

Candidatos:

- reactivaciones;
- bajas;
- metas/límites;
- ritmo/proyección cuando exista;
- concentración del deterioro.

### 12.4 Operación / Mantenimiento

Candidatos:

- tickets activos;
- tickets vencidos;
- equipos fuera de operación;
- tickets sin fecha compromiso;
- compromisos de la semana;
- cumplimiento de compromisos;
- sucursales con mayor concentración.

Fuente principal esperada: Tickets + Maintenance Planner, respetando sus permisos y contratos.

---

## 13. Trazabilidad y fuente de verdad

Toda métrica debe poder declarar su procedencia.

Para información proveniente de Warehouse/Track se priorizará:

- versión Track efectiva;
- snapshot canónico;
- `business_date` / `track_date`;
- `report_type_key` cuando corresponda;
- estado de canonicalidad.

Para dominios OLTP se priorizará:

- entidad fuente;
- ID estable;
- timestamps de negocio;
- historial cuando exista.

Control nunca debe ocultar una inconsistencia de fuente mediante un cálculo alternativo silencioso.

---

## 14. Reglas visuales

La vista Nivel 0 debe poder usarse en Meet sin explicación previa extensa.

Evitar:

- mosaicos excesivos;
- veinte KPI simultáneos;
- colores decorativos;
- gráficas sin decisión asociada;
- tablas extensas en portada;
- duplicación de información;
- textos operativos largos.

Priorizar:

- jerarquía visual;
- comparación;
- brecha;
- tendencia/proyección;
- concentración;
- excepción;
- compromiso operativo;
- drill-down evidente.

Frase de producto:

> La primera pantalla muestra dónde preguntar; cada clic responde la siguiente pregunta.

---

## 15. Criterios de aceptación V1

Una métrica está correctamente integrada cuando el usuario autorizado puede:

1. entender su situación en pocos segundos;
2. identificar si requiere atención;
3. seleccionar la métrica;
4. comprender su explicación principal;
5. localizar región/sucursal/entidad responsable cuando aplique;
6. identificar la fuente y corte;
7. abrir el módulo propietario cuando necesite detalle operativo;
8. regresar sin perder contexto.

### 15.1 Prueba de consistencia vertical

Debe existir una prueba automatizable equivalente a:

```text
GLOBAL drill-down a REGION X
==
usuario REGION X en su vista inicial
```

para cada KPI que soporte ambos scopes.

### 15.2 Prueba de seguridad

Solicitar manualmente un scope superior o una sucursal no autorizada debe devolver 403 o limitar explícitamente al scope autorizado según la semántica documentada del endpoint.

Nunca debe filtrar únicamente en frontend.

### 15.3 Prueba de propiedad

Una métrica integrada no debe contener una segunda fórmula divergente dentro de Control si ya existe un cálculo canónico en su módulo propietario.

---

## 16. Migración desde el Control actual

La implementación actual se considera una V0/prototipo válida y no debe borrarse a ciegas.

Migración incremental:

1. introducir Control Context y resolver scope autorizado;
2. crear contrato/modelos comunes de métricas;
3. encapsular Track/Forecast mediante adapter;
4. migrar el componente Angular para consumir ControlService en lugar de depender directamente de TrackService;
5. habilitar drill-down contextual;
6. corregir alcance de GERENTE_REGIONAL;
7. integrar Conversión;
8. integrar Maintenance Planner;
9. retirar código V0 únicamente cuando exista paridad funcional verificada.

No se requiere migración de base de datos para introducir el contrato o la capa de orquestación si no se agregan campos persistentes.

---

## 17. Deuda conocida que este contrato debe resolver

### 17.1 Scope regional inconsistente

Existe lógica previa donde algunos servicios tratan a GERENTE_REGIONAL como global mientras otros respetan `sucursales_ids`.

Control V1 debe unificar esa semántica.

GERENTE_REGIONAL no debe recibir scope global por el solo hecho de su rol.

### 17.2 Acoplamiento directo del frontend a Track

El Control actual consume contratos de Track directamente.

V1 debe introducir una frontera `ControlService` / `/api/control/*` para que la UI ejecutiva no dependa de estructuras internas de cada dominio.

### 17.3 Evolución de permisos

Los permisos de dominio deben centralizarse gradualmente sin romper los permisos propios de cada backend fuente.

Control agrega una capa de lectura autorizada; nunca debilita el guard del módulo propietario.

---

## 18. No objetivos de V1

V1 no pretende:

- reemplazar Warehouse;
- reemplazar Track;
- reemplazar Maintenance Planner;
- centralizar todos los cálculos de Suite;
- convertirse en motor genérico de BI externo;
- ejecutar acciones destructivas desde la portada;
- resolver toda la gestión de compromisos corporativos en la primera entrega.

---

## 19. Regla final

Cuando exista duda entre mostrar más información o conservar claridad, Control conservará claridad y ofrecerá profundidad mediante drill-down.

> Control no muestra toda la empresa al mismo tiempo. Muestra lo que merece atención y garantiza un camino verificable hasta la realidad que produjo cada señal.
