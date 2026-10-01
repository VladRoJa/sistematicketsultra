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

Esta enmienda corrige supuestos del contrato original a partir de evidencia real observada en la aplicación web de iVentas. **Si una sección posterior entra en conflicto con esta enmienda, prevalece esta enmienda.**

M8 reconoce dos capacidades independientes:

1. **Campaign aggregate analytics**
   - evidencia observada en:
     `GET https://iventas-analytics-v1-production.up.railway.app/campaign-stats/campaigns/{campaignId}?companyId={companyId}`;
   - devuelve analytics agregados de campaña, incluyendo campos observados como `totalRecipients`, `funnel`, `rates`, `failures`, `costs`, `interactions` y `temporal`;
   - no se observó en esta frontera una lista de destinatarios/teléfonos por estado.

2. **Recipient/message historical status**
   - evidencia observada mediante GraphQL HTTP en `graph-v2.iventas.mx`;
   - la app resuelve primero conversación/cliente por teléfono y obtiene `Client.id`;
   - después consulta historial por `Client.id` mediante una query `messages`;
   - se observaron, entre otros, `sender`, `messageStatus`, `errorCode`, `errorInfo`, `createdAt`, `seenAt`, `messageApiId` y `quotedMsgId`.

Frontera histórica observada:

    phone
      -> Client.id
      -> messages(clientId)
      -> sender / messageStatus / errorCode / errorInfo / createdAt

Reglas derivadas de la evidencia:

- `sender == CLIENT` identifica inbound en los casos observados.
- Un inbound con `messageStatus = null` **no** representa estado delivery y no debe convertirse en `sent`, `delivered`, `viewed`, `failed` ni equivalente.
- Cuando un inbound cumple `quotedMsgId == outbound.messageApiId`, existe evidencia positiva de respuesta a **ese outbound concreto**.
- La ausencia de esa relación no significa “no respondió”.
- `createdAt`, `seenAt` u otros timestamps del proveedor no deben reinterpretarse todavía como `sent_at`, `delivered_at` o `viewed_at` sin evidencia adicional de su semántica.
- La correlación `Campaign V2 recipient -> outbound provider message` **permanece abierta**. Haber encontrado historial por teléfono no demuestra todavía qué outbound individual pertenece a una campaña concreta.
- El criterio de salida de Fase 2 que exige `sent/delivered/viewed/failed` **por número y por campaña** permanece bloqueado hasta demostrar esa correlación.

Supuestos retirados como contrato implementable:

- `GET /v2/broadcast/stats/:id` **NO OBSERVADO** como frontera válida con un campaign ID real.
- `successfulMessages`, `failedMessages`, `sentMessages`, `deliveredMessages`, `viewedMessages`, `answeredMessages` y su shape por destinatario quedan **NO OBSERVADOS**.
- No construir provider, parser ni persistencia recipient-level basándose en esos arrays hasta obtener evidencia real compatible.

Regla de seguridad M8:

- solo operaciones provider estrictamente read-only;
- HTTP GET read-only permitido;
- GraphQL `query` read-only mediante HTTP POST permitido;
- GraphQL `mutation` prohibida;
- `POST /v2/broadcast` prohibido;
- no asumir que `IVENTAS_API_TOKEN` actual es intercambiable con la credencial usada por el frontend GraphQL; debe comprobarse de forma read-only antes de integrar.

## 1. Alcance exacto

Fase 2 contiene dos bloques que deben quedar listos antes de Fase 3:

- **2A — iVentas lectura/BI:** lectura y sincronización de campañas.
- **2B — Cartera Funnel:** fuente de audiencia para Venta Nueva/Funnel, tolerante a identidad incompleta.

Debe permitir:

- asociar una campaña V2 con un campaign_id de iVentas;
- importar campañas creadas directamente en iVentas cuando exista forma de descubrirlas;
- consultar analytics agregados de una campaña cuando la frontera observada y la credencial backend lo permitan;
- consultar histórico de mensajes por teléfono cuando la frontera GraphQL observada y la credencial backend lo permitan;
- persistir estados por destinatario **solo después** de demostrar la correlación campaña concreta -> outbound provider message;
- persistir interacciones recipient-level **solo si** existe evidencia individual suficiente;
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

La evidencia M8 distingue además dos superficies nuevas:

- Campaign Analytics: analytics agregados por `campaignId + companyId`;
- GraphQL histórico: conversación/Client y mensajes por `Client.id`.

No existe todavía evidencia de una sola API que entregue simultáneamente campaña concreta + destinatarios + estados individuales.

No mezclar estas cosas.

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

Cuando exista correlación demostrada entre una campaña concreta y sus mensajes individuales, los hechos de delivery deberán guardarse en el recipient/delivery de **esa campaña**, nunca como estado global del contacto.

Hasta resolver `Campaign V2 recipient -> outbound provider message`, M8 **no autoriza** persistir `sent`, `delivered`, `viewed`, `failed` ni interacciones recipient-level como hechos de una campaña.

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

Fase 2 debe introducir o completar una abstracción de proveedor.

La abstracción debe representar **capacidades independientes**, sin fingir que analytics agregados e historial por destinatario son la misma respuesta.

Interfaz conceptual mínima:

    CampaignProvider
        capabilities()

        # capability independiente
        get_campaign_aggregate_analytics(provider_campaign_id, provider_company_id)

        # capability independiente
        resolve_recipient_by_phone(phone_mx10)
        get_recipient_message_history(provider_client_id, ...)

        # opcional solo con evidencia
        list_campaigns(period)
        get_campaign_recipient_delivery(...)

Implementación futura:

    IVentasCampaignProvider

M8 no implementará todavía esta interfaz hasta validar acceso backend read-only a las fronteras observadas.

El resto del módulo no debe conocer URLs, GraphQL, nombres concretos de campos externos ni detalles de Apollo salvo en el adaptador.

## 7. Capacidades conocidas de iVentas

### 7.1 Campaign aggregate analytics — OBSERVADO

Frontera observada en Network:

    GET https://iventas-analytics-v1-production.up.railway.app/campaign-stats/campaigns/{campaignId}?companyId={companyId}

En una campaña real se observaron analytics agregados con campos como:

- `totalRecipients`;
- `funnel.accepted`;
- `funnel.delivered`;
- `funnel.read`;
- `funnel.failed`;
- `rates.deliveryRate`;
- `rates.readRate`;
- `rates.failureRate`;
- `rates.responseRate`;
- `failures`;
- `costs`;
- `interactions`;
- `temporal`.

También se observaron costo real/provisional, moneda, errores Meta y responders dentro del payload agregado.

**No se observó una lista de destinatarios/teléfonos por estado en esta frontera.**

El shape exacto de `costs`, `failures`, `interactions`, `temporal` y otros objetos debe congelarse con payload sanitizado antes de programar parser.

### 7.2 Recipient/message historical status — OBSERVADO

Transporte observado:

- GraphQL HTTP;
- host `graph-v2.iventas.mx`;
- Apollo `HttpLink`;
- header `Authorization: Bearer <token>`.

La app primero resuelve conversación/cliente mediante una operación equivalente a `conversationByFilters`, donde se observaron:

- `Client.id`;
- `senderId`;
- `phoneNumber`;
- `lastMessageId`.

Después consulta historial mediante una query equivalente a:

    messages(
      where: {clientId: $id}
      orderBy: createdAt_DESC
      skip: $skip
      first: 30
    )

con campos observados como:

- `id`;
- `content`;
- `time`;
- `createdAt`;
- `seen`;
- `seenAt`;
- `messageStatus`;
- `errorCode`;
- `errorInfo`;
- `seenBy`;
- `sender`;
- `senderId`;
- `messageApiId`;
- `messageType`;
- `structuredPayload`;
- `quotedMsgId` cuando aplique.

La paginación observada usa `skip=0,30,60...`.

### 7.3 Broadcast stats anterior — NO OBSERVADO

La documentación anterior mencionaba:

    GET /v2/broadcast/stats/:id

y arrays:

- `successfulMessages`;
- `failedMessages`;
- `sentMessages`;
- `deliveredMessages`;
- `viewedMessages`;
- `answeredMessages`;
- `interactions`;
- `analytics`;
- `analyticsStatus`.

Sin embargo, al probar esa ruta con un campaign ID real se obtuvo “no se encontró la orden”. Por tanto:

- la ruta no queda confirmada como frontera real para Campañas V2;
- los arrays anteriores quedan **NO OBSERVADOS**;
- `analyticsStatus = ok/not_synced/unavailable/disabled` queda **NO OBSERVADO** en las fronteras reales ahora conocidas;
- no se implementará parser, persistence ni capability basados en esa estructura hasta recibir evidencia real compatible.

## 8. Estado histórico por destinatario

La evidencia actual permite consultar **historial de mensajes por teléfono/Client.id**, pero no atribuir todavía cada outbound a una campaña concreta de Campaign V2.

En registros observados:

- outbound: `sender != CLIENT` y puede tener `messageStatus` como `viewed`;
- inbound: `sender == CLIENT` y se observó `messageStatus = null`.

Reglas:

- `sender == CLIENT` se trata como inbound observado.
- `messageStatus = null` de un inbound no se convierte en ningún estado delivery.
- Estados observados en mensajes deben conservarse con su semántica provider; no se convierten automáticamente en flags de campaign-recipient.
- Historial por teléfono puede servir como dimensión de comportamiento previa, pero debe distinguir “mensaje histórico observado” de “mensaje atribuido a una campaña concreta”.
- La correlación `Campaign V2 recipient -> outbound provider message` queda como requisito pendiente.

### 8.1 Resolver de comportamiento histórico por teléfono

Fase 2 debe poder derivar comportamiento histórico a partir de evidencia provider observada, sin escribir flags históricos en tablas fuente.

Mientras no exista correlación por campaña, cualquier resolver inicial debe limitarse a afirmaciones soportadas por el historial de mensajes por teléfono, por ejemplo:

    has_any_provider_message_history
    has_any_observed_viewed_message

No debe afirmar todavía:

    last_campaign_viewed
    viewed_in_campaign_X
    contacted_never_viewed_in_campaign_X

salvo que exista una relación demostrada entre campaña y outbound.

Semántica importante:

- “sin historial observado” no equivale a “nunca contactado” fuera del alcance de los datos consultados.
- La ausencia de un `messageStatus` concreto no equivale a un estado negativo.
- La ausencia de una respuesta con quote no equivale a “no respondió”.
- No recalcular retroactivamente audiencias ya congeladas sin un contrato explícito.

## 9. Interacciones

Campaign Analytics devolvió `interactions` a nivel agregado, pero M8 todavía no ha demostrado una lista individual de teléfonos/destinatarios asociada a esas interacciones.

Por tanto:

- conservar `interactions` como capability agregada observada;
- no persistir interacciones recipient-level sin evidencia individual;
- no convertir `INTERACTED` en sustituto de `VIEWED`;
- si posteriormente se observa una relación individual 0..N, documentar el payload real y recién entonces modelarla.

## 10. Respondidos

El array `answeredMessages` del contrato anterior queda **NO OBSERVADO** y no puede usarse como fuente individual.

Sí se observó un caso real donde:

    inbound.quotedMsgId == outbound.messageApiId

Esto constituye evidencia positiva de que ese inbound referencia/responde a **ese outbound concreto**.

Reglas:

- puede registrarse conceptualmente una evidencia positiva de reply cuando exista esa correlación inequívoca;
- la ausencia de `quotedMsgId` o de una coincidencia no significa “no respondió”;
- no implementar `NO_RESPONDIÓ` por destinatario;
- un conteo agregado de responders puede conservarse como agregado si el payload real lo soporta, sin inventar la lista individual.

## 11. Timestamps individuales

La frontera GraphQL observada expone campos como `createdAt` y `seenAt`, pero M8 todavía no ha demostrado que su semántica equivalga a:

- `sent_at`;
- `delivered_at`;
- `viewed_at`;
- `replied_at`.

Por tanto no reinterpretar `createdAt`, `seenAt`, hora de sync, hora de campaña ni hora aproximada como timestamps de delivery.

Solo podrán normalizarse timestamps de evento cuando exista evidencia adicional de su significado provider.

Metadata propia de Suite como `first_seen_at_in_suite` o `last_synced_at` puede existir más adelante si se nombra claramente y no se confunde con un evento WhatsApp.

## 12. campaign_id externo

Campañas V2 debe tener identidad propia y referencia externa.

Conceptualmente:

    campaign_v2.id
    provider = IVENTAS
    provider_campaign_id = <id>

Debe existir una unique constraint adecuada para evitar duplicar la misma campaña externa.

No usar el campaign_id de iVentas como PK interna de Suite.

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

La frontera Campaign Analytics observada requiere `campaignId + companyId`; la frontera GraphQL observada permite recorrer mensajes de un `Client.id`, pero eso no constituye un listado de campañas.

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

La evidencia actual permite investigar retroactividad por dos vías independientes:

- Campaign Analytics por `campaignId + companyId`;
- historial GraphQL por `Client.id` y paginación de mensajes.

Un backfill futuro solo queda autorizado para capacidades read-only realmente accesibles con credencial backend y con payload real documentado.

No asumir que consultar historial por teléfono reconstruye automáticamente una campaña. El backfill no debe crear correlaciones campaña->mensaje ni simular timestamps que no existan.

## 16. Costos por campaña

Campaign Analytics observado incluye `costs` y datos de costo real/provisional, pero el shape exacto todavía no está congelado contractualmente.

Antes de programar parser:
1. obtener un payload real sanitizado desde la frontera Campaign Analytics observada;
2. documentar exactamente los campos usados;
3. escribir fixture;
4. implementar parser tolerante a campos extra;
5. mantener `cost unavailable/unknown` cuando la frontera o la credencial no permita obtenerlo.

Prohibido inventar rutas internas del objeto `costs` sin ver y congelar el payload real.

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

Fase 2 podrá añadir filtros por campaña como `SENT`, `DELIVERED`, `VIEWED`, `FAILED` o `INTERACTED` **solo después** de demostrar y persistir correctamente la relación:

    Campaign V2 recipient
      -> outbound provider message
      -> estado/interacción observada

Mientras esa correlación siga abierta, el historial GraphQL por teléfono puede informar comportamiento provider general, pero no debe presentarse como estado de una campaña concreta.

No ofrecer `NO_RESPONDIDO` hasta tener dato individual confiable.

## 21. Persistencia conceptual

La implementación futura puede variar, pero debe separar como mínimo. **M8 no autoriza todavía crear esta persistencia; recipient delivery e interactions quedan bloqueados hasta resolver la correlación campaña->outbound:**

### Provider campaign binding
- campaign_v2_id opcional;
- provider;
- provider_campaign_id;
- external origin;
- last_synced_at;
- analytics_status.

### Recipient delivery state
- campaign/provider campaign;
- phone canonical;
- successful;
- failed;
- sent;
- delivered;
- viewed;
- provider error/cause;
- last_synced_at.

### Interactions
- recipient;
- label;
- provider metadata;
- first_seen_at / last_seen_at si se necesita idempotencia.

### Analytics snapshot o campos normalizados
- solo campos realmente utilizados;
- payload raw/sanitizado opcional si la política de datos lo permite;
- costo;
- moneda;
- status.

No crear una mega-columna JSON como sustituto de todo si después se necesitan filtros frecuentes. Tampoco normalizar campos no usados por anticipado.

## 22. Idempotencia

Repetir sync de una campaña no debe duplicar nada.

El patrón final dependerá de la capability:

    campaign aggregate analytics
      -> fetch
      -> normalize
      -> upsert campaign binding/analytics cuando esté autorizado

    recipient/message history
      -> fetch read-only
      -> normalize evidencia histórica
      -> NO convertir en campaign-recipient hasta resolver correlación

No borrar estado más avanzado porque una respuesta transitoria venga incompleta.

Definir explícitamente reglas de monotonicidad solo cuando el proveedor las garantice; no asumirlas si no están documentadas.

## 23. Rate limits y retries

El adaptador debe respetar límites documentados por iVentas.

La estrategia debe:
- limitar concurrencia;
- usar retry solo para errores transitorios;
- respetar Retry-After cuando exista;
- registrar supportRef/error sanitizado;
- nunca convertir 5xx en cero.

No meter requests largos dentro del backend web si terminan bloqueando workers. Para backfills grandes evaluar job separado/scheduler siguiendo la arquitectura ya usada por Warehouse/Track.

## 24. Seguridad

Toda credencial iVentas:
- backend only;
- env/secret;
- nunca persistida en DB;
- nunca enviada a Angular;
- nunca registrada completa.

No asumir que `IVENTAS_API_TOKEN` de la integración REST existente funciona también contra GraphQL o Campaign Analytics. Esa compatibilidad debe probarse read-only de forma aislada.

GraphQL HTTP POST está permitido únicamente para operaciones `query` read-only. `mutation` está prohibida en M8.

La credencial compartida durante análisis debe rotarse antes de considerarse integración productiva final.

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

Capacidades equivalentes futuras, separadas:

- attach provider campaign id;
- read campaign aggregate analytics;
- resolve provider client/conversation by phone;
- read recipient message history;
- update commercial purpose;
- list imported/external campaigns;
- sync period cuando exista capability de listado confirmada;
- read campaign-recipient delivery **solo cuando exista correlación demostrada campaña->outbound**.

Los nombres definitivos se acuerdan al implementar.

## 29. Pruebas mínimas

M8, antes de implementación:

- validar de forma aislada si la credencial backend existente accede al GraphQL HTTP observado;
- validar por separado la credencial necesaria para Campaign Analytics si difiere;
- no ejecutar mutations;
- no ejecutar `POST /v2/broadcast`.

Cuando exista implementación basada en payloads reales:

Campaign aggregate analytics:
- payload real sanitizado;
- campos usados documentados;
- costos solo según shape observado;
- campos extra ignorados;
- payload incompleto controlado.

Recipient/message history:
- phone -> Client.id;
- paginación `skip`;
- outbound con `messageStatus`;
- inbound `sender == CLIENT` con `messageStatus = null` sin convertirlo en delivery;
- quote positivo `quotedMsgId == outbound.messageApiId`;
- ausencia de quote no produce `NO_RESPONDIDO`;
- timestamps no reinterpretados sin evidencia.

Correlación campaign-recipient:
- permanece bloqueada hasta encontrar evidencia provider suficiente;
- cuando exista, deberá probar pertenencia del outbound a una campaña concreta antes de persistir `sent/delivered/viewed/failed` por número y campaña.

Seguridad:
- token no aparece en logs/response;
- errores sanitizados;
- ninguna mutation/envío en pruebas M8.

## 30. Criterio de aceptación de Fase 2

Fase 2 debe poder representar correctamente las dos capacidades independientes observadas:

### Campaign aggregate analytics

Dada una campaña real conocida y accesible, Suite debe poder mostrar/persistir únicamente campos soportados por payload real, incluyendo cuando aplique:

- identidad/provider_campaign_id;
- analytics agregados;
- funnel/rates agregados;
- failures agregados;
- interactions agregadas;
- costo/moneda según shape congelado;
- fecha de última sincronización;
- propósito comercial.

### Recipient/message historical status

Dado un teléfono accesible por la frontera provider:

- resolver `Client.id`;
- recorrer historial de mensajes;
- distinguir inbound/outbound según evidencia observada;
- conservar `messageStatus` y errores provider sin inventar delivery;
- reconocer evidencia positiva de reply cuando exista correlación `quotedMsgId -> messageApiId`;
- no fabricar “no respondió” ni timestamps de delivery.

### Bloqueo explícito

El criterio original:

    saber qué números de una campaña pertenecen a
    sent / delivered / viewed / failed

**permanece pendiente**.

No se considera satisfecho hasta demostrar:

    Campaign V2 recipient
      -> outbound provider message
      -> estado individual

No es requisito todavía enviar desde Suite.

## 31. Condición de salida hacia Fase 3

No iniciar Fase 3 hasta que:
- provider abstraction sea estable;
- Campaign aggregate analytics reales estén validados con payload sanitizado;
- recipient/message history real esté validado con credencial backend;
- la correlación `Campaign V2 recipient -> outbound provider message` esté demostrada;
- `sent/delivered/viewed/failed` por número y campaña puedan derivarse sin especulación;
- costos reales estén parseados con fixture si la capability los expone;
- sync sea idempotente para cada capability implementada;
- campañas externas puedan representarse;
- branch resolution funcione cuando aplique;
- secretos estén fuera del código;
- legacy no se haya roto;
- `FUNNEL_PORTFOLIO` funcione con recipients phone-only;
- la cartera Funnel reutilice la semántica vigente de compradores/no compradores;
- la cartera Funnel excluya por número a quienes aparezcan en el snapshot canónico vigente de Socios Activos y reporte `ACTIVE_MEMBER_SUPPRESSION`;
- los flags iVentas, cuando puedan atribuirse, estén ligados a campaña-recipient y no a las bases canónicas.

## 32. Instrucción de arranque recomendada para una conversación nueva de Fase 2

    Estamos implementando únicamente Campañas V2 Fase 2.
    Este archivo es autosuficiente; no asumas contexto de conversaciones anteriores.
    Confirma en el repositorio que Fase 1 está terminada.
    Inspecciona la integración iVentas existente y reutiliza normalización,
    aliases, seguridad y patrones de persistencia.
    No implementes POST /v2/broadcast ni GraphQL mutations.
    Trata Campaign aggregate analytics y Recipient/message history como capabilities independientes.
    Considera /v2/broadcast/stats/:id y sus arrays como NO OBSERVADOS hasta nueva evidencia.
    Antes de modelar analytics/costo, obtén un payload real sanitizado.
    No persistir delivery por campaign-recipient hasta demostrar campaign -> outbound provider message.
    Propón un solo cambio mínimo y su prueba.
