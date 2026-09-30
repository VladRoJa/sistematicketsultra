# Contrato Campañas V2 — Fase 3

Estado: CONTRATO DE ENVÍO; REQUIERE FASES 1 Y 2 ESTABLES  
Dependencia de ejecución: Fase 1 y Fase 2 terminadas, incluida la fuente FUNNEL_PORTFOLIO; este archivo es autosuficiente como contexto.  
Objetivo: permitir que Suite Ultra envíe campañas mediante iVentas sin romper la trazabilidad construida previamente.

## 0. Contexto autosuficiente para una conversación nueva

Este archivo puede entregarse **por sí solo** a una conversación nueva, pero Fase 3 solo puede comenzar después de comprobar en el repositorio que Fase 1 y Fase 2 están terminadas.

Contexto fijo:

- Suite Ultra usa Angular + Flask + PostgreSQL y Alembic.
- Fase 1 construye y congela audiencias.
- Fase 2 sincroniza iVentas, conserva estados por campaign-recipient, deriva comportamiento histórico por teléfono e incorpora \`FUNNEL_PORTFOLIO\`.
- Funnel debe haber aplicado la lógica vigente de compradores/no compradores y \`ACTIVE_MEMBER_SUPPRESSION\` contra Socios Activos antes de congelar la audiencia.
- Fase 3 **no recalcula fuentes, familias, compras, socios activos ni historial de engagement**: envía exactamente la audiencia congelada y validada.
- No crear tablas espejo de Socios Activos/Vencidos.
- No crear un tercer normalizador de teléfonos ni un mapping duplicado de sucursales/canales.
- Un Campaign V2 puede requerir N provider campaigns porque iVentas envía por \`channelId\`.
- Backend es autoridad para permisos, channel binding, plantilla, variables e idempotencia.
- No retirar el legacy dentro de esta fase.

Modo de trabajo:

1. inspeccionar \`main\` y confirmar que Fase 1/Fase 2 están completas;
2. revisar provider abstraction, delivery y mappings existentes;
3. explicar un solo cambio mínimo y prueba;
4. probar primero un flujo controlado;
5. no mezclar en el mismo cambio rediseños del constructor de audiencia.

## 1. Alcance exacto

Fase 3 agrega envío de campañas desde Suite.

Debe permitir:

- seleccionar plantilla aprobada;
- seleccionar sucursal/canal válido;
- construir variables por destinatario;
- validar audiencia congelada;
- enviar inmediatamente o programar;
- llamar POST /v2/broadcast;
- guardar el campaign_id devuelto por iVentas;
- enlazar ese ID con la campaña V2;
- habilitar sincronización posterior usando Fase 2;
- manejar errores/reintentos de forma segura;
- mantener auditoría de quién envió, cuándo y con qué configuración.

Fase 3 NO debe:

- rehacer el constructor de audiencias;
- recalcular una audiencia al momento de enviar;
- meter credenciales en frontend;
- saltarse permisos backend;
- borrar el legacy automáticamente;
- duplicar branch resolution ya existente.

## 2. API iVentas conocida

Endpoint:

    POST https://rest.iventas.mx/v2/broadcast

Autenticación:

    Authorization: Bearer <integration key>

La integration key entregada a Ultra tiene, según documentación recibida:

- send:campaigns
- read:campaign-stats

El request soporta, entre otros:

- templateName;
- leads;
- channelId;
- token legacy;
- fileUrl;
- name;
- sendAt;
- tag;
- tagId;
- type;
- phonesToNotify;
- actions;
- botIntents.

Fase 3 debe usar el flujo moderno con integration key y channelId, no el legacy static token, salvo decisión explícita posterior.

## 3. Respuesta de creación

Respuesta exitosa:

    {
      "campaign": "<provider campaign id>"
    }

Puede aparecer:

    deduplicated = true

en ciertos escenarios programados.

Regla:
- provider_campaign_id debe persistirse inmediatamente después de una creación exitosa;
- no marcar campaña como enviada antes de tener confirmación válida del proveedor;
- si la respuesta es ambigua/error, no inventar campaign_id.

## 4. Reutilización obligatoria del repo

Antes de implementar, inspeccionar main actual y reutilizar cuando aplique:

- backend/app/services/marketing_iventas_service.py
- backend/app/services/marketing_iventas_branch_service.py
- backend/app/services/marketing_campaign_delivery_service.py
- backend/app/models/marketing_campaign_delivery.py
- backend/app/services/marketing_campaign_export_service.py
- backend/app/services/marketing_reactivation_outcome_service.py
- infraestructura de permisos de Marketing;
- scheduler/job patterns existentes si se requieren envíos diferidos o retries.

No crear otro normalizador de teléfono ni otro mapa branch -> sucursal.

## 5. Audiencia inmutable al enviar

El envío usa exclusivamente la audiencia congelada de la campaña V2.

Está prohibido:

- volver a consultar socios activos;
- volver a consultar socios vencidos;
- volver a ejecutar el Funnel;
- recalcular familias;
- agregar o quitar destinatarios silenciosamente

en el momento del POST.

Si el usuario necesita cambiar audiencia:
- crear nueva versión/campaña según política que se defina;
- no mutar una cohorte ya aprobada/enviada sin trazabilidad.

## 6. Validación pre-envío

Antes de llamar iVentas, backend debe validar:

- campaña existe;
- usuario tiene permiso;
- campaña está en estado permitido;
- audiencia no está vacía;
- todos los recipients sendables tienen teléfono normalizado;
- sucursal/canal o política de dispatch está resuelta explícitamente;
- recipients `PHONE_ONLY` sin dispatch resoluble están bloqueados y visibles, no reasignados arbitrariamente;
- plantilla está definida;
- variables requeridas pueden construirse;
- provider binding no indica envío previo;
- no existe operación concurrente incompatible.

La UI debe mostrar preview final de envío, pero backend vuelve a validar todo.

## 7. Plantilla WhatsApp

Plantilla WhatsApp es independiente de audience_family.

Ejemplo:

    purpose = REACTIVATION
    families = DOMICILIADO + TRIMESTRAL
    whatsapp_template = reactivacion_octubre_v2

No asumir que cada familia siempre corresponde a una sola plantilla.

El catálogo de plantillas deberá representar al menos:

- provider;
- templateName;
- label de negocio;
- estado activo;
- uso comercial;
- metadata de variables requeridas si se conoce;
- compatibilidad por canal/sucursal si aplica.

No duplicar templates hardcodeados en Angular.

## 8. Obtención/listado de plantillas

La documentación recibida describe cómo enviar templateName, pero no incluye en este contrato un endpoint confirmado para listar plantillas aprobadas.

Por lo tanto hay dos caminos permitidos:

### Camino A — API de templates confirmada

Si iVentas entrega endpoint de catálogo:
- crear capability;
- sincronizar/cachear;
- no hardcodear.

### Camino B — catálogo administrado en Suite

Mientras no exista API:
- mantener catálogo backend/DB controlado;
- carga/edición por rol autorizado;
- validar templateName por proveedor/canal tanto como sea posible.

No inventar endpoint de templates.

## 9. Channel binding

La documentación de iVentas exige channelId para integration keys salvo flujo opcional alterno.

Suite ya puede resolver branch iVentas -> sucursal Suite mediante aliases, pero eso no garantiza que exista una tabla canónica de channelId actual para envío.

Antes de crear una nueva entidad, investigar:
- MarketingIventasContactORM.channel_id observado;
- si ese channel_id es estable y suficiente por sucursal;
- si existe más de un canal activo;
- si iVentas entrega un catálogo oficial.

### Regla de diseño

No hardcodear channelId en un service ni en Angular.

Si no existe una fuente canónica estable, es pertinente crear una configuración/binding de proveedor, por ejemplo conceptualmente:

    provider
    sucursal_id
    provider_branch_code
    provider_channel_id
    is_active
    valid_from
    valid_to / metadata

La entidad exacta se define en implementación.

El caso Tecnológico debe respetar la migración/alias actual que dejó tecnologico-2 como canal/código activo hacia TEC_MXL.

## 10. Variables por destinatario

Cada lead iVentas puede incluir:

- phone;
- vars[];
- urlVars[].

La construcción de variables pertenece al backend.

Debe existir contrato por plantilla:

    variable 1 -> nombre
    variable 2 -> fecha
    variable 3 -> monto

o equivalente.

No montar arrays de vars manualmente en componentes Angular.

Si falta una variable obligatoria:
- bloquear pre-envío;
- mostrar error comprensible;
- no mandar una campaña parcialmente mal formada por default.

## 11. Media

fileUrl puede adjuntar media según tipos soportados por proveedor.

No implementar soporte de archivos en el primer cambio de Fase 3 salvo necesidad real.

Si se implementa:
- URL accesible por iVentas;
- archivo permitido;
- seguridad;
- expiración;
- trazabilidad.

No reutilizar URLs temporales de Warehouse sin comprobar que el proveedor pueda accederlas.

## 12. Programación sendAt

Sin sendAt:
- envío inmediato según contrato iVentas.

Con sendAt:
- campaña programada.

Suite debe decidir timezone de UX y convertir de manera explícita al formato esperado por proveedor.

No mezclar America/Tijuana con America/Mexico_City por inferencia.

La UI muestra hora local de negocio; backend persiste:
- valor local/origen;
- valor enviado al proveedor;
- timezone usado.

## 13. Deduplicación del proveedor

iVentas documenta protección de duplicados para campañas programadas dentro de una ventana corta.

Esto NO sustituye idempotencia de Suite.

Suite debe crear su propia llave/idempotency state conceptual para impedir doble click/doble request concurrente.

Escenarios:
- primer request éxito;
- retry por timeout;
- proveedor devuelve deduplicated;
- error antes de persistir provider_campaign_id.

Cada escenario debe tener prueba.

## 14. Estados internos de campaña

Los estados exactos se definirán al implementar, pero deben distinguir al menos:

- DRAFT;
- READY;
- SENDING / SUBMITTING;
- SCHEDULED;
- SENT / SUBMITTED;
- FAILED / PROVIDER_ERROR;
- CANCELLED cuando aplique.

No reutilizar sin análisis los estados DRAFT/EXPORTED/SENT/CANCELLED de MarketingReactivationCampaignORM porque su semántica está ligada al legacy de exportación manual.

## 15. Registro de envío por sucursal

El legacy ya tiene:

    MarketingReactivationCampaignBranchSendORM
    marketing_campaign_delivery_service.py

Fase 3 debe investigar si:
- se puede extraer un modelo/servicio común de delivery;
- o V2 necesita persistencia propia.

No duplicar “sent_at por sucursal” si una abstracción común resuelve ambos modelos sin romper legacy.

Si V2 puede contener más de una sucursal en una campaña, el diseño debe reflejar cardinalidad real del proveedor:
- una llamada por channelId/sucursal;
- o varias provider campaigns ligadas a una campaña lógica Suite.

Esto debe confirmarse antes de asumir que una campaña V2 = un solo campaign_id externo.

## 16. Punto crítico: campaña multísucursal

POST /v2/broadcast recibe un channelId.

Eso implica que una audiencia con múltiples sucursales probablemente requiera:
- dividir por sucursal/canal;
- crear un broadcast por cada canal;
- almacenar varios provider_campaign_id bajo una campaña lógica Suite.

Por lo tanto el modelo V2 debe soportar conceptualmente:

    Campaign V2
        1
        |
        N ProviderCampaign

Cada ProviderCampaign:
- sucursal;
- provider;
- channel;
- provider_campaign_id;
- send status;
- cost/stats propios.

No modelar provider_campaign_id directamente como único campo en campaign_v2 si eso impide multísucursal.

Esta regla debe revisarse en Fase 2 también al importar históricos.

## 17. Resultado del envío y Fase 2

Después de crear provider campaigns:

1. persistir IDs;
2. registrar estado de submit;
3. no esperar analytics sincrónicamente;
4. Fase 2 consulta stats;
5. si analyticsStatus = not_synced, mostrar pendiente;
6. reintentar de forma controlada.

No bloquear un request web durante minutos esperando analytics.

## 18. Programación y background jobs

Si Suite programa mediante sendAt, el proveedor se encarga del horario de envío.

Si Suite necesita:
- sync posterior;
- retries;
- backfill;

usar jobs separados cuando la duración pueda comprometer Gunicorn.

No crear loops infinitos dentro del proceso web.

Seguir patrones de scheduler/jobs existentes y limpiar db.session por ciclo cuando aplique.

## 19. Errores de iVentas

El endpoint documenta errores como:
- FORBIDDEN;
- INVALID_CHANNEL_TOKEN;
- MISSING_CHANNEL;
- TEMPLATE_NOT_FOUND;
- DUPLICATE_BROADCAST_IN_PROGRESS;
- errores internos con supportRef.

Reglas:
- conservar código y supportRef sanitizado;
- no exponer secretos;
- errores 4xx de configuración no se reintentan ciegamente;
- errores transitorios pueden reintentarse de forma limitada;
- un 500 no significa “no se envió” ni “sí se envió”: debe quedar estado de conciliación si el resultado es incierto.

## 20. Observabilidad

Registrar:
- campaign_v2_id;
- provider campaign binding id;
- sucursal_id;
- provider;
- operación;
- status;
- supportRef;
- duración;
- count recipients.

No registrar:
- Authorization;
- credencial;
- payload completo con datos personales si no es necesario;
- teléfonos completos en logs generales.

## 21. Permisos

Enviar campañas es una acción de mayor riesgo que consultar.

Fase 3 debe identificar un permiso explícito de envío.

Backend valida:
- usuario;
- alcance de sucursal;
- capacidad de enviar;
- acceso a plantilla/canal.

Ocultar botón en frontend no sustituye autorización.

## 22. Confirmación de envío

La UI debe requerir confirmación final con:
- nombre;
- propósito;
- sucursal(es);
- template;
- destinatarios;
- inmediato/programado;
- fecha/hora si aplica.

No mostrar el costo como exacto antes de que proveedor lo confirme, salvo que iVentas exponga una cotización explícita con semántica documentada.

## 23. Envío por varias familias

Las familias son parte de la audiencia, no lotes de envío obligatorios.

Ejemplo válido:

    DOMICILIADO + TRIMESTRAL
    -> misma plantilla
    -> misma sucursal
    -> un broadcast de ese canal

Siempre deduplicando teléfonos antes de crear leads.

## 24. Plantillas y cinco rubros

El catálogo comercial actual orienta plantillas aproximadamente a:
- Domiciliado;
- Trimestral;
- Convenio;
- Semestre;
- Estudiante.

Esto sirve para sugerir/filtrar templates, pero no debe impedir manualmente una combinación autorizada de familias si negocio decide usar una plantilla transversal.

La relación template <-> audience_family debe ser configurable, no lógica hardcodeada.

## 25. Auditoría

Persistir:
- created_by;
- approved/sent_by según flujo final;
- submitted_at;
- scheduled_for;
- provider IDs;
- template usado;
- snapshot de configuración crítica;
- resultado de submit;
- supportRef si aplica.

El template puede cambiar en iVentas en el futuro; la campaña debe conservar suficiente metadata para saber qué se intentó enviar.

## 26. Relación con costos

Después de enviar:
- Fase 2 obtiene costo real por provider campaign;
- Campaign V2 agrega costos de sus N provider campaigns.

Para una campaña multísucursal:

    campaign_total_cost
    = suma de provider_campaign costs válidos

Si un provider campaign está pendiente/unavailable:
- total debe marcarse incompleto;
- no asumir costo cero.

## 27. Pruebas mínimas

Pre-envío:
- audiencia vacía;
- phone inválido;
- template ausente;
- channel ausente;
- permiso denegado;
- sucursal fuera de alcance.

Provider:
- éxito;
- deduplicated;
- template not found;
- invalid channel;
- forbidden;
- timeout;
- 500 con supportRef.

Idempotencia:
- doble click;
- retry después de timeout;
- dos workers intentando enviar la misma campaña.

Multísucursal:
- divide por sucursal;
- N provider campaigns;
- un fallo no borra éxitos previos;
- resumen parcial claro.

Seguridad:
- credencial no aparece en frontend/logs;
- channelId no puede sustituirse arbitrariamente por request del navegador.

## 28. Criterio de aceptación de Fase 3

Debe poder ejecutarse un caso controlado:

1. crear campaña V2 desde Fase 1;
2. tener audiencia congelada;
3. seleccionar plantilla;
4. confirmar sucursal/canal;
5. enviar;
6. recibir campaign_id;
7. persistir provider campaign;
8. mostrar estado de submit;
9. ejecutar sync de Fase 2;
10. visualizar delivery/costo cuando estén disponibles.

También debe probarse un caso multísucursal si Campañas V2 permite audiencia multísucursal.

## 29. Retiro del legacy

Terminar Fase 3 NO autoriza automáticamente borrar legacy.

Antes:
- validar campañas reales;
- comparar conteos;
- validar Reactivaciones;
- validar socios activos;
- validar Venta nueva;
- confirmar exportaciones pendientes;
- definir migración/consulta histórica;
- acordar fecha de corte.

El retiro debe tener contrato/PR separado.

## 30. Instrucción de arranque recomendada para una conversación nueva de Fase 3

    Estamos implementando únicamente Campañas V2 Fase 3.
    Este archivo es autosuficiente; no asumas contexto de conversaciones anteriores.
    Confirma con pruebas en el repositorio que Fase 1 y Fase 2 están terminadas.
    Inspecciona la integración actual y reutiliza normalización,
    branch resolution, permisos, delivery y provider abstraction.
    No recalcules audiencias al enviar.
    Diseña primero el caso multísucursal porque POST /v2/broadcast usa un channelId.
    Propón un solo primer cambio mínimo y su prueba.
