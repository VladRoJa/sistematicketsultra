# Contrato Campañas V2 — Fase 2

Estado: CONTRATO DE LECTURA/BI; NO AUTORIZA ENVÍO  
Dependencia de ejecución: Fase 1 debe estar terminada y comprobada en el repositorio; este archivo es autosuficiente como contexto.  
Objetivo: consolidar la lectura/histórico de iVentas ya aceptada como 2A, mantener `FUNNEL_PORTFOLIO` ya aceptada como 2B, incorporar Historical Targeting como capacidad transversal obligatoria y añadir Campaign BI/Reporting/Excel como 2C antes de habilitar cualquier envío en Fase 3.

## 0. Contexto autosuficiente para una conversación nueva

Este archivo puede entregarse **por sí solo** a una conversación nueva. La conversación debe comprobar en el repositorio que Fase 1 está realmente implementada y estable antes de modificar Fase 2; no debe asumirlo por el texto.

Contexto fijo:

- Suite Ultra usa Angular + Flask + PostgreSQL y Alembic.
- Campañas V2 convive con Reactivaciones legacy.
- Fase 1 aporta el núcleo de campañas, preview y audiencia congelada.
- No se crean tablas espejo de Socios Activos ni Socios Vencidos.
- `socios_vencidos_cartera` y snapshots/resolvers canónicos de Socios Activos son fuentes existentes que se reutilizan.
- Campaign-recipient almacena la pertenencia al cohorte y hechos específicos de esa campaña; no reemplaza la base fuente.
- `sent`, `delivered`, `viewed`, `failed` e interacciones son hechos de una campaña concreta.
- A partir de esos hechos se debe poder derivar **comportamiento histórico por teléfono** para filtrar campañas nuevas sin contaminar las fuentes.
- `FUNNEL_PORTFOLIO` pertenece a 2B y está ACCEPTED. Su identidad mínima puede ser teléfono; `contact_id`, nombre, sucursal, canal y fecha son enriquecimientos cuando existan.
- Funnel debe reutilizar su lógica existente de compradores/no compradores y además aplicar supresión por teléfono contra el snapshot canónico vigente de Socios Activos.
- Esta fase cubre lectura/histórico iVentas, `FUNNEL_PORTFOLIO`, Campaign BI/Reporting y Excel. **No implementar POST /v2/broadcast.**

Modo de trabajo:

1. inspeccionar `main` y confirmar Fase 1;
2. revisar integración iVentas y Funnel existentes antes de crear código;
3. explicar un solo cambio mínimo y su prueba;
4. no modelar campos no observados en un payload real;
5. no avanzar a Fase 3.

### 0.1 Estado contractual de Fase 2

La estructura de Fase 2 queda congelada así:

    2A — iVentas / histórico / engagement      ACCEPTED
    2B — FUNNEL_PORTFOLIO                      ACCEPTED

    Historical Targeting transversal           ACCEPTED

    2C — Campaign BI / Reporting / Excel       PENDIENTE
    2D — Acceptance final                      PENDIENTE

2A corresponde a M8–M16 y está IMPLEMENTADA, ACCEPTED M16 y DEPLOYADA. Smoke real provider: PASS.

2B corresponde a M17–M20 y está ACCEPTED. `FUNNEL_PORTFOLIO` ya atraviesa cartera canónica, comprador/no comprador, `ACTIVE_MEMBER_SUPPRESSION`, scope backend, history exclusion M14, dedupe, Preview, Preview Detail, fingerprint, Freeze y Angular.

La captura automática M12 está implementada, pero permanece operativamente deshabilitada hasta definir explícitamente `cadence`, `horizon` y `max`.

Historical Targeting transversal corresponde a M21–M25 y está ACCEPTED. 2C y 2D permanecen PENDIENTES. Fase 3 sólo puede comenzar después de cerrar 2C y completar 2D con aceptación integral.

### 0.2 Enmienda M8 — evidencia real observada y frontera vigente

Esta enmienda consolida la evidencia real confirmada para el provider read-only de Campaign V2. Si una sección posterior entra en conflicto con esta enmienda, debe actualizarse para mantener una sola semántica contractual.

#### API oficial de campaign stats — CONFIRMADA

Frontera validada en servidor real:

    GET https://rest.iventas.mx/v2/broadcast/stats/{campaign_id}
    Authorization: Bearer IVENTAS_CAMPAIGNS_API_KEY

La credencial de campañas es independiente de `IVENTAS_API_TOKEN`.

Se confirmó HTTP 200 con las claves:

- `successfulMessages`;
- `failedMessages`;
- `sentMessages`;
- `sentdMessages`;
- `deliveredMessages`;
- `viewedMessages`;
- `answeredMessages`;
- `interactions`;
- `analytics`;
- `analyticsStatus`.

En la campaña validada se observaron 528 recipients:

    successful = 497
    failed = 31
    sent = 6
    delivered = 200
    viewed = 291

y se verificó:

    successful = sent ⊔ delivered ⊔ viewed
    failed ∩ successful = ∅

    sent ∩ delivered = ∅
    sent ∩ viewed = ∅
    delivered ∩ viewed = ∅

Por tanto `sentMessages`, `deliveredMessages` y `viewedMessages` se tratan como buckets recipient-level mutuamente excluyentes en el contrato M8.

#### Alias legacy observado

`sentdMessages` fue comprobado contra `sentMessages` en el mismo payload:

    len(sentMessages) = 6
    len(sentdMessages) = 6
    sets_equal = True

Regla M8:

- fuente canónica: `sentMessages`;
- `sentdMessages` = alias/typo legacy observado;
- puede tolerarse como fallback defensivo;
- nunca se suma con `sentMessages`;
- si ambos existen y difieren, el payload es incompatible con el contrato observado.

#### Analytics y recipients son niveles distintos

`analytics` es un objeto agregado y cruza la frontera como agregado/opaco. No debe usarse para fabricar estados individuales.

En el payload validado:

    analytics.funnel.delivered = 491
    analytics.funnel.read = 291

y:

    deliveredMessages + viewedMessages = 491
    viewedMessages = 291

Esto confirma que el funnel agregado puede ser acumulativo mientras los buckets recipient-level representan estados mutuamente excluyentes.

`analyticsStatus = not_synced` no invalida por sí solo los recipient buckets. `analytics` puede estar ausente o parcial mientras los arrays recipient-level sigan siendo válidos.

#### Responders e interacciones

`answeredMessages` no es fuente canónica recipient-level de responders. Se observó:

    answeredMessages = []
    analytics.responders = 79

Por tanto no se deriva `responded_phones` ni `NO_RESPONDIÓ` desde `answeredMessages`.

`interactions[].items` sí aporta teléfonos recipient-level asociados a botones. Puede contener duplicados y debe distinguir:

- conteo raw/provider;
- recipients únicos normalizados.

La capability M8 es:

    recipient_button_interactions = true
    recipient_response_attribution = false

`analytics.interactions.freeText` existe sólo como agregado; no hay recipients correspondientes demostrados.

#### Límites recipient-level

La API confirmada no aporta:

- timestamps individuales `sent_at/delivered_at/viewed_at/failed_at`;
- causa de fallo por teléfono;
- recipient-level attribution de free-text responders.

`analytics.failures.categories` es agregado. `failedMessages` contiene teléfonos, pero no existe evidencia que vincule cada teléfono con una causa Meta concreta.

#### GraphQL histórico

La investigación GraphQL histórica sigue siendo una capability separada y futura. No forma parte del provider M8.1–M8.4 implementado y no es necesaria para interpretar los buckets confirmados de `/v2/broadcast/stats/{campaign_id}`.

Regla de seguridad M8:

- provider estrictamente read-only;
- `GET /v2/broadcast/stats/{campaign_id}` permitido;
- GraphQL `query` read-only puede investigarse en un milestone separado;
- GraphQL `mutation` prohibida;
- `POST /v2/broadcast` prohibido.

## 1. Alcance exacto

Fase 2 conserva cuatro bloques numerados y añade una capacidad transversal obligatoria:

- **2A — iVentas / histórico / engagement:** ACCEPTED; corresponde a M8–M16 y conserva toda su semántica vigente.
- **2B — FUNNEL_PORTFOLIO:** ACCEPTED; corresponde a M17–M20 y reutiliza la cartera Funnel canónica, `ACTIVE_MEMBER_SUPPRESSION`, scope backend, history M14, dedupe, Preview/Detail, fingerprint, Freeze y Angular.
- **Historical Targeting transversal:** ACCEPTED; M21–M25 reutilizan el histórico persistido M11/M13 para incluir o excluir por comportamiento previo con semántica `INCLUDE/EXCLUDE` + `ALL/ANY`, Preview Detail neutral, fingerprint/Freeze y Angular, preservando compatibilidad legacy.
- **2C — Campaign BI / Reporting / Excel:** PENDIENTE; proyección read-only sobre evidencia persistida por Suite.
- **2D — Acceptance final:** PENDIENTE; valida integralmente 2A + 2B + Historical Targeting + 2C antes de autorizar Fase 3.

M8–M16 no se reinterpretan: `successful/failed`, `SENT/DELIVERED/VIEWED`, snapshots append-only, `fetched_at`, button interactions, history exclusions y M12 disabled por defecto mantienen su semántica existente.

Debe permitir:

- asociar una campaña V2 con un campaign_id de iVentas;
- importar campañas creadas directamente en iVentas cuando exista forma de descubrirlas;
- consultar stats y analytics agregados de una campaña mediante la frontera oficial confirmada;
- obtener buckets recipient-level `sent/delivered/viewed/failed` por teléfono para un `campaign_id` conocido;
- obtener interacciones de botón recipient-level desde `interactions[].items`;
- investigar histórico GraphQL por teléfono en un milestone separado cuando exista una necesidad distinta de campaign stats;
- persistir estados/interacciones sólo en un milestone posterior con modelo e idempotencia explícitos; M8 no crea persistencia;
- persistir analytics relevantes;
- persistir costo de campaña cuando el proveedor lo entregue y su shape real haya sido congelado;
- clasificar campañas históricas por propósito comercial;
- filtrar audiencias futuras por comportamiento previo soportado;
- realizar sincronizaciones idempotentes;
- crear una audiencia desde `FUNNEL_PORTFOLIO` aunque el único dato individual confiable sea el teléfono;
- congelar esa cartera sin fabricar socio, PIN, tarifa o sucursal.

Fase 2 NO debe:

- enviar campañas;
- llamar POST /v2/broadcast;
- guardar credenciales en frontend;
- inferir datos que la API no entregue;
- sustituir automáticamente métricas corporativas de Track;
- retirar el módulo legacy.

## 2. Investigación de repo que debe reutilizarse

Antes de implementar, revisar main actual y confirmar que siguen vigentes:

- backend/app/services/marketing_iventas_service.py
- backend/app/services/marketing_iventas_branch_service.py
- backend/app/services/marketing_iventas_leads_service.py
- backend/app/services/marketing_iventas_run_sync_service.py
- backend/app/services/marketing_iventas_structured_persistence_service.py
- backend/app/models/marketing.py
- backend/app/services/marketing_campaign_preview_detail_service.py
- backend/app/services/marketing_campaign_delivery_service.py
- backend/app/services/marketing_campaign_iventas_followup_service.py
- backend/app/services/marketing_sales_funnel_iventas_stage_service.py
- docs/contratos/contrato_marketing_iventas_leads_v1.md

Hallazgo de diseño: Suite ya tiene una integración iVentas de contactos, raw/structured, phone normalization, alias de sucursal y canonical runs. La integración de broadcast stats es nueva semánticamente, pero no debe duplicar utilidades ya resueltas.

## 3. Separación entre contactos iVentas y campañas iVentas

La integración existente GET /v1/integrations/contacts representa contactos CRM y snapshots de contactos.

La evidencia M8 confirma además dos superficies read-only distintas:

- Campaign Stats oficial: `GET /v2/broadcast/stats/{campaign_id}`, que entrega buckets recipient-level por teléfono y un objeto `analytics` agregado;
- GraphQL histórico: conversación/Client y mensajes por `Client.id`, investigado aparte y no implementado en M8.1–M8.4.

No mezclar campaign stats con contactos CRM ni con historial GraphQL. La API de campaign stats ya aporta campaña concreta + destinatarios + bucket individual, pero no aporta timestamps individuales, causa de fallo por teléfono ni atribución individual de free-text responders.

Ejemplo de error prohibido:
- asumir que MarketingIventasContactORM es la tabla natural para guardar cada estado de broadcast.

Un mismo contacto puede participar en varias campañas. Los estados deben pertenecer a la relación campaña-destinatario, no al contacto global.

Sí se debe reutilizar:
- normalize_iventas_phone();
- resolución de branch;
- patrones de seguridad;
- patrones de sync idempotente;
- manejo de timezone cuando aplique.

## 4. Regla de persistencia: reutilizar fuentes, guardar estado por campaña

Fase 2 no crea una copia completa de Socios Activos ni de Socios Vencidos.

- Socios Vencidos: reutilizar `socios_vencidos_cartera` y conservar referencia al episodio cuando aplique.
- Socios Activos: reutilizar snapshots canónicos y conservar referencia al snapshot/fila fuente cuando el modelo vigente lo permita.
- Funnel: reutilizar el detalle/identidad existente; si solo existe teléfono, conservar `PHONE_ONLY`.

La frontera confirmada ya permite atribuir `sent`, `delivered`, `viewed`, `failed` y button interactions a un `campaign_id` concreto por teléfono.

M8.1–M8.4 permanece estrictamente read-only y **no autoriza persistencia**. Cuando un milestone posterior la implemente, estos hechos deberán guardarse en el recipient/delivery de esa campaña, nunca como estado global del contacto.

Nunca agregar estos hechos a las bases canónicas. El mismo socio/teléfono puede tener resultados distintos en campañas distintas.

## 5. Cartera Funnel / Venta Nueva

### 5.1 Infraestructura existente

Revisar/reutilizar antes de crear código nuevo:
- `marketing_sales_funnel_detail_service.py`;
- `marketing_sales_funnel_iventas_stage_service.py`;
- `marketing_sales_funnel_drilldown_service.py`;
- `marketing_sales_funnel_service.py`;
- `marketing_phone.py`;
- integración Funnel -> Contact Center.

### 5.2 Contrato mínimo

Para `FUNNEL_PORTFOLIO` solo es obligatorio:

    phone_mx10
    source = FUNNEL_PORTFOLIO

Opcionales cuando existan:

    source_reference
    contact_id
    name
    sucursal_id
    channel
    source_date
    origin

No exigir member_id, PIN, tarifa, categoria_tarifa ni audience_family.

### 5.3 Identidad phone-only

El teléfono es clave operativa para deduplicar envíos, no identidad humana definitiva. Un recipient puede quedar `identity_quality = PHONE_ONLY`.

No inferir sucursal por lada ni fabricar datos faltantes.

### 5.4 Compradores y cartera utilizable

El Funnel ya contiene lógica de cruces contra ventas y una ventana de compra para leads. Antes de definir quién queda en cartera para campaña, localizar y reutilizar exactamente esa semántica.

No contactar a un comprador solo porque Campañas V2 consultó una fuente más cruda que el Funnel vigente. Si la definición de cartera deseada difiere, detenerse y crear contrato específico; no crear un segundo matcher silencioso.

### 5.5 Sucursal desconocida

Un contacto puede conservar `sucursal_id = NULL` en Fase 2. Esto no invalida su existencia en cartera.

Antes de Fase 3 deberá existir una regla explícita de dispatch/channel. Si no puede resolverse, el recipient se bloquea para envío; jamás se manda desde una sucursal arbitraria.

### 5.6 Supresión obligatoria contra Socios Activos

Una campaña de Venta Nueva construida desde `FUNNEL_PORTFOLIO` no debe enviar mensajes a números que ya correspondan a socios actualmente activos.

El cruce debe reutilizar:

    resolve_latest_canonical_socios_activos_snapshot()
    SociosActivosSnapshotRowORM.telefono_raw
    marketing_phone.normalize_phone()

No crear una tabla paralela de socios activos ni poblarla para Marketing.

Flujo conceptual:

    FUNNEL_PORTFOLIO
        -> normalizar phone_mx10
        -> cruzar contra snapshot canónico de Socios Activos
        -> teléfono presente en activos: ACTIVE_MEMBER_SUPPRESSION
        -> teléfono ausente: continuar evaluación

La supresión es **por número destinatario**, no una declaración fuerte de identidad humana. Esto es deliberado: si un teléfono está siendo utilizado por un socio activo, no se desea enviar a ese mismo número una campaña de adquisición aunque el lead CRM corresponda a otra fila/contact_id.

El Preview debe mostrar esta población por separado, por ejemplo:

    Candidatos Funnel
    Compradores excluidos por lógica Funnel
    Socios activos excluidos
    Teléfonos duplicados/conflictos
    Audiencia final

La razón `ACTIVE_MEMBER_SUPPRESSION` debe quedar congelada/auditada en el resultado del preview o creación cuando corresponda, pero **no** se escribe como flag permanente en el lead ni en Socios Activos.

Esta supresión complementa, no reemplaza, el cruce de compra de 60 días ya utilizado por el Funnel:

- cruce de compra: evita contactar a quien ya convirtió dentro de la lógica comercial del Funnel;
- Socios Activos: evita contactar como Venta Nueva a quien hoy ya pertenece a la base activa, incluso si el dato de compra no quedó representado del mismo modo en la cohorte del Funnel.

### 5.7 Pipeline contractual de 2B

El pipeline de `FUNNEL_PORTFOLIO` debe ser:

    Funnel vigente
      -> lógica comprador/no comprador existente
      -> normalización phone_mx10
      -> ACTIVE_MEMBER_SUPPRESSION
      -> scope backend
      -> history exclusions existentes
      -> dedupe
      -> Preview
      -> Freeze

El contrato mínimo del recipient continúa siendo:

    phone_mx10
    source = FUNNEL_PORTFOLIO

Los campos `contact_id`, `name`, `sucursal_id`, `channel`, `source_date`, `origin` y `source_reference` son opcionales y sólo se incluyen cuando existan realmente.

`identity_quality = PHONE_ONLY` es válido. Está prohibido inventar `member_id`, PIN, tarifa, familia o sucursal cuando no exista evidencia.

Preview/Detail debe auditar separadamente:

- candidatos Funnel;
- compradores excluidos;
- socios activos excluidos;
- teléfonos inválidos;
- duplicados/conflictos;
- history exclusions;
- audiencia final.

`ACTIVE_MEMBER_SUPPRESSION` significa únicamente "no enviar Venta Nueva a ese número"; no afirma que el lead y el socio sean necesariamente la misma persona.

## 6. Provider abstraction

M8 implementa una abstracción de proveedor read-only ya validada.

Interfaz vigente:

    CampaignProvider
        capabilities()
        get_campaign_stats(provider_campaign_id)

Implementación:

    IVentasCampaignProvider

Flujo M8:

    provider_campaign_id
      -> IVentasCampaignsClient.get_campaign_stats()
      -> parse_iventas_campaign_stats()
      -> CampaignProviderStats

Capabilities vigentes para iVentas M8:

    campaign_stats = true
    campaign_aggregate_analytics = true
    recipient_status_buckets = true
    recipient_button_interactions = true
    recipient_response_attribution = false
    recipient_event_timestamps = false
    recipient_failure_causes = false
    list_campaigns = false
    send = false

El provider no vuelve a normalizar teléfonos, validar buckets, interpretar `sentdMessages`, deduplicar ni recalcular analytics. Es un mapping mecánico desde el parser aprobado hacia tipos internos provider-agnostic.

El resto del módulo no debe conocer URL, credencial ni nombres externos de iVentas fuera del cliente/adaptador.

## 7. Capacidades conocidas de iVentas

### 7.1 Campaign stats oficial — CONFIRMADO

Frontera implementada por M8:

    GET https://rest.iventas.mx/v2/broadcast/stats/{campaign_id}

Autenticación:

    Authorization: Bearer IVENTAS_CAMPAIGNS_API_KEY

`IVENTAS_CAMPAIGNS_API_KEY` es una credencial separada de `IVENTAS_API_TOKEN`. El cliente no hace fallback entre ambas.

Shape recipient-level confirmado:

- `successfulMessages: list[str phone]`;
- `failedMessages: list[str phone]`;
- `sentMessages: list[str phone]`;
- `sentdMessages: list[str phone]` como alias legacy observado;
- `deliveredMessages: list[str phone]`;
- `viewedMessages: list[str phone]`;
- `answeredMessages: list`;
- `interactions: [{label, items: list[str phone]}]`.

Shape agregado confirmado:

- `analytics: object`;
- `analyticsStatus`, con `ok` y `not_synced` ya contemplados por M8.

El parser conserva dos niveles:

    raw/provider
      -> conteos y estructura recibidos

    normalized/internal
      -> teléfonos normalizados con normalize_iventas_phone()

No se validan métricas agregadas de iVentas contra cardinalidades post-normalización, porque varios formatos provider podrían colapsar al mismo teléfono. Las invariantes recipient-level sí se validan después de normalizar para impedir que un mismo teléfono termine silenciosamente en buckets incompatibles.

### 7.2 Semántica de buckets — CONFIRMADA

En la campaña real validada:

    successful = sent ⊔ delivered ⊔ viewed
    failed ∩ successful = ∅

    sent ∩ delivered = ∅
    sent ∩ viewed = ∅
    delivered ∩ viewed = ∅

El parser M8 trata estas relaciones como invariantes del contrato observado. Si un payload futuro las viola después de normalización, falla explícitamente; no inventa precedencia ni corrige buckets silenciosamente.

`sentdMessages` se tolera sólo como compatibilidad defensiva. `sentMessages` es la fuente canónica.

### 7.3 Analytics agregado — CONFIRMADO

`analytics` cruza la frontera del provider como objeto agregado/opaco.

Se observaron, entre otros:

- `funnel`;
- `responders`;
- `interactions.campaignButton`;
- `interactions.freeText`;
- `failures.categories`;
- `cost`/información de costo poblada en el payload real.

M8 no recalcula ni convierte esos agregados a hechos recipient-level.

### 7.4 GraphQL histórico — SEPARADO DE M8

Se observaron previamente operaciones GraphQL read-only para resolver `Client.id` e historial de mensajes por teléfono. Esa superficie no forma parte del provider M8.1–M8.4 y no se necesita para interpretar los buckets confirmados de campaign stats.

Puede retomarse en un milestone posterior si hace falta una capability distinta de historial por teléfono.

## 8. Estado recipient-level por campaña

Para un `campaign_id` conocido, `/v2/broadcast/stats/{campaign_id}` ya entrega pertenencia recipient-level a:

    sent
    delivered
    viewed
    failed

La relación es directa entre campaña consultada y teléfono devuelto por el provider. No requiere correlación GraphQL con un outbound individual para conocer el bucket actual observado de esa campaña.

M8 no persiste estos hechos; sólo los expone read-only mediante `CampaignProviderStats`.

## 9. Interacciones

La API confirmada expone dos niveles distintos:

Recipient-level:

    interactions[].label
    interactions[].items -> list[str phone]

Estos items corresponden a interacciones de botón observadas. Pueden contener duplicados, por lo que el parser conserva:

- `raw_item_count`;
- recipients únicos normalizados.

Capability M8:

    recipient_button_interactions = true

Agregado:

    analytics.interactions.campaignButton
    analytics.interactions.freeText

`freeText` sólo está demostrado como agregado. No existe una lista recipient-level asociada, por lo que:

    recipient_response_attribution = false

No convertir button interaction en sustituto de `VIEWED` ni inferir free-text responders individuales.

## 10. Respondidos

`answeredMessages` existe en el payload real, pero no es fuente canónica recipient-level de responders.

Evidencia observada:

    answeredMessages = []
    analytics.responders = 79

Por tanto:

- se permite conservar el conteo raw de `answeredMessages`;
- no existe `responded_phones` en M8;
- no implementar `NO_RESPONDIÓ` por destinatario;
- `analytics.responders` y `analytics.interactions.freeText` permanecen agregados/opacos.

La investigación GraphQL de `quotedMsgId -> messageApiId` sigue siendo evidencia histórica separada y no forma parte del provider M8.

## 11. Timestamps individuales y causas de fallo

La API oficial de campaign stats no aporta timestamps recipient-level para:

- `sent_at`;
- `delivered_at`;
- `viewed_at`;
- `failed_at`;
- `replied_at`.

Tampoco aporta causa de fallo por teléfono. `analytics.failures.categories` es agregado y `failedMessages` contiene sólo teléfonos.

Por tanto M8 mantiene:

    recipient_event_timestamps = false
    recipient_failure_causes = false

No reinterpretar hora de sync, hora de campaña, campos GraphQL históricos ni agregados analytics como timestamps/cause recipient-level.

Metadata propia de Suite como `last_synced_at` puede existir en un milestone posterior si se nombra claramente y no se confunde con un evento WhatsApp.

## 12. campaign_id externo — M9 implementado

Campaign V2 conserva identidad interna propia y puede quedar vinculada opcionalmente a una identidad externa provider mediante:

    marketing_campaign_v2_campaigns.provider
    marketing_campaign_v2_campaigns.provider_campaign_id

Reglas M9:

- ambos campos son nullable sólo como conjunto;
- no se permite binding parcial;
- `provider` se normaliza a uppercase en backend;
- `provider_campaign_id` conserva el ID externo como texto;
- el CHECK de DB exige provider canónico uppercase/trimmed e ID externo sin espacios de borde;
- existe `UNIQUE(provider, provider_campaign_id)`;
- el mismo ID externo puede existir en providers distintos;
- la PK interna de Suite sigue siendo `campaign_v2.id`.

Idempotencia:

- repetir el mismo binding sobre la misma Campaign V2 es no-op exitoso;
- intentar cambiar una Campaign V2 ya vinculada a otro par produce conflicto;
- reutilizar el mismo par `(provider, provider_campaign_id)` en otra Campaign V2 produce conflicto;
- el bind bloquea la fila de campaña durante la decisión para evitar rebinding concurrente silencioso.

API interna/backend:

    PUT /campaigns-v2/{campaign_id}/provider-binding

con payload:

    {
      "provider": "IVENTAS",
      "provider_campaign_id": "<external id>"
    }

List/detail exponen ambos campos. M9 no consulta stats automáticamente ni persiste analytics/delivery.

### M10 — provider stats read-through

M10 conecta el binding persistido con la abstracción provider existente mediante:

    GET /api/marketing/campaigns-v2/{campaign_id}/provider-stats

El request no acepta `provider` ni `provider_campaign_id`. Ambos salen exclusivamente de la Campaign V2 visible para el usuario.

Flujo:

    Campaign V2 accesible por scope
      -> provider/provider_campaign_id persistidos
      -> resolve_campaign_provider(provider)
      -> CampaignProvider.get_campaign_stats(provider_campaign_id)
      -> serialización provider-agnostic

La respuesta separa:

- `raw_counts`;
- recipients por outcome/bucket;
- `button_interactions`;
- `analytics_status`;
- `analytics` agregado/opaco.

Las colecciones normalizadas se serializan ordenadas para una respuesta determinística.

M10 es estrictamente read-through:

- no INSERT;
- no UPDATE;
- no DELETE;
- no commit;
- no snapshot;
- no `last_synced_at`;
- no persistencia de `analytics_status`.

`analyticsStatus=not_synced` sigue siendo respuesta válida `200` cuando el provider respondió correctamente.

### M11 — snapshots persistentes append-only

M11 agrega evidencia histórica persistente sin alterar el GET read-through de M10.

Modelo:

    marketing_campaign_v2_provider_stats_snapshots
      -> marketing_campaign_v2_provider_recipient_observations

Cada snapshot copia:
- `campaign_v2_id`;
- `provider`;
- `provider_campaign_id`;
- `analytics_status`;
- `fetched_at` propio de Suite;
- raw counts;
- `analytics_json` agregado/opaco;
- `button_interactions_json`;
- métricas diagnósticas;
- fingerprint SHA-256;
- `created_at`.

Las observations conservan:
- `normalized_phone` según la clave normalizada M8;
- `campaign_recipient_id` nullable;
- outcome `SUCCESSFUL/FAILED`;
- delivery bucket `SENT/DELIVERED/VIEWED` sólo para successful;
- button labels observadas.

Matching con frozen recipients:
- sólo `mx10:<10 dígitos>` se vincula contra `MarketingCampaignV2RecipientORM.phone_mx10`;
- teléfonos provider sin frozen recipient se conservan con FK null;
- frozen recipients ausentes del provider no reciben estado inventado.

Diagnósticos por snapshot:
- provider recipients normalizados únicos;
- matched recipients;
- unmatched provider phones;
- frozen recipients sin status provider.

Idempotencia:
- fingerprint determinístico sobre `CampaignProviderStats` normalizado;
- sets ordenados;
- interactions ordenadas establemente;
- analytics JSON canonicalizado;
- no incluye fetched_at ni DB ids;
- `UNIQUE(campaign_v2_id, provider, provider_campaign_id, fingerprint)`;
- captura idéntica devuelve el snapshot existente sin duplicar observations;
- cambio real crea nuevo snapshot append-only.

API:

    POST /api/marketing/campaigns-v2/{id}/provider-stats/snapshots
    GET  /api/marketing/campaigns-v2/{id}/provider-stats/snapshots
    GET  /api/marketing/campaigns-v2/{id}/provider-stats/snapshots/latest

La creación de snapshot + observations es una sola transacción. M11 no persiste timestamps recipient-level ni failure causes.

### M12 — captura automática de provider stats

M12 reutiliza el proceso separado ya existente:

    marketing-scheduler
      -> selección Campaign V2
      -> capture_campaign_v2_provider_stats_snapshot()
      -> M11

No corre en Gunicorn, no crea background threads Flask y no hace requests HTTP internos contra Suite.

Configuración:

    CAMPAIGN_V2_PROVIDER_STATS_AUTO_CAPTURE_ENABLED
    CAMPAIGN_V2_PROVIDER_STATS_INTERVAL_SECONDS
    CAMPAIGN_V2_PROVIDER_STATS_HORIZON_HOURS
    CAMPAIGN_V2_PROVIDER_STATS_MAX_CAMPAIGNS_PER_CYCLE

Reglas de configuración:
- auto-capture está disabled por defecto;
- si se habilita, interval/horizon/max son obligatorios y deben ser enteros positivos;
- no existen defaults ocultos de producto para cadence, horizon o batch size.

Elegibilidad:
- sólo Campaign V2 con provider binding completo;
- campaign sin snapshots puede recibir captura inicial;
- después de la primera captura, la ventana automática se mide desde el primer `fetched_at` M11;
- si `first_fetched_at < now - horizon`, deja de consultarse automáticamente;
- no se inspecciona `analytics_json` para scheduling.

Orden de selección:
1. campañas sin snapshot;
2. campañas elegibles por `latest_fetched_at` más antiguo;
3. `campaign_id`.

El límite se aplica después de ese orden para evitar starvation.

Resumen de ciclo:

    selected
    attempted
    created
    unchanged
    failed
    skipped

`skipped` incluye campañas bound fuera de horizon y elegibles omitidas por max-per-cycle. Campañas sin binding no entran a selección.

Aislamiento:
- cada campaña llama directamente M11;
- M11 decide created/unchanged mediante fingerprint;
- un fallo de una campaña no aborta las siguientes;
- logs sólo incluyen campaign_id, conteos y clase/categoría de error sanitizada;
- no se loggean teléfonos, payloads, analytics, headers ni secretos.

Sesiones:
- cleanup por campaña cuando usa `db.session`;
- rollback aislado en fallo;
- `db.session.remove()` al finalizar el ciclo M12;
- el loop general de marketing-scheduler conserva además su cleanup final.

Concurrencia:
- no se agrega advisory lock;
- dos workers pueden efectuar HTTP redundante accidentalmente;
- M11 evita snapshots idénticos duplicados mediante fingerprint + UNIQUE;
- respuestas realmente distintas pueden producir snapshots distintos, como evidencia válida.

M12 no crea tablas ni migraciones.

### M13 — histórico recipient-level transversal por teléfono

M13 construye una consulta histórica provider-agnostic usando exclusivamente evidencia persistida M11:

    marketing_campaign_v2_provider_stats_snapshots
      -> marketing_campaign_v2_provider_recipient_observations
      -> marketing_campaign_v2_campaigns

No consulta iVentas, GraphQL, M10 read-through ni dispara capturas.

Semántica temporal:

    observed_at = snapshot.fetched_at

significa cuándo Suite observó el estado. No representa sent_at/delivered_at/viewed_at reales del provider.

El servicio bulk:

    get_provider_history_for_phones(...)

normaliza inputs reutilizando `normalize_iventas_phone()` y resuelve MX10 a la representación interna:

    mx10:<10 dígitos>

Máximo por request:

    100 teléfonos

alineado con el límite ya usado por Campaign V2 para page_size.

La consulta es bulk y evita N+1:
- una query observations -> snapshots -> campaigns;
- filtro por `normalized_phone IN (...)`;
- cutoff opcional `fetched_at <= observed_before`;
- scope Campaign V2 aplicado con la semántica existente.

Perspectivas:

1. `latest_by_campaign`
   - una observación por `campaign_v2_id + normalized_phone`;
   - desempate determinístico `fetched_at DESC, snapshot_id DESC`;
   - conserva outcome, exact delivery bucket, button labels, provider identity y observed_at.

2. `ever_observed`
   - outcomes observados;
   - delivery buckets exactos observados;
   - button labels observadas;
   - `button_interacted`;
   - first/last observed_at;
   - campaign_count.

M13 no fabrica jerarquía:

    VIEWED != SENT + DELIVERED

ni crea:

    responded
    no_answer
    unanswered

La ausencia de button interaction no se reinterpreta como ausencia de respuesta.

API read-only:

    POST /api/marketing/campaigns-v2/provider-history/lookup

Payload:

    {
      "phones": ["686...", "664..."],
      "observed_before": "optional ISO datetime with timezone"
    }

Aunque usa POST como transporte, la operación hace:
- cero INSERT;
- cero UPDATE;
- cero DELETE;
- cero commit;
- `session.no_autoflush`.

Scope/permisos:
- reutiliza autorización Campaign V2;
- campañas fuera del scope backend no aparecen;
- un teléfono conocido no permite descubrir actividad de campañas no visibles.

Performance/índices:
- M11 ya tiene índice por observation.normalized_phone;
- snapshot_id une por PK;
- snapshots ya tienen índice por campaign_v2_id + fetched_at;
- M13 no requiere migración ni materialización adicional.

M13 funciona indistintamente con snapshots manuales M11 y automáticos M12.

### M14 — filtros históricos provider en Audience Builder

M14 integra M13 dentro del builder server-side sin provider HTTP:

    source audience
      -> scope/status/clasificación
      -> teléfono MX10
      -> history M13 bulk
      -> history exclusion
      -> dedupe
      -> Preview / Detail / Freeze

Contrato de filtro:

    {
      "history_exclusion": {
        "delivery_buckets": ["SENT", "DELIVERED", "VIEWED"],
        "outcomes": ["SUCCESSFUL", "FAILED"],
        "button_interacted": true,
        "lookback_days": null
      }
    }

Todos los campos son opcionales. Un objeto sin condiciones efectivas equivale a no usar filtro histórico. lookback_days no tiene default y requiere al menos una condición.

Semántica de exclusión:
- OR entre todas las condiciones seleccionadas;
- un teléfono se excluye una sola vez aunque cumpla varias reglas;
- reason counts son no exclusivos y pueden sumar más que history_excluded_count;
- VIEWED/DELIVERED/SENT son buckets exactos observados, sin jerarquía implícita;
- no existen responded/no_answer/unanswered.

Razones canónicas de Preview Detail:
- HISTORY_DELIVERY_SENT;
- HISTORY_DELIVERY_DELIVERED;
- HISTORY_DELIVERY_VIEWED;
- HISTORY_OUTCOME_SUCCESSFUL;
- HISTORY_OUTCOME_FAILED;
- HISTORY_BUTTON_INTERACTION.

Preview diagnostics, sólo cuando el filtro está activo:
- before_history_filter_count;
- history_excluded_count;
- after_history_filter_count;
- excluded_by_delivery_bucket;
- excluded_by_outcome;
- excluded_by_button_interaction.

Los tres primeros cuentan teléfonos MX10 únicos antes/después de aplicar history, no filas fuente.

Cutoff/reproducibilidad:
- Angular no envía observed_before ni resultados históricos;
- el backend consulta M13 sobre los teléfonos candidatos visibles;
- observed_before efectivo es el máximo last_observed_at persistido relevante para esos teléfonos;
- sin historia, el cutoff efectivo es null;
- con lookback_days=N, observed_after = observed_before - N días;
- la ventana es inclusiva: observed_after <= fetched_at <= observed_before;
- Preview calcula su cutoff autoritativamente;
- Preview Detail reconstruye y recalcula autoritativamente en su request;
- Freeze reconstruye de nuevo;
- history_evaluation.observed_before/observed_after se guarda en source_metadata;
- filters + source_metadata ya forman parte del fingerprint existente;
- si nuevos snapshots relevantes cambian el cutoff o audiencia entre Preview y Freeze, Freeze produce preview mismatch y exige regenerar Preview.

Persistencia:
- audience_definition_json.filters.history_exclusion conserva la regla aplicada;
- audience_definition_json.source_metadata.history_evaluation conserva los límites efectivos;
- no se copian snapshots/history dentro de Campaign V2;
- no se requiere migración.

Preview Detail soporta:

    bucket = HISTORY_EXCLUDED

y devuelve un teléfono representativo con history_exclusion_reasons.

Performance:
- M13 mantiene máximo 100 sólo como default de la frontera pública;
- Audience Builder llama el mismo core con max_phones=None;
- sin lookback se hace una llamada bulk M13;
- con lookback se hace una consulta bulk anchor + una consulta bulk de ventana;
- nunca hay N+1 por recipient.

Compatibilidad:
- sin history_exclusion, Audience Builder no llama M13;
- filtros/source_metadata/fingerprint/recipient set previos permanecen sin cambios;
- campañas existentes siguen siendo legibles.

## 13. Campañas creadas fuera de Suite

Fase 2 debe soportar el concepto:

    origin = EXTERNAL_PROVIDER

Las campañas que clubes crearon desde el panel iVentas deben poder existir en V2 sin haber pasado por Fase 3.

Datos mínimos deseables al importar:
- provider_campaign_id;
- nombre;
- sucursal/provider branch;
- fecha;
- costo si disponible;
- stats;
- purpose = UNCLASSIFIED inicialmente si no es evidente.

## 14. Descubrimiento histórico por periodo

M8 no tiene todavía un endpoint de listado de campañas por periodo confirmado.

La frontera confirmada `GET /v2/broadcast/stats/{campaign_id}` requiere conocer previamente el `campaign_id`; GraphQL histórico tampoco constituye un listado de campañas.

Por tanto se mantienen dos caminos conceptuales:

### Camino A — listado provider confirmado

Solo si se observa/documenta una operación read-only de listado:
1. listar campañas del periodo;
2. registrar metadata;
3. consultar analytics agregados;
4. ejecutar las capacidades adicionales que estén realmente soportadas.

### Camino B — IDs provistos externamente

Mientras no exista listado confirmado, permitir más adelante un mecanismo administrativo controlado para registrar/importar IDs conocidos, sin enviar campañas.

No inventar scraping del panel ni consultar MongoDB de iVentas.

## 15. Retroactividad

La evidencia actual permite consultar retroactivamente stats de campañas cuando ya se conoce el `campaign_id` mediante la API oficial read-only.

El historial GraphQL por `Client.id` sigue siendo una capability separada y no sustituye un listado de campañas.

Un backfill futuro sólo queda autorizado para IDs/capabilities read-only realmente disponibles. No inventar campañas, timestamps recipient-level ni causas de fallo por teléfono.

## 16. Costos por campaña

El payload real de campaign stats contiene información de costo poblada dentro de `analytics`.

M8 conserva `analytics` como agregado/opaco y **no normaliza todavía** el costo a un DTO interno específico. Esto permite mantener evidencia real sin inventar semántica de campos no utilizada aún.

Antes de persistir o calcular con costo:
1. congelar el shape exacto que vaya a consumirse;
2. documentar moneda/unidades/campos usados;
3. agregar tests específicos;
4. mantener unknown/unavailable si esos campos no existen.

Prohibido inventar rutas internas o repartir costos artificialmente.

## 17. Conciliación de costos

La API anterior de costos por sucursal sigue existiendo y complementa la nueva.

Fase 2 debe distinguir:

- costo por campaña: atribución comercial;
- costo por sucursal/periodo: conciliación financiera.

No exigir que la suma de campañas sea igual al 100% del costo de sucursal si existen:
- mensajes operativos;
- utility/service;
- campañas no importadas;
- costos no atribuibles;
- periodos en curso.

La diferencia debe poder mostrarse como no atribuida, nunca repartirse artificialmente.

## 18. Clasificación comercial histórica

Propósitos:
- NEW_SALE
- REACTIVATION
- ACTIVE_MEMBERS
- UNCLASSIFIED

Campañas históricas deben llegar inicialmente:
- auto-clasificadas solo cuando el nombre sea inequívoco;
- UNCLASSIFIED en caso de duda.

Ejemplos de patrones permitidos como sugerencia:
- "venta nueva ..." -> NEW_SALE
- "reactivacion ..." -> REACTIVATION
- "socios activos ..." -> ACTIVE_MEMBERS

Pero la implementación debe ser:
- backend;
- configurable/mantenible;
- auditable;
- con override manual.
No codificar reglas en Angular.

## 19. Drill-down de clasificación

En el listado de campañas importadas debe poder abrirse un control y seleccionar:

    Venta nueva
    Reactivación
    Socios activos
    Sin clasificar

Persistir:
- purpose;
- classification_source = AUTO | MANUAL;
- classified_by;
- classified_at.

Una clasificación manual prevalece sobre la automática y no debe reescribirse en siguientes sync.

## 20. Estados iVentas como filtro de futuras audiencias

La API confirmada ya permite conocer por teléfono, para un `campaign_id` conocido, los buckets:

    SENT
    DELIVERED
    VIEWED
    FAILED

y button interactions recipient-level.

M8 sólo expone estos hechos read-only. Antes de usarlos como filtros persistentes de futuras audiencias debe existir un milestone separado de persistencia/idempotencia ligado a campaign-recipient.

No ofrecer `NO_RESPONDIDO` ni filtros de free-text response hasta tener atribución recipient-level confiable.

## 21. Persistencia conceptual

M9 crea únicamente la persistencia mínima de identidad provider directamente sobre `marketing_campaign_v2_campaigns`.

### Provider campaign binding — implementado
- campaign_v2_id = PK interna existente;
- provider nullable;
- provider_campaign_id nullable;
- check de completitud del par;
- unique constraint por `(provider, provider_campaign_id)`.

Todavía no se persisten:
- external origin;
- last_synced_at;
- analytics_status;
- stats snapshots.

### Recipient delivery state
- campaign/provider campaign;
- phone canonical;
- outcome successful/failed;
- delivery bucket sent/delivered/viewed cuando aplique;
- last_synced_at como metadata Suite, no timestamp WhatsApp.

No guardar `provider error/cause` por recipient porque campaign stats no aporta esa relación.

### Button interactions
- recipient;
- label;
- provider metadata;
- idempotencia definida explícitamente.

### Analytics snapshot o campos normalizados
- solo campos realmente utilizados;
- agregado separado de recipient state;
- costo/moneda sólo cuando su shape de consumo quede congelado.

No crear una mega-columna JSON como sustituto de todo si después se necesitan filtros frecuentes. Tampoco normalizar campos no usados por anticipado.

## 22. Idempotencia

Repetir sync de una campaña no debe duplicar nada.

El patrón futuro para campaign stats será:

    campaign_id
      -> fetch read-only
      -> parse/normalize
      -> upsert campaign binding + recipient buckets + button interactions + analytics
         sólo cuando un milestone de persistencia lo autorice

No deducir monotonicidad temporal a partir de los nombres `sent/delivered/viewed`. M8 sólo confirmó buckets disjuntos en el snapshot consultado, no una regla histórica de transición.

No borrar ni degradar estado persistido en el futuro sin una política de sync explícita y probada.

## 23. Rate limits y retries

`IVentasCampaignsClient` usa una política read-only explícita:

- máximo 3 requests totales;
- `401/403`: sin retry;
- `429` y `500/502/503/504`: retry controlado;
- transporte/timeout: retry controlado;
- fallback de espera: 2s, 5s;
- `Retry-After` soporta delta-seconds y HTTP-date;
- nunca reintentar antes del tiempo indicado por un `Retry-After` válido;
- si el tiempo indicado excede el máximo síncrono permitido, no truncarlo: devolver error retryable con `retry_after_seconds`;
- nunca convertir 5xx/429/transporte en payload vacío o conteos cero.

Los tests inyectan `sleep`; no duermen realmente.

No meter backfills largos dentro del backend web. Si más adelante existen sync masivos, evaluar job separado/scheduler.

## 24. Seguridad

Toda credencial iVentas:
- backend only;
- env/secret;
- nunca persistida en DB;
- nunca enviada a Angular;
- nunca registrada completa.

Campaign stats usa exclusivamente:

    IVENTAS_CAMPAIGNS_API_KEY

y opcionalmente:

    IVENTAS_CAMPAIGNS_API_BASE_URL

No existe fallback a `IVENTAS_API_TOKEN`.

El cliente es GET-only, no expone `send`, no ejecuta `POST /v2/broadcast` y sanitiza errores para no incluir token ni body raw.

GraphQL, si se retoma, queda en un milestone separado y sólo para queries read-only; mutations siguen prohibidas.

## 25. Sucursal y branch

Reutilizar:

    marketing_iventas_branch_service.py
    iventas_family
    Track aliases

No crear mapping hardcodeado de branch code a sucursal.

Para campañas externas, si el provider devuelve branch/channel, resolver a sucursal Suite mediante la infraestructura existente.

Si no puede resolverse:
- conservar campaña externa;
- marcar branch unresolved;
- no asignarla arbitrariamente.

## 26. Relación con Funnel

Venta nueva puede usar costos de campañas clasificadas NEW_SALE.

No mezclar:
- ventas/reactivaciones;
- leads;
- socios activos.

Fase 2 entrega datos de campaña para que Funnel los consuma posteriormente mediante interfaces explícitas.

No modificar el KPI del Funnel en el mismo cambio que implementa el sync si no existe un contrato separado de cálculo.

## 27. Relación con Reactivaciones

Una campaña clasificada REACTIVATION puede cruzarse con el motor de outcomes existente.

Primero investigar adaptación; no duplicar:
- last-touch;
- ventana;
- resolución de socios activos;
- outcomes terminales.

La conexión del nuevo campaign model al motor legacy puede requerir una interfaz común. Debe ser un cambio separado y probado.

## 28. API interna esperada

Ya existe en M8:

- `CampaignProvider.capabilities()`;
- `CampaignProvider.get_campaign_stats(provider_campaign_id)`;
- `IVentasCampaignProvider`;
- `CampaignProviderStats` con raw counts, outcome/buckets normalizados, button interactions y analytics agregado/opaco.

Ya existe en M9:

- attach/persist provider campaign id;
- consultar provider/provider_campaign_id en list/detail.

Ya existe en M10:

- resolver provider desde `campaign.provider`;
- consultar stats read-through usando exclusivamente `campaign.provider_campaign_id`;
- endpoint interno provider-agnostic `GET /campaigns-v2/{id}/provider-stats`;
- serialización determinística de `CampaignProviderStats`;
- manejo sanitizado de errores upstream sin persistencia.

Ya existe en M11:

- snapshots append-only de provider stats;
- observations recipient-level por snapshot;
- fingerprint SHA-256 determinístico e idempotencia DB;
- matching opcional provider phone -> frozen recipient;
- conservación de provider phones unmatched;
- diagnostics matched/unmatched/frozen-without-status;
- history/latest sin volver a consultar provider.

Ya existe en M12:

- captura automática dentro del proceso separado `marketing-scheduler`;
- auto-capture disabled por defecto;
- cadence/horizon/max obligatorios cuando se habilita;
- selección bound, determinística y acotada;
- ventana anclada en primer `fetched_at` M11;
- reutilización directa del snapshot service M11;
- aislamiento por campaña y cleanup de `db.session`.

Ya existe en M13:

- histórico transversal recipient-level por teléfono sobre snapshots M11;
- lookup bulk provider-agnostic sin llamadas a iVentas;
- `latest_by_campaign` determinístico;
- `ever_observed` con outcomes/buckets/button labels exactos;
- cutoff `observed_before` basado en `snapshot.fetched_at`;
- scope Campaign V2 backend-authoritative;
- endpoint read-only `POST /campaigns-v2/provider-history/lookup`;
- máximo de 100 teléfonos por request;
- una query bulk, sin N+1 y sin migración adicional.

Ya existe en M14:

- history exclusions server-side integradas al Audience Builder;
- exclusión OR por delivery bucket, outcome y button interaction;
- lookback opcional con ventana observada inclusiva;
- cutoff backend-authoritative;
- Preview diagnostics + bucket `HISTORY_EXCLUDED`;
- regla + cutoff efectivo dentro de `audience_definition_json`;
- Preview/Freeze protegidos por fingerprint existente;
- core M13 reutilizado en bulk, sin provider HTTP ni N+1;
- compatibilidad exacta cuando no se usa history filter.

Ya existe en M15:

- UI Angular dentro del Audience Builder existente;
- `SENT`, `DELIVERED` y `VIEWED` se presentan como opciones independientes;
- outcomes `SUCCESSFUL` / `FAILED` se presentan como dimensión separada;
- button interaction usa exclusivamente `button_interacted=true`;
- `history_exclusion` se omite si no existe condición efectiva;
- `lookback_days` sólo admite null o entero positivo;
- Angular nunca envía `observed_before`, `observed_after`, teléfonos excluidos ni resultados históricos;
- cualquier cambio de criterio histórico invalida Preview/fingerprint;
- Preview muestra diagnostics M14 sin sumar reason counts como total exclusivo;
- Preview Detail integra `HISTORY_EXCLUDED` con mapper TypeScript de razones canónicas y fallback seguro;
- detalle de Campaign V2 muestra criterios persistidos desde `audience_definition_json`;
- frontend no llama `/provider-history/lookup`, iVentas ni maneja Authorization manual.

Capacidades futuras, separadas:

- update commercial purpose;
- list imported/external campaigns;
- sync period cuando exista capability de listado confirmada;
- persist/read campaign-recipient delivery;
- historial GraphQL por teléfono si sigue siendo necesario para otro caso de uso.

Los nombres futuros se acuerdan al implementar cada milestone.

## 29. Pruebas mínimas

M8.1–M8.4 debe mantener verde, como mínimo:

Parser:
- fixture sanitizado compartido: `backend/tests/fixtures/iventas_campaign_stats_observed_sanitized.json`;
- payload basado en shape real sin teléfonos reales;
- `analyticsStatus=ok` y `not_synced`;
- analytics ausente/parcial con buckets válidos;
- raw/provider counts separados de normalized unique phones;
- invariantes post-normalización;
- `sentMessages` canónico;
- `sentdMessages` alias/fallback y conflicto explícito;
- button interactions con raw count + recipients únicos;
- `answeredMessages` sin derivar responders;
- sin timestamps/cause recipient-level inventados.

HTTP client:
- `IVENTAS_CAMPAIGNS_API_KEY` exclusiva;
- base URL opcional;
- GET + escaping seguro de campaign_id;
- timeout explícito;
- 401/403 sin retry;
- 429 con Retry-After delta-seconds y HTTP-date;
- 5xx/transporte con retries controlados;
- máximo 3 requests;
- JSON inválido/root no-object controlado;
- token/body raw ausentes de excepciones;
- ningún POST/send.

Provider:
- capabilities exactas;
- composición client -> parser -> mapping;
- raw counts y sets normalizados preservados;
- `button_interactions`;
- analytics agregado/opaco;
- `recipient_response_attribution=false`;
- errores client/parser propagados en M8.

Seguridad:
- ninguna mutation;
- ningún envío;
- ningún secreto expuesto.

M10 read-through:
- resolver IVENTAS y rechazar provider desconocido;
- respetar scope/permisos Campaign V2;
- campaign sin binding no llama al provider;
- external ID sale sólo de DB, nunca del request;
- stats normalizados se preservan;
- `not_synced` y analytics `None` son válidos;
- upstream retryable/no-retryable se sanitiza;
- parser/invariant errors no se silencian;
- sólo SELECT, sin commit ni escrituras.

M11 snapshots:
- captura inicial atómica;
- repetición exacta idempotente;
- cambio de analytics o buckets crea snapshot nuevo;
- matching con frozen recipients;
- provider phone unmatched se conserva;
- frozen recipient ausente no recibe estado inventado;
- FAILED siempre con delivery bucket null;
- button labels recipient-level preservadas;
- `not_synced` y analytics null persistibles;
- rollback no deja snapshot parcial;
- history/latest ordenados por fetched_at/id desc;
- constraint de fingerprint soporta carreras de idempotencia.

M12-M15:
- scheduler disabled por defecto y sin provider calls cuando está deshabilitado;
- configuración incompleta M12 queda aislada del resto del marketing-scheduler;
- cleanup de `db.session`;
- M13 read-only con sesión dirty/no_autoflush;
- scope histórico backend-authoritative;
- lookback inclusivo basado en `fetched_at`;
- M14 OR exclusion + Preview/Freeze reproducible;
- drift histórico entre Preview y Freeze produce PreviewMismatch;
- M15 payload coincide exactamente con M14;
- M15 no llama M13/iVentas ni envía cutoff/resultados históricos.

M16 acceptance transversal de 2A:
- provider binding -> provider stats double -> snapshot M11 -> observations -> history M13 -> M14 Preview -> Freeze;
- A=VIEWED, B=FAILED, C=button interaction y D sin history visible deja sólo D;
- evidencia del mismo teléfono fuera de scope no afecta Preview;
- snapshot idéntico es idempotente y no duplica observations;
- mismo Preview sin cambios conserva fingerprint;
- nueva evidencia histórica posterior invalida el fingerprint aprobado;
- todo el historial y lookback producen resultados distintos cuando corresponde.

## 30. Criterio de aceptación de M8 provider read-only

M8 queda cerrado cuando:

- `GET /v2/broadcast/stats/{campaign_id}` está implementado read-only con credencial separada;
- parser y provider reflejan el payload real observado;
- `successful/failed` se modelan como outcome;
- `sent/delivered/viewed` se modelan como buckets recipient-level disjuntos observados;
- `sentdMessages` sólo es compatibilidad legacy;
- button interactions recipient-level quedan separadas de free-text agregado;
- `answeredMessages` no fabrica responders;
- analytics permanece agregado/opaco;
- no se inventan timestamps ni failure cause por teléfono;
- suite M8 y regresión relacionada están verdes;
- no existe persistencia, envío ni frontend en este milestone.

El criterio:

    saber qué números de una campaña pertenecen a
    sent / delivered / viewed / failed

queda satisfecho en modo read-only para un `campaign_id` conocido mediante campaign stats.

## 30.1 Historical Targeting transversal — contrato previo obligatorio a 2C/2D

Historical Targeting es una capacidad transversal del Audience Builder y no una fuente nueva ni un caso especial de Socios Vencidos.

Su objetivo es reutilizar la evidencia persistida por M11/M13 para que el comportamiento histórico por `phone_mx10` pueda actuar tanto como **criterio positivo de inclusión** como **regla de exclusión**, sobre:

- `EXPIRED_MEMBERS`;
- `ACTIVE_MEMBERS`;
- `FUNNEL_PORTFOLIO`;
- futuras fuentes Campaign V2 que atraviesen el mismo Audience Builder.

No se crea un histórico paralelo y Preview/Freeze no consultan iVentas. La única frontera histórica v1 sigue siendo la evidencia persistida y el core M13.

### 30.1.1 Estado y posición contractual

La estructura de Fase 2 permanece:

    2A — iVentas / histórico / engagement      ACCEPTED
    2B — FUNNEL_PORTFOLIO                      ACCEPTED

    Historical Targeting transversal           ACCEPTED

    2C — Campaign BI / Reporting / Excel       PENDIENTE
    2D — Acceptance final                      PENDIENTE

No se renumeran 2A/2B/2C/2D.

Historical Targeting está implementado y ACCEPTED mediante M21–M25. 2C/2D siguen pendientes y Fase 3 continúa bloqueada hasta completar toda Fase 2.

### 30.1.2 Contrato conceptual v1

La forma conceptual nueva es:

    {
      "historical_targeting": {
        "mode": "INCLUDE",
        "match": "ALL",
        "delivery_buckets": ["VIEWED"],
        "outcomes": [],
        "button_interacted": true,
        "lookback_days": 90
      }
    }

Reglas:

- `mode`: `INCLUDE | EXCLUDE`;
- `match`: `ALL | ANY`;
- `delivery_buckets`: subconjunto de `SENT | DELIVERED | VIEWED`;
- `outcomes`: subconjunto de `SUCCESSFUL | FAILED`;
- `button_interacted`: `true` o ausente/`false`;
- `lookback_days`: `null` o entero positivo;
- si `historical_targeting` está presente debe existir al menos una condición efectiva;
- Angular construye criterios; no envía teléfonos preseleccionados, resultados históricos ni cutoffs efectivos.

No se agregan en v1:

- `RESPONDED`;
- `FREE_TEXT_RESPONSE`;
- `NO_RESPONSE`;
- `UNANSWERED`;
- causa de fallo recipient-level;
- `sent_at/delivered_at/viewed_at`;
- filtros por campaña específica;
- purpose histórico específico;
- última campaña o última campaña aplicable.

### 30.1.3 Semántica de `mode`

#### INCLUDE

El contacto permanece en la audiencia únicamente si la regla histórica hace match.

Ejemplo:

    mode = INCLUDE
    signals = [VIEWED, BUTTON_INTERACTION]
    match = ALL

equivale a conservar teléfonos que demuestran:

    VIEWED
    AND
    BUTTON_INTERACTION

#### EXCLUDE

El contacto se elimina si la regla histórica hace match.

Ejemplo:

    mode = EXCLUDE
    signals = [VIEWED, BUTTON_INTERACTION]
    match = ANY

equivale a excluir teléfonos que demuestran:

    VIEWED
    OR
    BUTTON_INTERACTION

`INCLUDE` nunca revive un recipient eliminado previamente por una regla obligatoria de negocio.

### 30.1.4 Semántica de `match`

Las cuatro combinaciones quedan congeladas explícitamente:

    INCLUDE + ALL
    -> conservar si cumple TODAS las señales

    INCLUDE + ANY
    -> conservar si cumple AL MENOS UNA señal

    EXCLUDE + ALL
    -> excluir sólo si cumple TODAS las señales

    EXCLUDE + ANY
    -> excluir si cumple AL MENOS UNA señal

No existe interpretación implícita. El backend es la autoridad.

### 30.1.5 Señales soportadas v1

Sólo pueden utilizarse señales ya respaldadas por evidencia persistida:

    SENT
    DELIVERED
    VIEWED

    SUCCESSFUL
    FAILED

    BUTTON_INTERACTION

Separación semántica:

- `SENT/DELIVERED/VIEWED` son delivery buckets recipient-level observados;
- `SUCCESSFUL/FAILED` son outcomes;
- `BUTTON_INTERACTION` significa interacción recipient-level identificable.

No existe jerarquía implícita `VIEWED => DELIVERED => SENT` para esta regla. Se consulta exactamente la evidencia observada.

### 30.1.6 ALL puede satisfacerse entre campañas históricas diferentes

La semántica v1 opera sobre `ever_observed` transversal del teléfono dentro de la ventana.

Para:

    signals = [VIEWED, BUTTON_INTERACTION]
    match = ALL

es válido que:

    Campaign A -> VIEWED
    Campaign B -> BUTTON_INTERACTION

y el resultado sea:

    ALL = true

No se exige que las señales coexistan en una misma campaña histórica.

Filtrar por `campaign_id`, purpose, última campaña o misma provider campaign queda explícitamente diferido porque requiere otra semántica.

### 30.1.7 Ventana histórica

Se soportan:

    ALL_HISTORY

y:

    LOOKBACK_DAYS = entero positivo

Se reutiliza la semántica temporal de M13/M14:

    observed_at = snapshot.fetched_at

Esto significa momento en que Suite observó el estado, no timestamp real de WhatsApp.

El cutoff sigue siendo backend-authoritative:

- Angular no envía `observed_before`;
- Angular no envía `observed_after`;
- Preview resuelve el cutoff efectivo;
- Preview Detail reconstruye contra evidencia vigente;
- Freeze reconstruye nuevamente;
- con `lookback_days=N`, la ventana se deriva desde el cutoff autoritativo;
- si nueva evidencia relevante cambia el resultado entre Preview y Freeze debe ocurrir `PreviewMismatch`.

### 30.1.8 Orden dentro del Audience Builder

Pipeline general:

    SOURCE
      -> reglas propias de la fuente
      -> scope backend
      -> teléfonos válidos
      -> supresiones obligatorias de negocio
      -> HISTORICAL TARGETING
      -> dedupe
      -> Preview
      -> Freeze

Para Funnel:

    FUNNEL_PORTFOLIO
      -> comprador/no comprador canónico
      -> normalización de teléfono
      -> ACTIVE_MEMBER_SUPPRESSION
      -> scope backend
      -> HISTORICAL TARGETING
      -> dedupe
      -> Preview
      -> Freeze

Para otras fuentes:

    source-specific filters
      -> scope backend
      -> teléfonos válidos
      -> HISTORICAL TARGETING
      -> dedupe

No se crean filtros históricos específicos por source.

### 30.1.9 Supresiones obligatorias ganan sobre INCLUDE

Historical Targeting no puede volver a incluir un recipient ya eliminado por una supresión obligatoria.

Ejemplo Funnel:

    ACTIVE_MEMBER_SUPPRESSION
      -> elimina el número

después:

    INCLUDE VIEWED

no puede restaurarlo.

Por tanto `INCLUDE` es una condición adicional sobre candidatos aún elegibles, no una excepción de reglas comerciales o de permisos.

### 30.1.10 Scope y permisos

Historical Targeting reutiliza exactamente el scope Campaign V2.

Evidencia histórica de campañas fuera del scope del usuario:

- no puede influir en `INCLUDE`;
- no puede influir en `EXCLUDE`;
- no entra en counts;
- no genera reasons;
- no aparece en Preview Detail.

No se modifica M13 para ampliar visibilidad. `NULL` nunca significa acceso global.

### 30.1.11 Compatibilidad con M14/M15

Hoy existe:

    history_exclusion

La capacidad futura común se denomina:

    historical_targeting

Las campañas ya congeladas con `history_exclusion` **no se reinterpretan retroactivamente**.

Su significado legacy queda congelado exactamente como:

    mode = EXCLUDE
    match = ANY

con las mismas señales y ventana ya persistidas por M14/M15.

No se exige migración destructiva de `audience_definition_json` histórico.

Estrategia recomendada para implementación futura:

1. el lector de campañas debe seguir entendiendo `history_exclusion` legacy;
2. la UI de campañas históricas debe poder representarlo con su semántica original;
3. nuevas campañas deben converger en `historical_targeting`;
4. si temporalmente se acepta `history_exclusion` como payload legacy, debe normalizarse server-side sin cambiar su significado;
5. una vez retirada esa compatibilidad de escritura, `history_exclusion` puede permanecer únicamente como formato de lectura histórica.

Esta enmienda no decide todavía en qué milestone exacto se elimina la escritura legacy; sólo prohíbe romper campañas M14/M15 ya persistidas.

### 30.1.12 Preview diagnostics

El diseño debe soportar diagnostics genéricos:

    before_history_filter_count
    history_matched_count
    history_not_matched_count
    history_included_count
    history_excluded_count
    after_history_filter_count

Los nombres exactos podrán ajustarse al implementar si es necesario para compatibilidad, pero la semántica debe distinguir:

- población evaluada;
- población que hizo match;
- población que no hizo match;
- efecto final de `INCLUDE` o `EXCLUDE`.

Se mantienen reasons canónicas:

    HISTORY_DELIVERY_SENT
    HISTORY_DELIVERY_DELIVERED
    HISTORY_DELIVERY_VIEWED
    HISTORY_OUTCOME_SUCCESSFUL
    HISTORY_OUTCOME_FAILED
    HISTORY_BUTTON_INTERACTION

Un teléfono puede acumular múltiples reasons. Los reason counts pueden solaparse y nunca se suman para reconstruir el total de recipients.

### 30.1.13 Preview Detail

Preview Detail debe permitir explicar:

- si el teléfono hizo match histórico;
- qué reasons canónicas sustentan ese match;
- `mode`;
- `match`;
- señales configuradas;
- si el resultado terminó incluido o excluido.

No se inventan eventos individuales, timestamps provider ni campañas específicas cuando la evidencia v1 sólo demuestra `ever_observed`.

### 30.1.14 Fingerprint, Freeze y persistencia

Historical Targeting participa íntegramente en:

- `audience_definition_json`;
- `source_metadata.history_evaluation`;
- Preview fingerprint;
- Freeze rebuild.

Deben formar parte del fingerprint, directa o derivadamente:

- `mode`;
- `match`;
- señales seleccionadas;
- `lookback_days`;
- cutoff histórico backend-authoritative;
- resultado final de recipients.

Si nueva evidencia histórica relevante aparece entre Preview y Freeze y altera cutoff o recipients, Freeze debe producir `PreviewMismatch`.

Angular nunca puede enviar como autoridad:

- snapshot IDs;
- `observed_before`;
- `observed_after`;
- teléfonos que hicieron match;
- recipients finales;
- resultados históricos precalculados.

### 30.1.15 Read-only / frontera provider

Historical Targeting utiliza únicamente:

- M11 snapshots;
- M11 recipient observations;
- M13 history.

Preview y Freeze:

- no llaman iVentas;
- no hacen provider HTTP;
- no capturan snapshots;
- no activan M12.

La frescura del histórico pertenece a los mecanismos separados de captura/sync.

### 30.1.16 UX Angular objetivo

La UX objetivo es:

    Historial de campañas

    Modo:
    ○ Incluir sólo contactos que cumplan
    ○ Excluir contactos que cumplan

    Condiciones:
    ☐ Enviado
    ☐ Entregado
    ☐ Visto
    ☐ Exitoso
    ☐ Fallido
    ☐ Interactuó con botón

    Cumplimiento:
    ○ Todas
    ○ Cualquiera

    Ventana:
    ○ Todo el historial
    ○ Últimos N días

Angular:

- construye únicamente criterios;
- invalida Preview ante cualquier cambio;
- no resuelve histórico;
- no llama M13 directamente;
- no llama iVentas;
- no envía cutoffs efectivos.

### 30.1.17 No es un rule builder general

v1 queda deliberadamente limitado a:

    un mode
    un match
    N señales
    una ventana

No se diseñan:

- expresiones anidadas;
- `(A AND B) OR (C AND NOT D)`;
- grupos recursivos;
- SQL visual;
- `NOT` por señal individual;
- scoring;
- pesos;
- ranking.

### 30.1.18 Acceptance futura mínima

La implementación debe probar las cuatro combinaciones:

    INCLUDE + ALL
    INCLUDE + ANY
    EXCLUDE + ALL
    EXCLUDE + ANY

Fixture conceptual mínimo:

    A = VIEWED
    B = BUTTON
    C = VIEWED + BUTTON
    D = sin history

Resultados obligatorios:

    INCLUDE + ALL [VIEWED, BUTTON]
    -> sólo C

    INCLUDE + ANY [VIEWED, BUTTON]
    -> A + B + C

    EXCLUDE + ALL [VIEWED, BUTTON]
    -> elimina C

    EXCLUDE + ANY [VIEWED, BUTTON]
    -> elimina A + B + C

Además debe probar:

- mezcla de delivery/outcome/button;
- lookback;
- scope;
- contacto sin history;
- compatibilidad legacy `history_exclusion`;
- fingerprint estable sin cambios;
- drift histórico -> `PreviewMismatch`;
- ninguna provider call;
- ninguna ampliación de scope;
- supresiones obligatorias preceden a Historical Targeting.

## 31. Fase 2C — Campaign BI / Reporting / Excel

### 31.1 Objetivo y frontera read-only

2C convierte la evidencia persistida de Campaign V2 en reportes operativos y ejecutivos:

    Campaign V2
      -> snapshots M11
      -> recipient observations
      -> analytics provider
      -> reporting projection
      -> dashboard
      -> Excel

Reporting es **read-only respecto al provider**. Generar un reporte o exportar Excel **no consulta iVentas** y usa únicamente información ya persistida por Suite.

Si se necesita mayor frescura, `captura/sync` es una operación separada del reporting.

### 31.2 Dos niveles de reporte

El reporte individual de campaña debe poder mostrar como mínimo:

- Campaign V2;
- nombre;
- purpose;
- provider;
- provider_campaign_id;
- analytics_status;
- latest_observed_at;
- destinatarios;
- successful;
- failed;
- sent;
- delivered;
- viewed;
- reached;
- delivery/reach rate;
- read rate;
- failure rate;
- button interaction recipients;
- button interaction groups;
- responders agregados cuando provider los entregue;
- freeText agregado cuando provider lo entregue;
- costo;
- currency;
- cost status;
- KPIs de costo disponibles.

El reporte consolidado debe permitir comparar varias campañas por:

- periodo observado;
- campaign;
- purpose;
- provider;
- sucursal cuando sea atribuible;
- audience family cuando exista evidencia.

Ejemplo conceptual:

    Campaign       Dest. Reach Viewed Interactions Failed Cost
    React Oct 01     528   491    295       63       31   ...
    VN Oct 02        ...

### 31.3 Métricas y denominadores

`efectividad` no es una métrica canónica única hasta que negocio defina cuál desea usar. Reporting debe presentar métricas con nombre y denominador explícitos.

Como mínimo:

    total_recipients

    successful_rate =
      successful / total_recipients

    reach_count =
      DELIVERED ∪ VIEWED

    reach_rate =
      reach_count / total_recipients

    read_rate =
      viewed / reach_count

    failure_rate =
      failed / total_recipients

Toda división debe proteger denominador cero.

Bajo las invariantes actuales `DELIVERED ∩ VIEWED = ∅`, `reach_count` equivale hoy a `delivered + viewed`; cuando se trabaje recipient-level debe implementarse conceptualmente como conjunto/unión.

### 31.4 Provider raw vs Suite normalized

Reporting debe distinguir siempre entre:

- raw provider counts;
- normalized unique recipients.

Nunca debe mezclar ambos silenciosamente. Si varios formatos de teléfono del provider colapsan durante normalización, el reporte debe conservar y explicar esa diferencia.

### 31.5 Respuestas e interacciones

Se conserva la semántica vigente de 2A:

    analytics responders
      -> agregado provider

    analytics freeText
      -> agregado provider

    button interactions
      -> recipient-level identificable

No se exportan listas ficticias de `responded_phones`, `free_text_responders`, `no_answer` o `unanswered`.

Cuando existan, el reporte puede mostrar de forma explícita valores como:

    Responders agregados: 79
    Interacción botón identificable: 63
    Free text agregado: 16

### 31.6 Costos

La primera implementación debe consumir `snapshot.analytics_json` mediante una projection/extractor testeado.

No se normalizan anticipadamente todos los campos de costo a columnas DB.

Campos observados que pueden exponerse sólo cuando estén realmente presentes/soportados:

- currency;
- status;
- estimated;
- real.total;
- byCountry;
- costPerDelivered;
- costPerResponse;
- spendWithoutResponse;
- provider;
- paymentMethod.

Si el costo falta, el valor es `unavailable`/`null`, nunca `0` por ausencia.

No se suman costos de monedas distintas. El consolidado agrupa o separa por `currency` y marca cualquier total incompleto.

### 31.7 KPIs derivados por Suite

Si se agregan métricas como `cost_per_reached`, `cost_per_viewed` o `cost_per_button_interaction`, deben:

- etiquetarse como derivadas por Suite;
- documentar fórmula;
- documentar moneda;
- devolver `null` si el denominador es cero;
- no confundirse con un KPI del provider.

### 31.8 Evolución temporal

2C puede aprovechar los snapshots append-only de M11 para representar evolución por `fetched_at`, por ejemplo:

    fetched_at    SENT  DELIVERED  VIEWED
    10:00          ...
    12:00          ...
    18:00          ...

Debe describirse como **estado observado por Suite**. No se presenta como `sent_at`, `delivered_at` o `viewed_at` real del provider.

### 31.9 Histórico transversal

Reporting puede reutilizar M13 para análisis como:

- teléfono nunca observado anteriormente;
- teléfono previamente impactado;
- ever VIEWED;
- ever FAILED;
- ever button_interaction.

Debe distinguir el histórico previo a la campaña analizada de los resultados de la campaña actual para evitar leakage temporal.

2C no crea scoring.

### 31.10 Sucursal, propósito y familia

Sólo se agrupa por dimensiones atribuibles con evidencia:

- `purpose`: usar Campaign V2 purpose persistido;
- `sucursal`: usar relación/scope/binding disponible; no inferir por lada ni inventar desde phone;
- `audience_family`: usar metadata congelada cuando exista.

Si una dimensión no puede resolverse, usar `UNKNOWN`/`UNAVAILABLE` según la convención existente.

### 31.11 Excel

La exportación se genera **backend-side**. Angular solicita y descarga el archivo; no recalcula KPIs.

Arquitectura objetivo del workbook:

    1. Resumen
    2. Campañas
    3. KPIs
    4. Destinatarios
    5. Interacciones
    6. Costos
    7. Evolución
    8. Metadata

No es obligatorio implementar todas las hojas en el primer milestone si se preserva el contrato funcional, pero la arquitectura debe permitirlas.

Excel debe incluir:

- generated_at;
- filtros aplicados;
- última observación disponible;
- analytics_status;
- definiciones/denominadores relevantes.

No se hacen provider calls durante export.

### 31.12 Privacidad, permisos y freshness

Reporting reutiliza los permisos backend de Campaign V2.

El scope del usuario limita:

- campañas;
- recipients;
- agregaciones;
- exportaciones.

Un consolidado no puede revelar información de otra sucursal.

El Excel nunca debe contener:

- API keys;
- Authorization;
- payload provider raw innecesario;
- headers;
- secrets.

Los teléfonos sólo aparecen cuando el permiso y el propósito del reporte lo justifican. No se loggean teléfonos durante export.

Todo reporte debe poder indicar `latest_observed_at` y `analytics_status`.

M12 deshabilitado no bloquea Reporting; significa que la frescura depende de snapshots existentes/manuales hasta activar captura automática.

### 31.13 No duplicar persistencia

La primera implementación de Reporting debe reutilizar:

- Campaign V2;
- frozen recipients;
- M11 snapshots;
- M11 observations;
- M13 history;
- `analytics_json`.

No crear una reporting mega-table, copia de snapshots o copia de recipients salvo que una necesidad de rendimiento medida lo justifique posteriormente.

## 32. Fase 2D — Acceptance final

Fase 2 queda finalmente aceptada cuando estén cerrados:

    2A — iVentas/history                 PASS
    2B — FUNNEL_PORTFOLIO                PASS
    Historical Targeting transversal     PASS
    2C — Campaign BI/Reporting           PASS

La aceptación integral debe comprobar:

- Funnel -> Preview -> Freeze;
- ACTIVE_MEMBER_SUPPRESSION;
- Historical Targeting `INCLUDE/EXCLUDE` + `ALL/ANY`;
- compatibilidad legacy `history_exclusion`;
- reporting individual;
- reporting consolidado;
- Excel;
- scope/permisos;
- no provider writes;
- no envío.

Sólo después puede comenzar:

    Fase 3 — POST /v2/broadcast

## 33. Pendientes y trabajo posterior

PENDIENTE PARA CERRAR FASE 2:

- Campaign BI;
- Excel;
- Angular Reporting;
- acceptance final.

POSTERIOR / NO BLOQUEANTE salvo necesidad:

- importación automática de campañas externas;
- listado provider por periodo no confirmado;
- GraphQL histórico;
- normalización DB específica de costos;
- activación productiva M12.

`FUNNEL_PORTFOLIO` está ACCEPTED como 2B. Historical Targeting transversal también está ACCEPTED; 2C/2D permanecen pendientes antes de habilitar Fase 3.

## 34. Instrucción de arranque recomendada para una conversación nueva de Fase 2

    Estamos implementando únicamente Campañas V2 Fase 2.
    Este archivo es autosuficiente; no asumas contexto de conversaciones anteriores.
    2A — iVentas / histórico / engagement está IMPLEMENTADA, ACCEPTED M16 y DEPLOYADA.
    Conserva sin reinterpretar successful/failed, SENT/DELIVERED/VIEWED,
    snapshots append-only, fetched_at, button interactions e history exclusions.
    M12 permanece implementada pero disabled hasta definir cadence/horizon/max.
    2B — FUNNEL_PORTFOLIO está ACCEPTED.
    Conserva la lógica comprador/no comprador canónica del Funnel,
    normalize phone, ACTIVE_MEMBER_SUPPRESSION, scope backend,
    history M14, dedupe, Preview/Detail, fingerprint, Freeze y Angular.
    Historical Targeting transversal está ACCEPTED mediante M21–M25.
    Reutiliza M13 con INCLUDE/EXCLUDE + ALL/ANY, Preview Detail neutral,
    fingerprint/Freeze y Angular sin romper campañas M14/M15 con history_exclusion.
    2C — Campaign BI / Reporting / Excel está PENDIENTE.
    Reporting usa sólo evidencia persistida por Suite y no consulta iVentas.
    Export Excel es backend-side y Angular no recalcula KPIs.
    2D sólo pasa cuando 2A + 2B + Historical Targeting + 2C tienen aceptación integral.
    No implementes POST /v2/broadcast ni GraphQL mutations.
