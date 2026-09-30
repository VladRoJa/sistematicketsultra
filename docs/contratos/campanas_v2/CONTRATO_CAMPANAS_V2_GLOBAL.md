# Contrato global — Campañas V2

Estado: BASE CONTRACTUAL PARA IMPLEMENTACIÓN POR FASES  
Fecha: 2026-09-30  
Alcance: arquitectura global, convivencia con legacy y límites entre Fase 1, Fase 2 y Fase 3.

## 1. Objetivo

Campañas V2 será un módulo nuevo de Suite Ultra para construir audiencias, congelar cohortes, clasificar campañas, leer resultados de proveedores y, en una fase posterior, enviar campañas.

No se refactoriza ni se sustituye de inicio el módulo legacy de Reactivaciones. Ambos deben convivir hasta que V2 demuestre en operación real que cubre los flujos requeridos.

El objetivo arquitectónico es que las APIs nuevas de iVentas entren como una integración plug-and-play: el núcleo de Campañas V2 no debe quedar acoplado a endpoints, payloads, credenciales o peculiaridades de iVentas.

## 2. División obligatoria en tres fases

### Fase 1 — Núcleo V2 y constructor de audiencias

- No envía WhatsApp.
- No requiere API nueva de iVentas.
- Define catálogo, fuentes, filtros, familias, preview, deduplicación y audiencia congelada.

### Fase 2 — Integración analítica con iVentas + Cartera Funnel

- Solo lectura/sincronización de iVentas.
- Estados por destinatario, interacciones, analytics, costos e histórico.
- Importación de campañas externas.
- Incorpora antes del enviador una fuente `FUNNEL_PORTFOLIO` para Venta Nueva/Funnel, tolerante a registros donde prácticamente solo existe teléfono.
- No envía campañas desde Suite.

### Fase 3 — Envío por iVentas

- Selección de plantilla, variables, canal, programación y POST /v2/broadcast.
- Guarda provider_campaign_id y enlaza automáticamente con Fase 2.
- Solo después se evalúa retirar el legacy.

Regla: no adelantar trabajo de una fase si la fase anterior no tiene sus criterios de aceptación cerrados.

## 3. Investigación del repositorio realizada antes de este contrato

Este contrato no parte de cero. En main ya existe infraestructura de Marketing que debe reutilizarse cuando su semántica sea compatible.

### 3.1 Campañas legacy ya persistidas y cohortes congeladas

Existen:

- backend/app/models/marketing.py
  - MarketingReactivationCampaignORM
  - MarketingReactivationCampaignRecipientORM
  - MarketingReactivationTariffORM
- backend/app/services/marketing_reactivation_service.py
- backend/app/services/marketing_campaign_explorer_creation_service.py
- backend/app/services/marketing_campaign_export_service.py

Hallazgo: el legacy ya congela destinatarios y protege unicidad por campaña + teléfono. marketing_campaign_explorer_creation_service.py reconstruye en backend la selección antes de persistir; el navegador no es autoridad sobre IDs de destinatarios.

Decisión: V2 debe conservar ese principio. No se debe copiar la selección enviada por Angular como verdad.

### 3.2 Audience Explorer ya existente

Existen:

- backend/app/services/marketing_campaign_audience_service.py
- backend/app/services/marketing_campaign_preview_detail_service.py
- backend/app/services/marketing_campaign_explorer_creation_service.py
- frontend/src/app/marketing-reactivation/marketing-audience-explorer-dialog.component.*
- frontend/src/app/marketing-reactivation/marketing-audience-explorer.models.ts

Ya hay:

- preview;
- drill-down;
- paginación;
- filtros por sucursal, categoría de tarifa y tarifa;
- historial Suite;
- enriquecimiento con estado iVentas existente;
- validación de que el detalle coincide con el contador del preview;
- deduplicación final por teléfono.

Decisión: Fase 1 no debe reimplementar estas capacidades sin revisar primero qué helpers pueden extraerse o reutilizarse. Sin embargo, V2 no debe quedar dependiente de los buckets rígidos de Reactivaciones V1.

### 3.3 Normalización y persistencia iVentas ya existente

Existen:

- backend/app/services/marketing_iventas_service.py
- backend/app/services/marketing_iventas_branch_service.py
- backend/app/services/marketing_iventas_leads_service.py
- backend/app/services/marketing_iventas_*_persistence_service.py
- modelos MarketingIventas* en backend/app/models/marketing.py

El repo ya contiene dos niveles útiles de normalización: `backend/app/services/marketing_phone.py::normalize_phone()` es el normalizador general que ya consumen Funnel y Contact Center, mientras que `marketing_iventas_service.py::normalize_iventas_phone()` conserva semántica específica de iVentas. El núcleo genérico de audiencias debe preferir `normalize_phone()` y el adapter iVentas reutilizar su normalizador específico. No crear un tercer normalizador.

También existe resolución de sucursales iVentas mediante:

- source_family = iventas_family;
- resolver Track;
- backend/app/services/marketing_iventas_branch_service.py.

Decisión: queda prohibido crear en servicios un diccionario duplicado branch iVentas -> sucursal Suite. El caso Tecnológico ya fue corregido en migración para usar tecnologico-2 como alias activo hacia TEC_MXL.

### 3.4 Fuentes Warehouse ya resueltas

Socios activos:

- backend/app/warehouse/services/socios_activos_snapshot_resolver.py
- resolve_latest_canonical_socios_activos_snapshot()

Socios vencidos:

- backend/app/warehouse/services/socios_vencidos_current_status_resolver.py
- backend/app/warehouse/services/socios_vencidos_reactivation_candidate_resolver.py

Decisión: V2 debe consumir estas fuentes/resolvers. No debe reimplementar canonicalidad ni lógica de identidad de socios vencidos vs activos.

Regla adicional: **no crear tablas espejo de Socios Activos ni Socios Vencidos para Campañas V2**. Las bases canónicas ya existen y deben consultarse/referenciarse. Una fila de destinatario de campaña representa pertenencia a un cohorte, no una copia de la base fuente.

Para Socios Vencidos se debe conservar la referencia al episodio canónico existente (`socios_vencidos_cartera_id` cuando aplique). Para Socios Activos se debe conservar la referencia al snapshot/fila canónica cuando el modelo vigente lo permita. Solo se persiste en la campaña la metadata mínima necesaria para congelar la selección o sobrevivir a una política de retención demostrada; no se repuebla otra base completa.

### 3.5 Cartera Funnel / Venta Nueva ya tiene detalle individual reutilizable

Existen servicios de detalle del Funnel (`marketing_sales_funnel_detail_service.py`, `marketing_sales_funnel_iventas_stage_service.py` y drill-downs) y `marketing_phone.py`. Además Contact Center ya consume contactos CRM/Funnel.

Decisión: `FUNNEL_PORTFOLIO` se integra en Fase 2, antes del enviador. Su contrato mínimo es phone-centric: `phone_mx10` puede ser el único dato confiable. Nombre, sucursal, contact_id, canal o fecha son enriquecimientos opcionales; no se inventan member_id, PIN, tarifa ni sucursal.

Además, la cartera Funnel debe aplicar una **supresión obligatoria contra Socios Activos** usando el snapshot canónico vigente. Si el teléfono destinatario aparece asociado a un socio actualmente activo, ese número no entra a una campaña de Venta Nueva. Esta supresión se resuelve en preview; no se copia la base de activos ni se agrega un flag permanente al lead.

### 3.6 Envío registrado y atribución de Reactivaciones ya existente

Existen:

- backend/app/models/marketing_campaign_delivery.py
- backend/app/services/marketing_campaign_delivery_service.py
- backend/app/models/marketing_reactivation_outcome.py
- backend/app/services/marketing_reactivation_outcome_service.py
- docs/contratos/contrato_reactivaciones_atribuidas_campana_v1.md

El legacy ya registra envíos por sucursal y existe atribución last-touch de Reactivaciones.

Decisión: V2 no debe duplicar ese motor de atribución. Cuando una campaña V2 de tipo REACTIVATION necesite atribución, la implementación debe investigar si el motor existente puede recibir una interfaz común o un adaptador sin romper el legacy.

## 4. Principios de arquitectura

### 4.1 Nuevo módulo, no refactor destructivo

V2 tendrá rutas, frontend y persistencia propias donde la semántica legacy no sea suficientemente general.

Se permite extraer helpers comunes del legacy únicamente cuando:

- el comportamiento actual quede protegido por pruebas;
- el helper sea realmente genérico;
- no se cambie el contrato del legacy como efecto lateral.

No se debe generalizar el legacy a la fuerza para ahorrar tablas si eso mezcla semánticas incompatibles.

### 4.2 Reutilizar antes de crear

Antes de cada servicio/modelo/helper nuevo, la implementación debe responder:

1. ¿Existe ya algo equivalente?
2. ¿La semántica es la misma o solo se parece?
3. ¿Puede reutilizarse sin acoplar V2 al legacy?
4. ¿Conviene extraer una utilidad compartida?
5. ¿La nueva pieza es una excepción pertinente por tener un ciclo de vida distinto?

### 4.3 Backend como autoridad

Angular:

- estructura visual;
- bindings;
- selección;
- llamadas a servicios.

Backend:

- permisos;
- construcción real de audiencia;
- clasificación;
- deduplicación;
- validaciones;
- persistencia;
- integración de proveedor.

El frontend nunca será autoridad para decidir destinatarios finales.

## 5. Conceptos canónicos

### 5.1 Propósito comercial de campaña

Valores iniciales:

- NEW_SALE — Venta nueva
- REACTIVATION — Reactivación
- ACTIVE_MEMBERS — Socios activos
- UNCLASSIFIED — Sin clasificar

Este propósito sirve para análisis y asignación de costo. No describe la tarifa del destinatario.

### 5.2 Familia de audiencia

Familias principales definidas por el catálogo recibido:

- DOMICILIADO
- TRIMESTRAL
- CONVENIO
- SEMESTRE
- ESTUDIANTE

El catálogo recibido también contiene:

- mes
- Fuera de segmento

Estado:

- mes queda PENDIENTE de decisión de negocio. No asumir si será sexta familia, si se integrará en otra o si se excluirá.
- Fuera de segmento debe conservarse explícitamente y no mezclarse en las cinco familias.

### 5.3 Categoría de tarifa

La categoría de tarifa es un nivel distinto de familia de audiencia.

Cadena conceptual:

    Tarifa Gasca
        -> categoria_tarifa
        -> audience_family

La columna llamada plantilla en el Excel de negocio debe renombrarse conceptualmente en V2 a audience_family para evitar confundirla con una plantilla real de WhatsApp.

### 5.4 Plantilla WhatsApp

Es otro concepto:

- templateName del proveedor;
- contenido aprobado por Meta/iVentas;
- variables por destinatario.

Nunca debe reutilizarse la palabra plantilla para representar audience_family en modelos nuevos.

## 6. Semántica de selección

Dentro de una misma dimensión, los checks se combinan con OR.

Ejemplo:

    DOMICILIADO OR TRIMESTRAL

Entre dimensiones distintas se aplica AND.

Ejemplo:

    vencidos julio-agosto
    AND sucursal permitida
    AND (DOMICILIADO OR TRIMESTRAL)

Un destinatario que coincida con varias familias aparece una sola vez, pero conserva todas las etiquetas que explican su inclusión.

## 7. Segmentación no equivale a exclusión

Una familia comercial no debe excluir por sí sola.

Separar:

- segmentación/composición;
- bloqueos técnicos;
- reglas obligatorias de negocio.

Ejemplos de bloqueo técnico:

- sin teléfono;
- teléfono no utilizable para el canal;
- duplicado dentro de la campaña.

Toda exclusión obligatoria debe ser explícita y auditable.

## 8. Dónde viven los estados iVentas

Los flags de iVentas son **campaña-específicos**, no atributos globales del socio.

Ejemplo: el mismo teléfono puede quedar `VIEWED` en una campaña y `FAILED` en otra. Por eso no se deben agregar columnas `sent/delivered/viewed/failed` a `socios_vencidos_cartera`, a las filas canónicas de Socios Activos ni a la entidad global del contacto.

Los estados viven en la relación **campaña -> destinatario** (o en su detalle/provider-delivery equivalente):

    campaign recipient
      -> successful
      -> sent
      -> delivered
      -> viewed
      -> failed
      -> interactions

Así se reutilizan las bases existentes sin contaminarlas con estado de una campaña particular.

## 9. Audiencia congelada

Al confirmar una campaña, la audiencia debe quedar persistida como cohorte.

Si una campaña se creó con 3,842 destinatarios, esos 3,842 no cambian porque después cambie:

- el estado del socio;
- la tarifa;
- el snapshot Warehouse;
- el Funnel;
- la clasificación del catálogo.

El preview se puede recalcular mientras la campaña no se confirme. La campaña confirmada no.

## 10. Capa de proveedores

El núcleo de V2 debe depender de una interfaz conceptual CampaignProvider y capacidades declaradas.

Capacidades esperadas:

- create_campaign;
- get_campaign_stats;
- list_campaigns;
- get_recipient_events;
- get_campaign_cost;
- supports_recipient_reply;
- supports_recipient_timeline.

iVentas será un adaptador. Un proveedor futuro no debe obligar a reescribir audiencias o persistencia central.

## 11. Seguridad

Las credenciales de integración viven solo en backend/env/secrets.

Nunca:

- Angular;
- environment.ts del frontend;
- localStorage;
- Git;
- logs;
- respuestas de API hacia navegador.

Los documentos recibidos con credenciales no deben copiarse al repositorio.

La credencial usada durante integración debe poder rotarse sin cambio de código.

## 12. Convivencia con legacy

Ruta de transición:

1. legacy sigue operativo;
2. V2 Fase 1 disponible;
3. V2 Fase 2 disponible;
4. V2 Fase 3 disponible;
5. campañas reales validadas;
6. se bloquea creación nueva en legacy;
7. legacy queda solo lectura;
8. retiro futuro explícito.

No borrar ni migrar datos legacy durante estas tres fases salvo decisión separada.

## 13. Preguntas abiertas que no pueden resolverse por inferencia

- Tratamiento final de la familia mes.
- Endpoint iVentas para listar campañas históricas por periodo.
- Disponibilidad de respondidos por número.
- Timestamps sent/delivered/viewed/replied por destinatario.
- Shape real de analytics/costo en respuesta productiva.
- Política final de edición de campañas V2 después de congelar audiencia.
- Política final de atribución de Reactivaciones V2 al motor existente.

Si una conversación posterior necesita una de estas respuestas, debe pedir evidencia o inspeccionar el proveedor/repo. No inventar.

## 14. Regla de trabajo para nuevas conversaciones

Antes de modificar código:

1. leer este contrato global;
2. leer únicamente el contrato de la fase activa;
3. inspeccionar los archivos existentes mencionados;
4. comparar contra main actual porque el repo puede haber cambiado;
5. proponer un solo cambio mínimo;
6. ejecutar pruebas específicas;
7. continuar solo si el resultado coincide con el contrato.

Los contratos de fases posteriores sirven para preparar interfaces, no para adelantar implementación.
