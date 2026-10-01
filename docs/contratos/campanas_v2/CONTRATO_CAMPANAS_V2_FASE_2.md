# Contrato Campañas V2 — Fase 2

Estado: CONTRATO DE LECTURA/BI; NO AUTORIZA ENVÍO  
Dependencia de ejecución: Fase 1 debe estar terminada y comprobada en el repositorio; este archivo es autosuficiente como contexto.  
Objetivo: integrar resultados de campañas iVentas con Campañas V2 sin acoplar el núcleo al proveedor e incorporar, antes del enviador, la Cartera Funnel de Venta Nueva como fuente phone-centric.

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
- `FUNNEL_PORTFOLIO` se integra en esta fase, antes del enviador. Su identidad mínima puede ser teléfono; `contact_id`, nombre, sucursal, canal y fecha son enriquecimientos cuando existan.
- Funnel debe reutilizar su lógica existente de compradores/no compradores y además aplicar supresión por teléfono contra el snapshot canónico vigente de Socios Activos.
- Esta fase es solo lectura/BI de iVentas + Cartera Funnel. **No implementar POST /v2/broadcast.**

Modo de trabajo:

1. inspeccionar `main` y confirmar Fase 1;
2. revisar integración iVentas y Funnel existentes antes de crear código;
3. explicar un solo cambio mínimo y su prueba;
4. no modelar campos no observados en un payload real;
5. no avanzar a Fase 3.

### 0.1 Enmienda M8 — evidencia real observada y frontera vigente

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

Fase 2 contiene dos bloques que deben quedar listos antes de Fase 3:

- **2A — iVentas lectura/BI:** lectura y sincronización de campañas.
- **2B — Cartera Funnel:** fuente de audiencia para Venta Nueva/Funnel, tolerante a identidad incompleta.

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

## 31. Limitaciones que permanecen abiertas para Fase 2

El cierre M14 **no cierra toda Fase 2**. Permanecen abiertos:

- definición/activación operativa de los valores productivos de cadence/horizon/max;
- listado/importación de campañas por periodo;
- representación/persistencia de campañas externas;
- normalización específica de costos cuando vaya a consumirse;
- branch resolution para campañas externas cuando aplique;
- UI Angular para configurar los filtros históricos ya cerrados en backend;
- GraphQL histórico por teléfono si se requiere para otro caso de uso;
- Cartera Funnel y sus reglas completas;
- preparación para Fase 3/envío.

No iniciar Fase 3 hasta cerrar los requisitos restantes de Fase 2 que correspondan al flujo de envío.

## 32. Instrucción de arranque recomendada para una conversación nueva de Fase 2

    Estamos implementando únicamente Campañas V2 Fase 2.
    Este archivo es autosuficiente; no asumas contexto de conversaciones anteriores.
    M8 provider read-only ya existe y usa:
      GET /v2/broadcast/stats/{campaign_id}
      IVENTAS_CAMPAIGNS_API_KEY
    Reutiliza normalize_iventas_phone() y las capas:
      IVentasCampaignsClient
      parse_iventas_campaign_stats()
      IVentasCampaignProvider
      CampaignProviderStats
    sentMessages es canónico; sentdMessages sólo fallback legacy.
    No derives responders desde answeredMessages.
    interactions[].items son button interactions recipient-level.
    analytics/freeText/failures/cost permanecen agregados salvo contrato posterior.
    No inventes timestamps ni failure cause por teléfono.
    M9 ya persiste únicamente provider + provider_campaign_id en Campaign V2.
    Usa PUT /campaigns-v2/{campaign_id}/provider-binding para ese vínculo.
    No rebindear una campaña a otra identidad provider.
    M10 ya expone GET /campaigns-v2/{campaign_id}/provider-stats como read-through.
    Ese endpoint obtiene provider/external id sólo de la Campaign V2 persistida.
    M11 persiste snapshots append-only y recipient observations.
    M12 reutiliza marketing-scheduler para captura automática configurable.
    M12 permanece disabled hasta definir explícitamente interval/horizon/max.
    M13 expone histórico transversal bulk sobre snapshots M11, sin provider calls.
    M13 usa observed_at=fetched_at y no fabrica timestamps provider.
    M14 integra exclusiones históricas OR en Audience Builder con cutoff backend-authoritative.
    M14 persiste sólo criterios + history_evaluation; no copia snapshots.
    No reemplaces snapshots M11 por estado mutable ni inventes timestamps/causas recipient-level.
    No implementes POST /v2/broadcast ni GraphQL mutations.
