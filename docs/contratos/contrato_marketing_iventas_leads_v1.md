# Contrato canónico — iVentas → Marketing / Contactos V1

**Estado:** APROBADO PARA PERSISTENCIA V1 Y CANARY REAL VALIDADO
**No autoriza:** sustituir todavía el KPI `leads` del dashboard
**Versión:** 1.2
**Fecha:** 2026-08-11

---

# 1. Objetivo

Integrar la API de contactos de iVentas con Suite Ultra como fuente estructurada, persistida y auditable de contactos CRM por sucursal.

La integración debe permitir conservar:

```text
iVentas
    ↓
Contacto CRM
    ↓
Identidad individual
    ↓
teléfono + sucursal
    ↓
tags observados
    ↓
futura relación con visitas y ventas
```

Esta V1 **NO** define:

```text
contacto iVentas = lead Meta
```

y **NO** sustituye todavía el KPI `leads` utilizado por Marketing.

La V1 tampoco modifica la lógica existente:

```text
Venta Total
    ↓
visita / pase
    ↓
Ventas Nuevos Socios Detalle
    ↓
venta atribuida
```

La investigación posterior a la primera versión del contrato sí permite definir una semántica derivada denominada:

```text
Lead Meta observado en iVentas
```

pero dicha semántica se mantiene separada de la atribución histórica/causal y no autoriza todavía el reemplazo del KPI del dashboard.

---

# 2. Regla semántica principal

La regla obligatoria es:

> Un registro devuelto por `/v1/integrations/contacts` es un **contacto iVentas**.

No debe llamarse automáticamente:

```text
lead
lead Meta
lead publicitario
conversión Meta
```

La cantidad total de contactos iVentas **NO** debe compararse como si fuera equivalente a una métrica agregada de Meta.

La evidencia real del run 20 confirmó esta separación: un solo día devolvió 1,065 contactos iVentas, pero únicamente 281 contactos tenían al menos un tag `ad_fb_<ad_id>`.

---

# 3. Responsabilidad de cada fuente

| Información | Fuente |
|---|---|
| Inversión publicitaria | Meta |
| Impresiones, clicks y actions publicitarias | Meta |
| Contactos CRM individuales | iVentas |
| Identidad / teléfono del contacto | iVentas |
| Tags CRM observados | iVentas |
| Visitas / pases | Venta Total |
| Ventas nuevas | Ventas Nuevos Socios Detalle |
| Ingreso atribuido | Ventas Nuevos Socios Detalle |
| Inputs manuales actuales | `marketing_monthly_inputs` |

Meta e iVentas son fuentes independientes.

Pueden relacionarse técnicamente, pero sus totales no tienen obligación de ser iguales.

---

# 4. Evidencia real validada en Papalote

La investigación read-only previa a la persistencia confirmó:

```text
Papalote
2026-07-01 → 2026-07-28

contactos iVentas:
2,417

contactos con al menos un tag ad_fb_*:
137

contactos con múltiples ad_fb_*:
2
```

También se validó:

```text
contact.id únicos:
2,417

duplicados exactos de contact.id:
0
```

La mayoría de los contactos son personas/números distintos y el alto volumen de iVentas **NO** se explica por duplicación masiva del mismo teléfono.

Esta evidencia continúa vigente y fue complementada posteriormente por el canary real de red completa descrito en la sección 30.

---

# 5. Puente técnico Meta ↔ iVentas

Se comprobó directamente que tags como:

```text
ad_fb_120247508131700426
ad_fb_120247508581990426
ad_fb_120247652169990426
```

corresponden a `ad_id` reales de Meta.

Ejemplo:

```text
Meta ad_id:
120247508131700426

iVentas tag:
ad_fb_120247508131700426
```

Por lo tanto:

```text
ad_fb_<ad_id>
```

es un puente técnico válido entre el estado observado de un contacto iVentas y un identificador de anuncio Meta.

Sin embargo, después del canary real también quedó demostrado que un `ad_id` observado en iVentas puede dejar de ser accesible mediante los tokens Meta actuales.

Por tanto:

```text
ad_fb_<ad_id> observado en iVentas
```

**NO** exige que el objeto Meta siga siendo resoluble en el futuro para conservar la observación raw/estructurada.

---

# 6. Un tag ad_fb_* NO es atribución histórica

Está prohibido interpretar automáticamente:

```text
ad_fb_<ad_id>
```

como:

```text
"este anuncio originó este contacto"
```

La investigación encontró un contacto:

```text
createdAt:
2026-07-07
```

que posteriormente contenía:

```text
ad_fb_120247748588320426
```

aunque ese anuncio Meta fue creado:

```text
2026-07-31
```

Por definición, ese anuncio no pudo originar el contacto el 7 de julio.

También se encontró un contacto:

```text
createdAt:
2026-07-13

firstMessageAt:
2026-07-28
```

con:

```text
ad_fb_120243932061760426
```

mientras Meta reportaba ese anuncio pausado desde junio y sin delivery durante el periodo de julio analizado.

Conclusión contractual:

> Los tags iVentas representan relaciones observadas en el estado del contacto al momento de consultar la API. No deben tratarse como historia inmutable de atribución.

Esto continúa siendo obligatorio incluso para la métrica derivada “Lead Meta observado en iVentas”.

---

# 7. Cardinalidad de tags

La relación es:

```text
contacto
    ↓
0..N tags
```

y específicamente:

```text
contacto
    ↓
0..N tags ad_fb_*
    ↓
0..N anuncios Meta relacionados
```

Se validaron contactos con múltiples tags `ad_fb_*` simultáneos.

Por tanto está prohibido modelar:

```text
marketing_iventas_contacts.meta_ad_id
```

como una única FK o columna de atribución.

La relación debe persistirse separadamente.

Para una futura métrica de “Lead Meta observado”:

```text
1 contacto
2+ META_AD tags
```

debe contar como:

```text
1 Lead Meta observado
N relaciones META_AD observadas
```

Nunca como N leads.

---

# 8. API iVentas

Endpoint:

```text
GET https://rest.iventas.mx/v1/integrations/contacts
```

Autenticación:

```text
Authorization: Bearer <TOKEN>
```

Parámetros:

```text
branch
from
to
limit
cursor
```

Restricciones conocidas:

```text
1 branch por request
máximo 31 días
máximo 100 contactos por página
aprox. 45 requests/minuto
```

Suite utiliza internamente:

```text
limit = 100
máximo 40 requests/minuto
```

---

# 9. Seguridad

El token únicamente puede existir en entorno backend:

```text
IVENTAS_API_TOKEN
```

Base URL configurable:

```text
IVENTAS_API_BASE_URL
```

Default:

```text
https://rest.iventas.mx
```

Nunca persistir o imprimir:

```text
Authorization
Bearer token
token completo
headers sensibles
```

La rotación de la credencial no debe requerir cambios de código.

Para pruebas locales:

```text
Flask / DB local
→ backend/.env.local

credenciales Meta/iVentas de integración
→ pueden leerse desde .env.docker mediante dotenv_values()
```

Está prohibido cargar `.env.docker` en `os.environ` dentro de una ejecución local de Flask cuando eso pueda contaminar la conexión PostgreSQL con:

```text
host = db
```

---

# 10. Sucursales

Los códigos proporcionados por iVentas son 26 y quedaron completamente validados contra Suite/Track.

| # | Código iVentas | `sucursal_id` Suite | Canon Track |
|---:|---|---:|---|
| 1 | `villas-del-rey` | 1 | `VILLAS_DEL_REY` |
| 2 | `villa-verde` | 2 | `VILLA_VERDE` |
| 3 | `independencia` | 3 | `INDEPENDENCIA` |
| 4 | `tecnologico` | 4 | `TEC_MXL` |
| 5 | `sendero-mexicali` | 5 | `SEND_MXL` |
| 6 | `san-luis-rio-colorado` | 6 | `SAN_LUIS` |
| 7 | `pabellon-rosarito` | 7 | `PABELLON_RTO` |
| 8 | `mision` | 8 | `MISION_ENS` |
| 9 | `paseo-2000` | 9 | `PASEO_2000` |
| 10 | `loma-bonita` | 10 | `LOMA_BONITA` |
| 11 | `santa-fe` | 11 | `SANTA_FE` |
| 12 | `carrousel` | 12 | `CARROUSEL_TJ` |
| 13 | `papalote` | 13 | `PAPALOTE_TJ` |
| 14 | `sendero-culiacan` | 14 | `SEND_CUL` |
| 15 | `san-isidro` | 15 | `SAN_ISIDRO_CUL` |
| 16 | `azahares` | 16 | `AZAHARES_CUL` |
| 17 | `santa-catarina` | 17 | `STA_CATARINA` |
| 18 | `saltillo-sur` | 18 | `SEND_SALTILLO` |
| 19 | `sendero-chihuahua` | 19 | `SEND_CHIH` |
| 20 | `paseo-la-paz` | 20 | `PASEO_LA_PAZ` |
| 21 | `ixtapaluca` | 21 | `IXTAPALUCA` |
| 22 | `insurgentes` | 22 | `INSURGENTES` |
| 23 | `tlalnepantla` | 23 | `TLALNEPANTLA` |
| 24 | `villalta` | 24 | `SALTILLO_VILLALTA` |
| 25 | `metepec` | 25 | `METEPEC` |
| 26 | `serrania` | 26 | `SERRANIA` |

Validación final:

```text
26 códigos iVentas
26 aliases activos iventas_family
26 aliases resueltos dinámicamente
26 sucursal_id únicos
26 Canon Track válidos
0 ambiguos
0 faltantes
0 destinos duplicados
```

La resolución runtime utiliza:

```text
TrackBranchAliasORM
source_family = iventas_family
```

No debe existir un diccionario de negocio quemado dentro del service.

## 10.1 Casos Saltillo validados contra iVentas

Se validaron directamente contra:

```text
GET /v1/integrations/contacts
```

| Código iVentas | Branch response iVentas | Sucursal Suite | `sucursal_id` | Canon Track | Estado |
|---|---|---|---:|---|---|
| `villalta` | `Villalta` | Saltillo Villalta | 24 | `SALTILLO_VILLALTA` | VALIDADO |
| `saltillo-sur` | `Sendero Saltillo Sur` | Sendero saltillo | 18 | `SEND_SALTILLO` | VALIDADO |

También se probó explícitamente:

```text
branch = saltillo
HTTP 404
BRANCH_NOT_FOUND
```

Por lo tanto, `saltillo` no debe registrarse como código iVentas válido ni como alias de `iventas_family`.

---

# 11. Fechas y timezone

El periodo comercial de Suite utiliza:

```text
America/Tijuana
```

iVentas recibe:

```text
UTC ISO8601
```

Se debe construir primero el rango local y después convertir a UTC.

Ejemplo válido:

```text
2026-07-01T07:00:00.000Z
2026-07-29T06:59:59.999Z
```

La integración debe emitir precisión de milisegundos:

```text
.000Z
.999Z
```

No utilizar microsegundos de seis posiciones.

El canary real 2026-08-10 utilizó:

```text
local:
2026-08-10 00:00:00 America/Tijuana
→
2026-08-10 23:59:59.999 America/Tijuana

UTC:
2026-08-10T07:00:00.000Z
→
2026-08-11T06:59:59.999Z
```

Nota Meta:

```text
CP01 / CP03:
America/Tijuana

ULTRAGYM2 / ULTRAGYM3:
America/Mexico_City
```

Por ello una verificación Meta “same-day” por calendario de cuenta es únicamente diagnóstica hasta que exista un contrato específico de timezone Meta.

---

# 12. createdAt y firstMessageAt

Ambos campos deben conservarse independientemente.

Persistir:

```text
created_at_utc
created_at_local
created_date_local

first_message_at_utc
first_message_at_local
first_message_date_local
```

`firstMessageAt` puede ser:

```text
igual o casi inmediato a createdAt
posterior a createdAt
nullable
```

No debe derivarse uno del otro.

La investigación histórica encontró diferencias de varios días entre ambos.

## 12.1 Regla temporal para “Lead Meta observado en iVentas”

La evidencia del run 20 permitió congelar la siguiente semántica derivada:

```text
lead_date = created_date_local
```

Razón:

```text
createdAt
→ fecha en que el contacto entra a la cohorte iVentas

firstMessageAt
→ evidencia de interacción/conversación
```

`firstMessageAt` será obligatorio para la métrica derivada de “Lead Meta observado”, pero **NO** gobierna su fecha comercial.

Ejemplo:

```text
createdAt:
2026-08-31 23:59 America/Tijuana

firstMessageAt:
2026-09-01 00:01 America/Tijuana
```

Debe pertenecer a:

```text
lead_date = 2026-08-31
```

y conservar:

```text
first_message_date_local = 2026-09-01
```

Esto evita mover retrospectivamente la cohorte por el momento de conversación.

Evidencia run 20 sobre 281 contactos META_AD:

```text
created_date_local = 2026-08-10:
281/281

first_message_date_local = 2026-08-10:
281/281

firstMessage NULL:
0

created → firstMessage:
mínimo   0.195 s
mediana  0.378 s
máximo   699.405 s

<= 1 s:
274/281
```

Esta regla **NO** autoriza todavía sustituir el KPI `marketing_monthly_inputs.leads`.

---

# 13. Teléfono

Debe conservarse siempre:

```text
phone_raw
phone_digits
```

Además se calcula:

```text
phone_mx10
```

solo cuando sea compatible con el matcher mexicano.

Reglas MX:

```text
10 dígitos
→ phone_mx10

52 + 10 dígitos
→ quitar 52

521 + 10 dígitos
→ quitar 521
```

Otros formatos **NO** deben clasificarse automáticamente como inválidos.

Clasificación:

```text
MX10_MATCHABLE
NON_MX_OR_UNRESOLVED
MISSING
```

Un contacto no MX:

```text
sigue siendo contacto iVentas
se conserva
no se descarta
```

Únicamente puede quedar fuera del matcher MX10 de visitas/ventas.

---

# 14. Estrategia raw first

Toda sincronización seguirá:

```text
raw first
structured later
```

Proceso obligatorio:

```text
crear sync_run en RUNNING

por cada branch:
    solicitar página
    guardar payload raw
    parsear metadata
    normalizar contactos/tags
    persistir structured
    continuar paginación

releer contadores desde DB
finalizar corrida

si cumple canonicalidad:
    puede sustituir snapshot canónico
```

La página raw debe persistirse **antes** de parsear el payload estructurado.

Si una página se recibió pero posteriormente falla su parseo:

```text
raw page:
se conserva

has_more:
puede quedar NULL

contacts_count:
puede quedar NULL
```

El snapshot canónico iVentas representa:

> La fotografía CRM oficial de esa extracción.

**NO** representa automáticamente:

> El número oficial de leads Meta del dashboard.

---

# 15. marketing_iventas_sync_runs

Campos:

```text
id

period_key
date_from
date_to

started_at
finished_at

status

branches_requested
branches_completed
branches_failed

contacts_received
contacts_unique

contacts_with_phone
contacts_mx10_matchable
contacts_non_mx_or_unresolved

contacts_with_first_message
contacts_with_any_tag
contacts_with_meta_ad_tag
contacts_with_multiple_meta_ad_tags

aliases_resolved
aliases_unresolved

is_canonical

created_at
```

Estados:

```text
RUNNING
COMPLETED
PARTIAL
FAILED
```

Semántica terminal:

```text
COMPLETED
→ todas las branches solicitadas terminaron correctamente
→ branches_failed = 0
→ aliases_unresolved = 0

PARTIAL
→ al menos 1 branch completó
→ pero no todas completaron

FAILED
→ 0 branches completaron
```

Debe cumplirse al finalizar:

```text
branches_completed + branches_failed
=
branches_requested
```

`contacts_received` representa la suma de objetos `contact` de páginas parseadas correctamente.

Si una branch procesa páginas válidas y luego falla:

```text
sus páginas válidas ya recibidas
sí participan en contacts_received

la página cuyo parseo falla
queda raw pero no aporta contacts_count
```

Los contadores finales deben releerse desde la DB persistida; no deben confiar únicamente en acumuladores de memoria.

---

# 16. marketing_iventas_raw_pages

Conserva exactamente la respuesta recibida.

Campos:

```text
id
sync_run_id

branch_code
page_number

request_cursor
next_cursor
has_more

http_status
payload_json

received_at
contacts_count
```

`has_more` y `contacts_count` deben permitir `NULL` cuando el raw fue persistido pero el parseo posterior falló.

`contacts_count` debe cumplir:

```text
NULL
o
>= 0
```

Nunca almacenar:

```text
Authorization
Bearer token
headers sensibles
```

---

# 17. marketing_iventas_contacts

Cada fila representa la fotografía estructurada de un contacto dentro de una corrida.

Campos:

```text
id
sync_run_id

sucursal_id
branch_code

contact_id

name

phone_raw
phone_digits
phone_mx10
phone_match_status

created_at_utc
created_at_local
created_date_local

first_message_at_utc
first_message_at_local
first_message_date_local

channel_id
channel_name
channel_phone
channel_platform

agent_json

last_message_status
last_outbound_message_at_utc

row_hash

created_at
```

Restricción:

```text
UNIQUE(
    sync_run_id,
    branch_code,
    contact_id
)
```

No inferir identidad utilizando nombre.

La persistencia es inmutable entre runs.

---

# 18. marketing_iventas_contact_tags

Esta tabla es obligatoria.

Representa los tags observados para un contacto dentro de un snapshot.

Campos:

```text
id

sync_run_id
iventas_contact_row_id

branch_code
contact_id

tag_raw
tag_kind
meta_ad_id

observed_at
created_at
```

`tag_kind`:

```text
META_AD
OTHER
```

Cuando:

```text
tag_raw = ad_fb_<número>
```

se deriva:

```text
tag_kind = META_AD
meta_ad_id = <número>
```

Esto **NO** convierte la relación en atribución histórica.

Restricción:

```text
UNIQUE(
    sync_run_id,
    iventas_contact_row_id,
    tag_raw
)
```

---

# 19. Snapshots y mutabilidad

No se hará UPSERT destructivo entre corridas.

Ejemplo:

```text
run 10
contact ABC
tags = [A]

run 11
contact ABC
tags = [A, B]
```

ambas fotografías deben conservarse.

Esto permite auditar:

```text
qué devolvía iVentas
en cada fecha de extracción
```

Los tags pueden cambiar entre corridas.

Por ello:

```text
ad_fb_<ad_id>
```

se interpreta como:

```text
relación observada en ese snapshot
```

y no como una propiedad histórica inmutable del contacto.

---

# 20. Canonicalidad

Una corrida puede convertirse en canónica solamente si:

```text
status = COMPLETED
branches_failed = 0
aliases_unresolved = 0
```

Una corrida:

```text
PARTIAL
FAILED
```

nunca sustituye la canónica anterior.

La sustitución debe ser transaccional.

Debe existir como máximo:

```text
1 corrida canónica por period_key
```

mediante restricción/índice único parcial equivalente.

Importante:

```text
canonical iVentas
!=
KPI leads oficial
```

Canonicalidad significa únicamente:

```text
snapshot CRM oficial del periodo
```

El canary real run 20 fue ejecutado deliberadamente con:

```text
make_canonical_on_completed = False
```

y debe permanecer:

```text
is_canonical = False
```

---

# 21. Paginación

Primera llamada:

```text
branch
from
to
limit=100
```

Siguientes:

```text
branch
from
to
limit=100
cursor=<nextCursor>
```

El cursor:

```text
pertenece al branch
pertenece al rango
no se reutiliza entre corridas
```

La implementación debe detectar:

```text
cursor repetido
has_more sin next_cursor
secuencia inválida
exceso de max_pages
```

y fallar explícitamente.

---

# 22. Retries y timeouts

Timeout:

```text
connect = 10 s
read = 30 s
```

Errores recuperables:

```text
429
500
503
timeout de red recuperable
```

Retry acotado:

```text
2 s
5 s
10 s
fallar
```

Nunca retry infinito.

Errores:

```text
400
403
404
```

deben producir diagnóstico explícito.

Los errores operativos de una branch no deben ocultar un bug inesperado del orquestador.

El orquestador puede capturar errores operativos conocidos para continuar con otras branches, pero una excepción genérica inesperada debe hacer rollback y propagarse.

---

# 23. Ejecución fuera de Gunicorn

Está prohibido ejecutar una sincronización completa como request Flask largo.

No implementar un request web que mantenga un worker Gunicorn ocupado durante minutos.

La sincronización debe vivir en:

```text
comando controlado
worker
scheduler independiente
```

siguiendo el patrón operativo de Suite Ultra.

---

# 24. Marketing Dashboard

Esta V1 **NO** sustituye todavía:

```text
marketing_monthly_inputs.leads
```

por:

```text
COUNT(contactos iVentas)
```

ni por:

```text
COUNT(contactos con META_AD)
```

sin activar el contrato derivado correspondiente.

Hasta aprobar e implementar el flujo oficial:

```text
lead KPI actual
→ conserva su fuente vigente
```

iVentas puede aportar métricas diagnósticas:

```text
iventas_contacts_total
iventas_contacts_with_meta_tag
iventas_contacts_mx10_matchable
iventas_contacts_multitag
```

No deben sumarse automáticamente a `leads`.

---

# 25. Semántica derivada — Lead Meta observado en iVentas

La investigación posterior al canary permite definir conceptualmente:

```text
Lead Meta observado en iVentas
```

como una métrica distinta de:

```text
contacto iVentas total
```

y distinta de:

```text
atribución histórica/causal Meta
```

## 25.1 Regla candidata aprobada

Un contacto puede contar una sola vez como “Lead Meta observado en iVentas” cuando:

```text
1. pertenece a un snapshot iVentas canónico;
2. tiene al menos un tag exacto ad_fb_<ad_id>;
3. firstMessageAt no es NULL;
4. se deduplica a nivel contacto + sucursal + periodo;
5. lead_date = created_date_local.
```

Si tiene múltiples tags `META_AD`:

```text
1 contacto
N ad_fb_*

→ 1 lead observado
→ N relaciones META_AD observadas
```

## 25.2 Verificación Meta separada del conteo

La verificación del `ad_id` en Meta es una dimensión de auditoría/enriquecimiento.

Estados conceptuales:

```text
VERIFIED_SAME_DAY
VERIFIED_OBJECT_ONLY
NOT_CURRENTLY_VERIFIABLE
```

Semántica:

```text
VERIFIED_SAME_DAY
→ el ad_id fue observado también en insights Meta del día consultado

VERIFIED_OBJECT_ONLY
→ el objeto Meta es accesible, pero no apareció en insights de ese día

NOT_CURRENTLY_VERIFIABLE
→ iVentas conserva ad_fb_<ad_id>, pero los tokens Meta actuales no pueden resolver el objeto
```

Ninguno de estos estados debe multiplicar ni eliminar por sí mismo el lead observado.

## 25.3 Lo que NO significa

Incluso si un contacto cumple la regla de Lead Meta observado:

```text
NO significa:
"este anuncio causó históricamente este contacto"
```

La relación sigue siendo:

```text
observada en el snapshot
```

La activación del KPI en dashboard, la persistencia de la verificación Meta y la automatización productiva requieren el contrato/implementación correspondiente.

---

# 26. No exigir igualdad Meta ↔ iVentas

Los agregados Meta y los contactos individuales iVentas pueden diferir.

Ejemplo histórico validado:

```text
ad 120247508131700426

Meta messaging_conversation_started_7d:
19

contactos iVentas observados con tag correspondiente:
19
```

pero también:

```text
ad 120247508581990426

Meta:
72

iVentas tags observados:
74
```

y:

```text
ad 120247652169990426

Meta:
41

iVentas tags observados:
44
```

Estas diferencias no deben corregirse artificialmente.

Cada fuente conserva su propia verdad operacional.

## 26.1 Evidencia run 20

Sobre los contactos META_AD del run 20:

```text
contactos únicos con META_AD:
281

filas de tag META_AD:
283

ad_id distintos:
64

contactos con múltiples META_AD:
2
```

Reconciliación diagnóstica same-day contra las cuatro cuentas Meta configuradas:

```text
ad_id observados en iVentas:
64

FOUND SAME-DAY META:
56

NOT IN SAME-DAY META:
8

multi-account matches:
0
```

Contactos:

```text
en ad_id FOUND SAME-DAY:
238

en ad_id NOT IN SAME-DAY:
43
```

De los 8 no encontrados same-day:

```text
1 ad_id / 1 contacto
→ objeto Meta actualmente accesible
→ CP01
→ CAMPAIGN_PAUSED

7 ad_id / 42 contactos
→ objeto no accesible actualmente con ninguno de los tokens configurados
```

La cobertura de cuentas Meta fue validada:

```text
3 tokens
4 cuentas configuradas
4 cuentas accesibles
0 cuentas accesibles no configuradas
```

Por tanto los 7 objetos no accesibles **NO** se explican por una quinta cuenta Meta omitida.

---

# 27. Firma de contactos META_AD y ruido operativo

El run 20 confirmó que `createdAt` por sí solo no puede representar leads.

Ejemplos de lotes operativos/no publicitarios:

```text
Azahares
279 contactos creados en el mismo minuto
276 sin firstMessage
0 META_AD

Sendero Mexicali
91 contactos creados en el mismo minuto
87 sin firstMessage
0 META_AD

San Isidro
123 contactos concentrados en pocos minutos
0 META_AD dentro del lote

Paseo La Paz
58 contactos concentrados en un minuto
0 META_AD dentro del lote
```

Comparación global:

```text
META_AD contacts:
281
with firstMessage:
281
median created→firstMessage:
0.378 s

NON_META contacts:
784
with firstMessage:
324
without firstMessage:
460
median created→firstMessage:
84.745 s
```

Los grandes lotes se concentraron en `NON_META`.

Esto demuestra:

```text
createdAt != lead
firstMessageAt != lead por sí solo
```

y soporta la definición separada de “Lead Meta observado”.

## 27.1 Objetos Meta no accesibles

Los 42 contactos pertenecientes a 7 `ad_id` no accesibles actualmente presentaron una firma equivalente a los contactos same-day verificados:

```text
META same-day:
238 contactos
median created→firstMessage = 0.376 s
delta <= 1 s = 97.06%

META object not currently accessible:
42 contactos
median created→firstMessage = 0.386 s
delta <= 1 s = 100%
```

Además:

```text
42/42 con firstMessage
42/42 con un único META_AD y sin otros tags
0 multitag
```

Por tanto está prohibido descartar esos contactos únicamente porque Meta ya no pueda resolver retrospectivamente el objeto.

---

# 28. Futuro contacto → visita

La persistencia de:

```text
phone_mx10
branch / sucursal
```

permitirá construir:

```text
Contacto / Lead Meta observado
    ↓ teléfono + sucursal
Venta Total
    ↓
Visita
```

La regla de visita existente continúa siendo independiente.

El cruce contacto/lead → visita requiere contrato propio.

No se implementa dentro de esta V1.

---

# 29. Seguridad y permisos

El backend continúa siendo la fuente real de permisos.

Cualquier endpoint que exponga información iVentas debe respetar:

```text
MarketingAccess
sucursales autorizadas
rol/permisos backend
```

Angular únicamente controla presentación.

Nombre y teléfono son información operativa.

La UI no debe exponer teléfono completo salvo caso funcional aprobado.

---

# 30. Logging

Permitido:

```text
sync_run_id
branch
page
http_status
cantidad de contactos
duración
retry
tipo de error
```

Prohibido:

```text
Bearer token
Authorization
teléfono completo
payload completo en stdout
```

Los payloads completos pertenecen exclusivamente al almacenamiento raw.

Los errores/resultados de orquestación tampoco deben imprimir:

```text
token
endpoint con secretos
payload raw
PII
```

---

# 31. Pruebas reales completadas

## 31.1 Papalote

Se comprobaron en modo read-only:

```text
Papalote 2 días
HTTP 200
35 contactos

Papalote julio completo
2,709 contactos
28 páginas

Papalote 1-28 julio
2,417 contactos
25 páginas
2,417 contact.id únicos
0 duplicados de ID
```

Además:

```text
137 contactos con ad_fb_*
2 contactos con múltiples ad_fb_*
```

## 31.2 Alias

Validación completa:

```text
26 branches
26 aliases iventas_family
26 sucursal_id
26 canon Track
0 ambiguos
0 faltantes
0 destinos duplicados
```

## 31.3 Persistencia/orquestación

Se validaron con PostgreSQL real y cliente fake:

```text
COMPLETED:
26/26
nuevo canonical sustituye anterior

PARTIAL:
25/26
raw de página fallida preservado
canonical anterior sobrevive

FAILED:
0/26
canonical anterior sobrevive
```

## 31.4 Test suite

La regresión iVentas completa quedó en:

```text
128 tests passed
```

incluyendo:

```text
normalización
timezone
branch resolver
raw persistence
structured persistence
run lifecycle
branch sync
counters
full-run orchestrator
```

## 31.5 Canary real de red completa

Run local conservado:

```text
run_id:
20

period_key:
CANARY-IVENTAS-REAL-2026-08-10

date:
2026-08-10

canonical:
False

branches:
26/26

failed:
0

aliases:
26/26

aliases unresolved:
0
```

Contadores:

```text
contacts_received:
1,065

contacts_unique:
1,065

contacts_with_phone:
1,065

MX10_MATCHABLE:
1,058

NON_MX_OR_UNRESOLVED:
7

contacts_with_first_message:
605

contacts_with_any_tag:
318

contacts_with_meta_ad_tag:
281

contacts_with_multiple_meta_ad_tags:
2

raw pages:
30

raw incomplete:
0

structured contacts:
1,065

tag rows:
338
```

Auditoría:

```text
sum(raw.contacts_count) = 1,065
structured rows = 1,065
raw vs structured por branch = exacto
pagination chains = válidas
duplicate (branch_code, contact_id) = 0
row_hash inválidos = 0
same contact_id en >1 branch = 0
canonical count del period_key = 0
```

Run 20 debe conservarse como canary no canónico hasta que se decida su limpieza explícitamente.

---

# 32. Tests obligatorios y estado

## 32.1 Cliente HTTP

Cubrir:

```text
token faltante
200
400
403
404
429 + retry
500 + retry
503 + retry
timeout
paginación
cursor
```

## 32.2 Timezone

Cubrir:

```text
inicio local → UTC
fin local → UTC
milisegundos
createdAt UTC → Tijuana
firstMessageAt UTC → Tijuana
```

## 32.3 Persistencia

Cubrir:

```text
página repetida no duplica en run
contact.id repetido en mismo branch/run se bloquea
mismo contacto puede existir en diferentes runs
varios tags por contacto permitidos
mismo tag no se duplica dentro del snapshot
raw persiste antes del parse
contacts_count NULL permitido ante parse fallido
```

## 32.4 Canonicalidad

Cubrir:

```text
COMPLETED → puede canonicalizar
PARTIAL → no
FAILED → no
nuevo canonical sustituye anterior transaccionalmente
máximo 1 canonical por period_key
```

## 32.5 Semántica

Cubrir:

```text
contacto iVentas != lead automático
ad_fb_* != atribución histórica automática
multi-tag permitido
número internacional != inválido automático

Lead Meta observado:
requiere META_AD
requiere firstMessageAt
lead_date = created_date_local
multi-tag no multiplica leads
verificación Meta no elimina observación iVentas
```

La suite actual de iVentas tiene 128 pruebas verdes. Cualquier implementación adicional de la métrica derivada Meta debe agregar sus propios tests sin degradar esta regresión.

---

# 33. Criterios de aceptación V1

La integración iVentas Contactos V1 se considera técnicamente validada cuando mantiene:

```text
✓ secretos exclusivamente en backend

✓ cliente HTTP separado

✓ timezone validado

✓ paginación completa

✓ rate limit ≤ 40 rpm

✓ retries acotados

✓ raw pages persistidas antes del parse

✓ contacts_count auditable

✓ contactos snapshot persistidos

✓ firstMessageAt persistido

✓ tags snapshot persistidos

✓ relación multi-tag soportada

✓ ningún meta_ad_id se usa como atribución histórica automática

✓ teléfono internacional se conserva

✓ 26 aliases resueltos

✓ canonicalidad CRM funcional

✓ corrida parcial no reemplaza canonical

✓ corrida failed no reemplaza canonical

✓ dashboard no confunde contactos totales con leads

✓ permisos backend obligatorios para futuros endpoints

✓ regresión iVentas verde

✓ ninguna credencial existe en Git
```

El canary real run 20 satisface la integridad técnica de una corrida completa 26/26, pero no se promociona automáticamente a canónico ni sustituye métricas del dashboard.

---

# 34. Estado de implementación

Modelos:

```text
backend/app/models/marketing.py

MarketingIventasSyncRunORM
MarketingIventasRawPageORM
MarketingIventasContactORM
MarketingIventasContactTagORM
```

Exports:

```text
backend/app/models/__init__.py
```

Cliente:

```text
backend/app/integrations/iventas/client.py
```

Services:

```text
backend/app/services/marketing_iventas_service.py
backend/app/services/marketing_iventas_branch_service.py
backend/app/services/marketing_iventas_persistence_service.py
backend/app/services/marketing_iventas_structured_persistence_service.py
backend/app/services/marketing_iventas_run_lifecycle_service.py
backend/app/services/marketing_iventas_run_counters_service.py
backend/app/services/marketing_iventas_branch_sync_service.py
backend/app/services/marketing_iventas_run_sync_service.py
```

Migraciones:

```text
d5f8a1c2e904
→ seed iventas_family 26 aliases

fb26...
→ create marketing_iventas_* tables

c42...
→ raw has_more nullable

e91...
→ unique canonical por period_key

a41...
→ raw contacts_count nullable + CHECK >= 0
```

Head local validado:

```text
a41...
```

La implementación del full-run orchestrator está congelada después de:

```text
unit tests
PostgreSQL canaries
real run 20
auditoría técnica
```

No modificar estos componentes por los hallazgos de ruido operativo del run 20; dichos hallazgos afectan la semántica de métricas derivadas, no la persistencia base iVentas.

---

# 35. Pendientes antes de automatización productiva / reemplazo de KPI

La persistencia base iVentas ya fue implementada y validada.

Antes de automatizarla productivamente o sustituir el KPI de Marketing debe resolverse explícitamente:

```text
1. comando/worker/scheduler productivo controlado
2. política de horario y repetición
3. política de canonicalización automática por period_key
4. observabilidad/alertas de runs PARTIAL/FAILED
5. persistencia Meta Ads completa, si se requiere
6. timezone canónico de reconciliación Meta
7. contrato/implementación de Lead Meta observado
8. activación explícita del reemplazo del KPI leads
9. contrato Lead/Contacto → Visita
10. contrato Visita → Venta para el funnel completo
```

No usar un endpoint Flask largo para resolver estos pendientes.

---

# 36. Fuera de alcance

No implementar dentro de este contrato base:

```text
atribución histórica/causal Meta → iVentas
persistencia completa Meta Ads
lead/contacto → visita
contacto → venta
ROAS por anuncio
eliminación del input manual
automatización diaria productiva
reemplazo automático de marketing_monthly_inputs.leads
```

La definición conceptual de “Lead Meta observado en iVentas” queda documentada aquí para congelar su semántica, pero su activación productiva requiere implementación/contrato derivado y pruebas propias.

---

# 37. Regla rectora

> iVentas es una fuente persistida y auditable de contactos CRM y de los tags observados en cada extracción.

> Un contacto iVentas no es automáticamente un lead publicitario.

> Un `ad_fb_<ad_id>` es un puente técnico hacia Meta y una relación observada en el snapshot, pero no una evidencia suficiente de atribución histórica.

> Para la métrica derivada “Lead Meta observado en iVentas”, `created_date_local` gobierna la fecha y `firstMessageAt` funciona como condición de interacción, sin convertir el tag en causalidad histórica.

> La verificabilidad actual del objeto Meta no debe borrar retrospectivamente una observación válida de iVentas.

> Una corrida incompleta nunca puede convertirse en snapshot canónico.

> Un canary real exitoso no se vuelve canónico automáticamente.
