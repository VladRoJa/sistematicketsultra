# Contrato Campañas V2 — Fase 2

Estado: CONTRATO DE LECTURA/BI; NO AUTORIZA ENVÍO  
Dependencia: Fase 1 terminada y estable  
Objetivo: integrar resultados de campañas iVentas con Campañas V2 sin acoplar el núcleo al proveedor e incorporar, antes del enviador, la Cartera Funnel de Venta Nueva como fuente phone-centric.

## 1. Alcance exacto

Fase 2 contiene dos bloques que deben quedar listos antes de Fase 3:

- **2A — iVentas lectura/BI:** lectura y sincronización de campañas.
- **2B — Cartera Funnel:** fuente de audiencia para Venta Nueva/Funnel, tolerante a identidad incompleta.

Debe permitir:

- asociar una campaña V2 con un campaign_id de iVentas;
- importar campañas creadas directamente en iVentas cuando exista forma de descubrirlas;
- consultar estadísticas de una campaña;
- persistir estados por destinatario;
- persistir interacciones;
- persistir analytics relevantes;
- persistir costo de campaña cuando el proveedor lo entregue;
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

La API nueva de broadcast stats representa una campaña concreta y sus destinatarios/estados.

No mezclar ambas cosas.

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

Los flags de iVentas se guardan en el recipient/delivery de **esa campaña**:

    successful
    sent
    delivered
    viewed
    failed
    interactions

Nunca agregarlos como estado global a las bases canónicas. El mismo socio/teléfono puede tener resultados distintos en campañas distintas.

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

## 6. Provider abstraction

Fase 2 debe introducir o completar una abstracción de proveedor.

Interfaz conceptual:

    CampaignProvider
        get_campaign_stats(provider_campaign_id)
        get_campaign_cost(provider_campaign_id)
        list_campaigns(period)          # opcional por capability
        get_recipient_events(id)        # opcional
        capabilities()

Implementación inicial:

    IVentasCampaignProvider

El resto del módulo no debe conocer URLs ni nombres concretos de campos externos salvo en el adaptador.

## 7. Capacidades conocidas de iVentas

Documentación recibida:

### GET /v2/broadcast/stats/:id

Autenticación:
- integration key backend;
- scope read:campaign-stats.

La respuesta base documenta listas:

- successfulMessages
- failedMessages
- sentMessages
- deliveredMessages
- viewedMessages
- answeredMessages
- interactions

Con integration key también:
- analytics
- analyticsStatus

Estados analyticsStatus documentados:
- ok
- not_synced
- unavailable
- disabled

Regla:
- solo ok autoriza usar analytics;
- not_synced NO significa cero;
- unavailable NO significa cero;
- disabled NO significa cero.

## 8. Estado por destinatario
Los arrays de estado no son mutuamente excluyentes.

Un número puede aparecer en:
- successful;
- sent;
- delivered;
- viewed.

Persistir flags independientes o eventos normalizados según el diseño final.

La UI puede mostrar estado más avanzado conocido:

    VIEWED
      ↑
    DELIVERED
      ↑
    SENT

FAILED debe conservarse con su error/cause cuando esté disponible; no convertirlo automáticamente en una etapa secuencial.

## 9. Interacciones

interactions devuelve:
- label del botón;
- items con destinatarios.

Persistir interacción separada del delivery.

Ejemplo:

    delivery_status = VIEWED
    interaction = "Me interesa"

No convertir INTERACTED en sustituto de VIEWED.

Si un destinatario puede tocar más de un botón, el modelo debe soportar 0..N interacciones.

## 10. Respondidos

La documentación actual indica que answeredMessages está reservado y actualmente vacío.

Por lo tanto Fase 2 no puede implementar:

    RESPONDIÓ
    NO RESPONDIÓ

por destinatario basándose en ese campo.

Si analytics presenta un conteo agregado de responded, conservarlo como agregado únicamente mientras no exista lista de números.

Para habilitar filtro por respuesta individual se requiere evidencia/API explícita.

## 11. Timestamps individuales

Actualmente el contrato recibido no garantiza:

- sent_at por destinatario;
- delivered_at;
- viewed_at;
- replied_at.

No crear columnas llenas con:
- hora de sync;
- hora de campaña;
- hora aproximada

fingiendo que son timestamps del evento.

Puede persistirse:
- first_seen_at_in_suite;
- last_synced_at

si se nombran claramente como metadata de Suite, no como evento WhatsApp.

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

Con la documentación actual, GET /v2/broadcast/stats/:id consulta una campaña por vez y no tiene query params.

Esto no impide backfill si conocemos los IDs.

El punto pendiente es descubrir todos los IDs de un periodo.

Fase 2 debe manejar dos caminos:

### Camino A — endpoint de listado disponible

Si iVentas libera una consulta por periodo:
1. listar campañas del periodo;
2. upsert metadata;
3. ejecutar stats por campaign_id;
4. persistir resultados;
5. marcar sync final.

### Camino B — IDs provistos externamente

Si todavía no existe listado, permitir un mecanismo administrativo controlado para registrar/importar IDs conocidos, sin enviar campañas.

No inventar scraping del panel ni consultar MongoDB de iVentas.

## 15. Retroactividad

No hay restricción documentada que prohíba consultar stats de una campaña histórica existente y autorizada.

Por tanto el contrato permite backfill retroactivo de septiembre u otros periodos siempre que:
- se conozca provider_campaign_id;
- la API todavía exponga la campaña;
- la credencial tenga acceso.

El backfill debe guardar la cohorte/resultado observado, no simular timestamps que no existan.

## 16. Costos por campaña

iVentas indicó que analytics incluye costo de campaña y que el envío almacena totalCost según país, categoría y fecha de envío.

Sin embargo, el shape exacto de analytics no está congelado en la documentación.

Antes de programar parser:
1. ejecutar GET stats contra una campaña real;
2. guardar/inspeccionar un payload sanitizado;
3. documentar campos usados;
4. escribir fixture;
5. implementar parser tolerante a campos extra.

Prohibido inventar rutas como:

    analytics.cost.total

sin ver el payload real.

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

Una vez persistidos, Fase 2 puede añadir a Campañas V2 filtros como:

- SENT
- DELIVERED
- VIEWED
- FAILED
- INTERACTED

Estos filtros se aplican sobre una campaña anterior elegida.

Ejemplo:

    source = previous_campaign
    family in (DOMICILIADO, TRIMESTRAL)
    AND viewed = true
    AND interacted = false

No ofrecer NO_RESPONDIDO hasta tener dato individual confiable.

## 21. Persistencia conceptual

La implementación puede variar, pero debe separar como mínimo:

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

Patrón:

    fetch
      -> normalize
      -> upsert campaign binding
      -> upsert recipients
      -> upsert interactions
      -> upsert analytics/cost
      -> set last_synced_at

No borrar estado más avanzado porque una respuesta transitoria venga incompleta.

Definir explícitamente reglas de monotonicidad cuando el proveedor las garantice; no asumirlas si no están documentadas.

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

La integration key:
- backend only;
- env/secret;
- nunca persistida en DB;
- nunca enviada a Angular;
- nunca registrada completa.

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

Operaciones equivalentes:

- attach provider campaign id;
- sync one campaign;
- read campaign delivery;
- read campaign interactions;
- update commercial purpose;
- list imported/external campaigns;
- sync period cuando capability list_campaigns exista.

Los nombres definitivos se acuerdan al implementar.

## 29. Pruebas mínimas

Provider parser:
- successful;
- failed;
- sent;
- delivered;
- viewed;
- interactions;
- analyticsStatus ok;
- not_synced;
- unavailable;
- campos extra ignorados;
- payload incompleto controlado.

Persistencia:
- idempotencia;
- no duplicar recipient;
- no duplicar interaction;
- unique provider campaign;
- manual classification survives resync.

Seguridad:
- token no aparece en logs/response;
- branch fuera de scope rechazado;
- campaign fuera de scope manejado como provider error.

Histórico:
- importar ID histórico;
- sincronizar;
- volver a sincronizar;
- mismos registros.

## 30. Criterio de aceptación de Fase 2

Dada una campaña real conocida de iVentas, Suite debe poder mostrar:

- nombre/identidad de campaña;
- provider_campaign_id;
- sucursal si se puede resolver;
- destinatarios;
- sent;
- delivered;
- viewed;
- failed;
- interacciones;
- analytics status;
- costo si el payload real lo soporta;
- propósito comercial;
- fecha de última sincronización.

Debe poder abrirse el detalle y saber qué números pertenecen a cada estado soportado.

Debe poder cambiarse propósito comercial manualmente.

No es requisito todavía enviar desde Suite.

## 31. Condición de salida hacia Fase 3

No iniciar Fase 3 hasta que:
- provider abstraction sea estable;
- stats reales estén validados;
- costos reales estén parseados con fixture;
- sync sea idempotente;
- campañas externas puedan representarse;
- branch resolution funcione;
- secretos estén fuera del código;
- legacy no se haya roto;
- `FUNNEL_PORTFOLIO` funcione con recipients phone-only;
- la cartera Funnel reutilice la semántica vigente de compradores/no compradores;
- los flags iVentas estén ligados a campaña-recipient y no a las bases canónicas.

## 32. Instrucción para una conversación nueva de Fase 2

    Estamos implementando únicamente Campañas V2 Fase 2.
    Lee el contrato global, Fase 1 y este contrato.
    Confirma que Fase 1 está terminada.
    Inspecciona la integración iVentas existente y reutiliza normalización,
    aliases, seguridad y patrones de persistencia.
    No implementes POST /v2/broadcast.
    Antes de modelar analytics/costo, obtén un payload real sanitizado.
    Propón un solo cambio mínimo y su prueba.
