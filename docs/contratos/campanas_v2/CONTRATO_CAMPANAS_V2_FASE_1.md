# Contrato Campañas V2 — Fase 1

Estado: LISTO PARA IMPLEMENTACIÓN DESPUÉS DE REVALIDAR MAIN  
Dependencia funcional: ninguna lectura adicional es necesaria para usar este archivo; se debe revalidar `main` actual.  
Objetivo: construir el núcleo de Campañas V2 y el constructor de audiencias sin depender de envío ni lectura nueva de iVentas.

## 0. Contexto autosuficiente para una conversación nueva

Este archivo puede entregarse **sin adjuntar los otros contratos**. Contiene el contexto mínimo necesario para trabajar Fase 1. Si existe una contradicción con código actual, primero se investiga el repositorio y se detiene el cambio; no se improvisa.

Contexto fijo:

- Suite Ultra usa Angular + Flask + PostgreSQL y Alembic.
- Campañas V2 es un módulo nuevo que convivirá con Reactivaciones legacy.
- Backend es autoridad de permisos, composición real de audiencia, deduplicación y persistencia.
- No se crean tablas espejo de Socios Activos ni Socios Vencidos. Se reutilizan sus fuentes canónicas.
- Una fila campaign-recipient representa pertenencia a una campaña/cohorte; **no es una segunda base maestra de socios**.
- La normalización general de teléfonos debe reutilizar \`backend/app/services/marketing_phone.py::normalize_phone()\`; el normalizador específico de iVentas se mantiene dentro de esa integración.
- Los estados iVentas pertenecen a campaña-recipient, no a las tablas fuente.
- Fase 2 agregará un resolver de comportamiento histórico por teléfono para poder filtrar, por ejemplo, "solo quienes han leído campañas anteriores". Fase 1 debe dejar el modelo preparado, pero **no implementa todavía stats iVentas**.
- Funnel/Venta Nueva se integra operativamente en Fase 2. Fase 1 solo debe evitar exigir member_id, PIN, tarifa o sucursal para todas las fuentes.
- No avanzar a Fase 2 ni Fase 3 dentro de esta conversación.

Modo de trabajo:

1. inspeccionar \`main\` actual y los archivos citados;
2. identificar qué se reutiliza y qué pieza nueva es realmente necesaria;
3. explicar archivo, función/método, objetivo y motivo;
4. hacer un solo cambio mínimo;
5. correr su prueba específica;
6. continuar únicamente si el resultado coincide con este contrato.

## 1. Alcance exacto

Fase 1 debe entregar un módulo nuevo que permita:

- elegir una fuente de audiencia;
- aplicar filtros generales;
- seleccionar familias de audiencia mediante checks acumulables;
- ver composición, duplicados y exclusiones;
- revisar detalle de destinatarios;
- crear una campaña V2;
- congelar la audiencia;
- clasificar comercialmente la campaña;
- consultar campañas V2 creadas.

Fase 1 NO debe:

- enviar WhatsApp;
- llamar POST /v2/broadcast;
- sincronizar stats por campaign_id;
- importar campañas históricas de iVentas;
- calcular costo de campaña;
- crear jobs/schedulers para iVentas;
- retirar ni modificar destructivamente el legacy.

## 2. Investigación obligatoria al comenzar la implementación

Antes de crear archivos nuevos, volver a inspeccionar main actual.

Archivos que deben revisarse como mínimo:

Backend:
- backend/app/models/marketing.py
- backend/app/services/marketing_reactivation_service.py
- backend/app/services/marketing_campaign_audience_service.py
- backend/app/services/marketing_campaign_preview_detail_service.py
- backend/app/services/marketing_campaign_explorer_creation_service.py
- backend/app/services/marketing_campaign_export_service.py
- backend/app/services/marketing_iventas_service.py
- backend/app/services/marketing_iventas_branch_service.py
- backend/app/warehouse/services/socios_activos_snapshot_resolver.py
- backend/app/warehouse/services/socios_vencidos_current_status_resolver.py
- backend/app/warehouse/services/socios_vencidos_reactivation_candidate_resolver.py
- backend/app/routes/marketing_routes.py
- backend/app/routes/marketing_campaign_preview_detail_routes.py

Frontend:
- frontend/src/app/marketing-reactivation/
- frontend/src/app/marketing-sales-funnel/
- frontend/src/app/app.routes.ts
- frontend/src/app/layout/layout.component.ts

Pruebas:
- backend/tests/services/test_marketing_campaign_v1.py
- backend/tests/services/test_marketing_campaign_preview_detail_service.py
- backend/tests/services/test_marketing_campaign_custom_expiration_dates.py
- backend/tests/services/test_marketing_custom_active_expiration.py
- backend/tests/services/test_marketing_weekly_frequency_choice.py
- backend/tests/marketing/test_marketing_routes.py

No asumir que estos archivos no cambiaron después de la fecha del contrato.

## 3. Qué debe reutilizarse

### 3.1 Normalización de teléfono

Reutilizar como normalizador general:

    backend/app/services/marketing_phone.py
    normalize_phone()

El adapter iVentas conserva además:

    backend/app/services/marketing_iventas_service.py
    normalize_iventas_phone()

El primero ya es compartido por Funnel/Contact Center; el segundo aporta semántica específica de iVentas. No crear normalize_campaign_phone(), normalize_whatsapp_phone() ni un tercer normalizador equivalente.

### 3.2 Resolución de sucursales y regiones

Reutilizar la infraestructura existente de:

- Sucursal;
- SuiteRegionORM;
- SuiteSucursalRegionAssignmentORM;
- TrackBranchCatalogORM;
- alias Track cuando corresponda.

No crear catálogos paralelos de sucursales.

### 3.3 Snapshots de socios activos

Reutilizar:

    resolve_latest_canonical_socios_activos_snapshot()

La fuente de Socios activos debe respetar canonicalidad Warehouse. No consultar directamente una tabla raw ignorando el resolver.

**No crear una nueva tabla poblada con todos los socios activos para Campañas V2.** El constructor consulta la base canónica existente. La campaña solo necesita registrar la pertenencia de los destinatarios elegidos al cohorte y una referencia al snapshot/fila fuente cuando sea posible.

### 3.4 Socios vencidos

Reutilizar los resolvers vigentes de estado actual y candidatos de reactivación y la cartera histórica canónica existente.

**No crear una nueva tabla poblada con la base completa de socios vencidos.** V2 consulta `socios_vencidos_cartera`/resolvers vigentes y, al congelar una campaña, referencia el episodio canónico (`socios_vencidos_cartera_id`) cuando aplique.

V2 puede cambiar la forma de seleccionar segmentos, pero no debe duplicar el matcher de identidad vencido/activo.

### 3.5 Preview y drill-down

El legacy ya tiene:

- rebuild server-side;
- buckets;
- paginación;
- filtros;
- composición;
- validación contador preview vs detalle;
- deduplicación final.

Fase 1 debe estudiar qué piezas son genéricas.

Preferencia:
- extraer helpers puros reutilizables;
- mantener wrappers legacy;
- crear un servicio V2 con semántica V2.

No copiar y pegar un segundo bloque grande de lógica casi idéntica.

## 4. Qué sí justifica código/persistencia nueva

El modelo legacy está semánticamente atado a Reactivaciones:

    MarketingReactivationCampaignORM
    MarketingReactivationCampaignRecipientORM

Incluye campos y estados específicos del flujo actual.

Como el usuario pidió convivencia real entre legacy y V2, es pertinente que V2 tenga persistencia propia si generalizar el legacy implica romperlo o introducir columnas ambiguas.

La decisión exacta debe documentarse en el primer PR de implementación, pero la preferencia contractual es:

- campañas V2 en entidad genérica propia;
- una relación mínima de destinatarios/cohorte V2, no una copia de las bases fuente;
- referencias hacia Socios Activos, Socios Vencidos, Funnel u otras fuentes existentes;
- metadata snapshot únicamente cuando sea necesaria para congelar el criterio o cubrir una retención real;
- reutilización de utilidades comunes.

No renombrar tablas legacy ni cambiar su semántica en Fase 1.

## 5. Catálogo de tarifas y familia de audiencia

El archivo de negocio entregado contiene tres niveles conceptuales:

    tarifa
    categoria_tarifa
    plantilla

En V2 el tercer nivel se llamará:

    audience_family

para no confundirlo con plantillas reales de WhatsApp.

Familias principales aprobadas:

- DOMICILIADO
- TRIMESTRAL
- CONVENIO
- SEMESTRE
- ESTUDIANTE

Estados adicionales observados en el catálogo:

- MES
- OUT_OF_SEGMENT

MES queda pendiente de definición funcional. No convertirlo automáticamente en sexta familia visible sin confirmación.

OUT_OF_SEGMENT debe permanecer distinguible y no entrar silenciosamente en Seleccionar todos de las cinco familias comerciales principales.

## 6. Relación con MarketingReactivationTariffORM existente

Actualmente existe:

    marketing_reactivation_tariffs

con:

- tarifa_key;
- tarifa_raw;
- categoria_tarifa;
- reactivation_group;
- is_active;
- source.

reactivation_group tiene semántica legacy:

- REACTIVATE
- DOMICILIATED_FLOW
- EXCLUDE
- REVIEW
Esto NO equivale a audience_family.

Por lo tanto está prohibido sustituir reactivation_group por la nueva taxonomía.

Antes de crear una segunda tabla de tarifas, comparar el catálogo nuevo contra marketing_reactivation_tariffs.

### Camino preferido si la identidad de tarifa coincide

Si tarifa_key existente representa la misma tarifa Gasca y el catálogo cubre el mismo universo, preferir extender el catálogo existente con un atributo independiente audience_family, mediante migración Alembic, sin alterar reactivation_group.

Ventaja:
- una sola identidad de tarifa;
- legacy conserva su grupo;
- V2 obtiene su familia;
- no se duplican 166 strings de negocio.

### Camino alterno permitido

Crear una tabla de mapping V2 separada solo si la investigación demuestra una diferencia real de ciclo de vida, fuente o cardinalidad.

En ese caso debe referenciar una clave canónica de tarifa y explicar por qué reutilizar marketing_reactivation_tariffs sería incorrecto.

No se permite crear un segundo catálogo idéntico únicamente por comodidad.

## 7. Fuentes de audiencia de Fase 1

### 7.1 Socios vencidos

Debe poder seleccionar un rango de vencimiento.

Ejemplo:

    2026-07-01 a 2026-08-31

Debe respetar:
- alcance de sucursal;
- estado actual resuelto con fuentes canónicas;
- teléfono normalizado;
- catálogo de tarifa.

No debe imponer automáticamente las exclusiones comerciales del flujo legacy solo porque antes existían.

### 7.2 Socios activos

Debe provenir del snapshot canónico de Socios Activos.

Debe permitir construir audiencias de campañas para clubes sin volver a descargar manualmente la base de Gasca cuando la información ya está disponible en Warehouse.

### 7.3 Funnel / Venta nueva

Fase 1 debe dejar el modelo suficientemente genérico para una fuente `FUNNEL_PORTFOLIO`, pero su integración operativa se hará en **Fase 2 antes del enviador**.

La investigación ya localizó detalle individual en los servicios de Funnel. No usar agregados como destinatarios.

Contrato mínimo futuro:
- `phone_mx10` válido;
- `source = FUNNEL_PORTFOLIO`;
- referencias/origen cuando existan.

Nombre, sucursal, contact_id, canal y fecha son opcionales. No exigir member_id, PIN, tarifa ni audience_family y no inventar sucursal por lada. Fase 1 solo debe evitar un esquema que obligue a tener identidad de socio para todo recipient.

### 7.4 Campaña anterior

Puede prepararse la abstracción, pero el filtro por estados iVentas de una campaña anterior pertenece funcionalmente a Fase 2.

En Fase 1 una campaña V2 previa sí puede ser fuente por su audiencia congelada, sin filtros de delivery que todavía no existan.

## 8. Semántica de filtros

### 8.1 Checks de familia

UI esperada:

    [x] Domiciliado
    [x] Trimestral
    [ ] Convenio
    [ ] Semestre
    [ ] Estudiante

Seleccionar todos es un atajo de UI, no un valor persistido.

### 8.2 OR dentro del grupo

Si están seleccionados Domiciliado y Trimestral:

    audience_family IN (DOMICILIADO, TRIMESTRAL)

No significa que el destinatario deba cumplir ambas.

### 8.3 AND entre dimensiones

Ejemplo:

    source = EXPIRED_MEMBERS
    AND expiration_date between A and B
    AND branch in allowed
    AND family in selected_families

### 8.4 Multi-etiqueta

Si en el futuro una persona puede portar varias etiquetas de segmentación, debe persistirse la composición que justificó su inclusión.

No perder información por deduplicar el teléfono.

## 9. Bloqueos técnicos

Fase 1 debe diferenciar claramente:

- coincidencia comercial;
- exclusión técnica;
- exclusión obligatoria de negocio.

El pipeline debe permitir **suppression resolvers** por fuente. Ejemplo futuro de Fase 2: `FUNNEL_PORTFOLIO` cruza contra el snapshot canónico de Socios Activos y marca `ACTIVE_MEMBER_SUPPRESSION` antes de congelar la audiencia. Fase 1 no implementa ese cruce, pero no debe diseñar un modelo que impida agregarlo.

Ejemplos técnicos:
- teléfono ausente;
- teléfono no normalizable para el canal;
- teléfono duplicado en la misma audiencia.

No denominar “fuera de segmento” a un teléfono inválido. Son motivos distintos.

## 10. Preview obligatorio

No se puede crear una campaña directamente desde filtros sin Preview.

El Preview debe exponer al menos:

- universo inicial;
- fuente y fecha/corte usados;
- filtros activos;
- conteo por familia;
- sin clasificación de familia;
- fuera de segmento;
- teléfonos inválidos;
- duplicados;
- destinatarios únicos finales.

Debe existir drill-down paginado por cada grupo relevante.

El conteo del drill-down debe coincidir con el contador del Preview. Si no coincide, fallar y no permitir congelar la campaña.

## 11. Seguridad de selección

Se mantiene el patrón del Audience Explorer actual:

- Angular manda filtros/selección;
- backend reconstruye el universo;
- backend reaplica filtros;
- backend verifica permisos;
- backend deduplica;
- backend persiste.

Nunca aceptar una lista arbitraria de recipient IDs del navegador como autoridad.

## 12. Audiencia congelada

Al crear la campaña V2, persistir snapshot suficiente para reconstruir qué se sabía en ese momento.

Por destinatario, conceptualmente conservar:

- identificador de campaña;
- identidad de miembro/lead si existe; puede ser NULL para fuentes phone-only;
- teléfono normalizado;
- identidad/calidad de fuente cuando aplique (por ejemplo PHONE_ONLY);
- sucursal cuando exista; no debe ser obligatoria para todas las fuentes;
- fuente;
- referencia de fuente;
- tarifa observada;
- categoria_tarifa observada;
- audience_family observada;
- fecha de vencimiento si aplica;
- razón de inclusión;
- created_at.

Preferir referencia a la fuente canónica. Si la fila fuente es inmutable y su retención está garantizada, no duplicar sus campos. Solo congelar metadata mínima cuando la fuente sea mutable, calculada o exista una política real de retención que pueda romper el histórico.

## 13. Estados de mensajería no pertenecen a las bases fuente

Aunque Fase 1 todavía no sincroniza iVentas, el modelo debe reservar el lugar correcto para Fase 2: los flags `sent`, `delivered`, `viewed`, `failed` e interacciones pertenecen al destinatario **dentro de una campaña**, no a Socios Activos ni Socios Vencidos.

No agregar esos flags a las tablas canónicas de Warehouse.

## 14. Clasificación comercial de campaña

Campo obligatorio con default:

    UNCLASSIFIED

Valores:
- NEW_SALE
- REACTIVATION
- ACTIVE_MEMBERS
- UNCLASSIFIED

La clasificación es distinta de audience_family.

Ejemplo válido:

    purpose = REACTIVATION
    families = DOMICILIADO + TRIMESTRAL

## 15. Precarga por nombre

Para campañas creadas dentro de V2, el usuario debe elegir explícitamente el propósito cuando corresponda.

La clasificación automática por nombre se requiere principalmente para campañas externas/históricas de Fase 2.

Si Fase 1 implementa sugerencia por nombre:
- debe ser backend;
- debe ser conservadora;
- debe registrar source = AUTO;
- cualquier ambigüedad queda UNCLASSIFIED;
- override manual siempre gana.

No hardcodear reglas en Angular.

## 16. Frontend

Crear un módulo/pantalla nuevo, separado del flujo legacy.

No reutilizar el componente legacy completo como V2 mediante condicionales crecientes.

Sí se permite:
- reutilizar modelos compartidos reales;
- extraer controles visuales genéricos;
- reutilizar estilos comunes;
- reutilizar servicios de permisos.

La ruta exacta debe definirse tras revisar app.routes.ts y menú actual. No modificar la ruta /#/marketing/reactivation.

## 17. Permisos

Fase 1 debe investigar el permiso real que hoy protege Marketing/Reactivaciones.

No confiar en ocultar el menú.

El backend debe validar alcance por usuario y sucursal en cada preview/create/read.

Si Campañas V2 necesita permiso nuevo, debe definirse en el sistema de permisos existente, no con un if de rol aislado.

## 18. API interna esperada

Los nombres finales se decidirán al implementar, pero V2 necesita operaciones equivalentes a:

- obtener opciones de fuente/filtros;
- preview;
- preview detail;
- crear campaña desde preview;
- listar campañas V2;
- obtener campaña V2;
- actualizar clasificación comercial.

No duplicar endpoints legacy solo cambiando /v1 por /v2 si la semántica es distinta.

## 19. Pruebas mínimas

Backend:
- OR de familias;
- AND entre dimensiones;
- deduplicación por teléfono;
- familia sin clasificar;
- fuera de segmento separado;
- teléfono inválido separado;
- alcance por sucursal;
- preview vs detail consistente;
- creación reconstruye selección server-side;
- audiencia congelada;
- cambio posterior del catálogo no cambia snapshot de campaña;
- campaña vacía rechazada;
- permisos backend.

Migraciones:
- upgrade;
- downgrade cuando sea razonable;
- constraints;
- índices;
- no alterar semántica legacy.

Frontend:
- checks acumulables;
- Seleccionar todos;
- invalidación del preview cuando cambia filtro;
- no crear sin preview válido;
- mostrar composición y total único;
- drill-down.

## 20. Criterio de aceptación de Fase 1

Debe ser posible:

1. abrir Campañas V2;
2. elegir Socios vencidos;
3. elegir rango julio-agosto 2026;
4. seleccionar todas las sucursales permitidas;
5. marcar Domiciliado y Trimestral;
6. obtener Preview;
7. ver conteos individuales, cruces/deduplicación y total final;
8. abrir detalle;
9. crear campaña;
10. cerrar y volver a abrir;
11. observar exactamente la misma cohorte congelada.

También debe funcionar un caso de Socios activos si su fuente ya está soportada por Warehouse.

No es requisito de Fase 1 que esa campaña sea enviada por iVentas.

## 21. Condición de salida hacia Fase 2

No iniciar Fase 2 hasta que:

- el catálogo esté resuelto;
- la audiencia congelada sea confiable;
- permisos estén probados;
- legacy siga funcionando;
- las fuentes utilizadas sean canónicas;
- no exista duplicación obvia de utilidades existentes;
- los contratos de API internos de Campañas V2 estén estabilizados.

## 22. Instrucción de arranque recomendada para una conversación nueva de Fase 1

Usar este texto como primera orden:

    Estamos implementando únicamente Campañas V2 Fase 1.
    Este archivo es autosuficiente; no asumas que tienes contexto de conversaciones anteriores.
    Inspecciona primero main actual y los archivos existentes citados.
    No modifiques nada todavía.
    Identifica exactamente qué podemos reutilizar y qué requiere persistencia nueva.
    Propón un solo primer cambio mínimo con archivo, función, objetivo, motivo y prueba.
    No avances a iVentas stats ni envío.
