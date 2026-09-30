# Contrato Campañas V2 — Fase 2

Estado: CONTRATO DE LECTURA/BI; NO AUTORIZA ENVÍO  
Dependencia: Fase 1 terminada y estable  
Objetivo: integrar resultados de campañas iVentas con Campañas V2 sin acoplar el núcleo al proveedor.

## 1. Alcance exacto

Fase 2 agrega lectura y sincronización de campañas iVentas.

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
- realizar sincronizaciones idempotentes.

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

## 4. Provider abstraction

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

## 5. Capacidades conocidas de iVentas

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

## 6. Estado por destinatario

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

## 7. Interacciones

interactions devuelve:
- label del botón;
- items con destinatarios.

Persistir interacción separada del delivery.

Ejemplo:

    delivery_status = VIEWED
    interaction = "Me interesa"

No convertir INTERACTED en sustituto de VIEWED.

Si un destinatario puede tocar más de un botón, el modelo debe soportar 0..N interacciones.

## 8. Respondidos

La documentación actual indica que answeredMessages está reservado y actualmente vacío.

Por lo tanto Fase 2 no puede implementar:

    RESPONDIÓ
    NO RESPONDIÓ

por destinatario basándose en ese campo.

Si analytics presenta un conteo agregado de responded, conservarlo como agregado únicamente mientras no exista lista de números.

Para habilitar filtro por respuesta individual se requiere evidencia/API explícita.

## 9. Timestamps individuales

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

## 10. campaign_id externo

Campañas V2 debe tener identidad propia y referencia externa.

Conceptualmente:

    campaign_v2.id
    provider = IVENTAS
    provider_campaign_id = <id>

Debe existir una unique constraint adecuada para evitar duplicar la misma campaña externa.

No usar el campaign_id de iVentas como PK interna de Suite.

## 11. Campañas creadas fuera de Suite

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

## 12. Descubrimiento histórico por periodo

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

## 13. Retroactividad

No hay restricción documentada que prohíba consultar stats de una campaña histórica existente y autorizada.

Por tanto el contrato permite backfill retroactivo de septiembre u otros periodos siempre que:
- se conozca provider_campaign_id;
- la API todavía exponga la campaña;
- la credencial tenga acceso.

El backfill debe guardar la cohorte/resultado observado, no simular timestamps que no existan.

## 14. Costos por campaña

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

## 15. Conciliación de costos

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

## 16. Clasificación comercial histórica

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

## 17. Drill-down de clasificación

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

## 18. Estados iVentas como filtro de futuras audiencias

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

## 19. Persistencia conceptual

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

## 20. Idempotencia

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

## 21. Rate limits y retries

El adaptador debe respetar límites documentados por iVentas.

La estrategia debe:
- limitar concurrencia;
- usar retry solo para errores transitorios;
- respetar Retry-After cuando exista;
- registrar supportRef/error sanitizado;
- nunca convertir 5xx en cero.

No meter requests largos dentro del backend web si terminan bloqueando workers. Para backfills grandes evaluar job separado/scheduler siguiendo la arquitectura ya usada por Warehouse/Track.

## 22. Seguridad

La integration key:
- backend only;
- env/secret;
- nunca persistida en DB;
- nunca enviada a Angular;
- nunca registrada completa.

La credencial compartida durante análisis debe rotarse antes de considerarse integración productiva final.

## 23. Sucursal y branch

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

## 24. Relación con Funnel

Venta nueva puede usar costos de campañas clasificadas NEW_SALE.

No mezclar:
- ventas/reactivaciones;
- leads;
- socios activos.

Fase 2 entrega datos de campaña para que Funnel los consuma posteriormente mediante interfaces explícitas.

No modificar el KPI del Funnel en el mismo cambio que implementa el sync si no existe un contrato separado de cálculo.

## 25. Relación con Reactivaciones

Una campaña clasificada REACTIVATION puede cruzarse con el motor de outcomes existente.

Primero investigar adaptación; no duplicar:
- last-touch;
- ventana;
- resolución de socios activos;
- outcomes terminales.

La conexión del nuevo campaign model al motor legacy puede requerir una interfaz común. Debe ser un cambio separado y probado.

## 26. API interna esperada

Operaciones equivalentes:

- attach provider campaign id;
- sync one campaign;
- read campaign delivery;
- read campaign interactions;
- update commercial purpose;
- list imported/external campaigns;
- sync period cuando capability list_campaigns exista.

Los nombres definitivos se acuerdan al implementar.

## 27. Pruebas mínimas

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

## 28. Criterio de aceptación de Fase 2

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

## 29. Condición de salida hacia Fase 3

No iniciar Fase 3 hasta que:
- provider abstraction sea estable;
- stats reales estén validados;
- costos reales estén parseados con fixture;
- sync sea idempotente;
- campañas externas puedan representarse;
- branch resolution funcione;
- secretos estén fuera del código;
- legacy no se haya roto.

## 30. Instrucción para una conversación nueva de Fase 2

    Estamos implementando únicamente Campañas V2 Fase 2.
    Lee el contrato global, Fase 1 y este contrato.
    Confirma que Fase 1 está terminada.
    Inspecciona la integración iVentas existente y reutiliza normalización,
    aliases, seguridad y patrones de persistencia.
    No implementes POST /v2/broadcast.
    Antes de modelar analytics/costo, obtén un payload real sanitizado.
    Propón un solo cambio mínimo y su prueba.
