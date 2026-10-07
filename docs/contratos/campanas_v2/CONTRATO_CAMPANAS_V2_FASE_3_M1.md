# Contrato Campañas V2 — Fase 3 / M1
## Foundation & Preflight

Estado: PENDIENTE DE IMPLEMENTACIÓN  
Gate de entrada: Fase 2 ACCEPTED y Fase 3 desbloqueada.  
Gate de salida: preflight determinístico, auditable y sin llamadas de creación al provider.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar **únicamente F3-M1**.

Está prohibido:

- llamar `POST /v2/broadcast`;
- activar envíos reales;
- programar campañas;
- implementar retries de creación;
- adelantar M2/M3.

Antes de tocar código:

1. inspeccionar `main`;
2. confirmar que existe descarga separada de:
   - cohorte congelada;
   - lista para envío;
3. confirmar blacklist Campaign V2;
4. revisar integración iVentas existente;
5. explicar un solo cambio mínimo y su prueba.

## 1. Objetivo

Construir la base segura que permita saber, **sin enviar nada**, exactamente:

- qué Campaign V2 se pretende enviar;
- cuántos recipients congelados tiene;
- qué supresiones dinámicas aplican;
- cuántos quedan enviables;
- cómo se agrupan por sucursal/channel;
- qué template se usaría;
- qué variables se construirían;
- qué recipients quedan bloqueados;
- cuántos provider campaigns serían necesarios;
- qué fingerprint representa ese plan.

M1 termina cuando Suite puede producir un plan que un humano pueda revisar y comparar contra la descarga de lista para envío.

## 2. Estado de partida obligatorio

Main debe conservar:

- Campaign V2 recipients congelados;
- evidence congelada;
- blacklist global incremental;
- export de cohorte congelada exacta;
- export de lista para envío;
- Fase 2 provider history/stats;
- Funnel/Activos/Vencidos ya resueltos antes de Freeze.

M1 no modifica la semántica de audiencia.

## 3. Invariantes de audiencia

### 3.1 Cohorte congelada

Es inmutable y nunca se recalcula.

No consultar en preflight:

- socios vencidos;
- socios activos;
- Funnel;
- tariff classifier para decidir pertenencia;
- Historical Targeting;
- provider history para decidir pertenencia.

### 3.2 Sendable projection

Debe existir una única abstracción backend reutilizable para:

`frozen recipients -> current safety suppressions -> sendable recipients`

Actualmente la supresión dinámica aprobada es blacklist.

La descarga "Lista para envío" y el preflight deben reutilizar esa misma lógica o demostrar equivalencia por contrato/pruebas.

No mantener dos filtros blacklist independientes.

## 4. Investigación obligatoria antes de crear entidades

Inspeccionar:

- `backend/app/services/marketing_iventas_service.py`
- `backend/app/services/marketing_iventas_branch_service.py`
- modelos `MarketingIventas*`
- `MarketingIventasContactORM.channel_id`
- aliases/canonicalidad de sucursales;
- caso Tecnológico / tecnologico-2 / TEC_MXL;
- provider binding actual de Campaign V2;
- delivery legacy;
- permisos Marketing actuales.

Responder con evidencia del repo:

1. ¿channel_id observado es estable por sucursal?
2. ¿una sucursal puede tener más de un channel activo?
3. ¿existe fuente oficial/canónica de channels?
4. ¿el campo `CampaignV2ORM.provider_campaign_id` actual es solo histórico/single-binding?
5. ¿qué piezas legacy siguen siendo compartidas y no deben borrarse?

No inventar respuestas.

## 5. Modelo 1:N obligatorio

La arquitectura debe soportar:

```
MarketingCampaignV2ORM
      1
      |
      N
MarketingCampaignV2ProviderCampaignORM
```

El nombre exacto puede variar si el repo ya contiene una abstracción equivalente.

Cada child provider campaign debe poder representar como mínimo:

- id interno;
- campaign_v2_id;
- provider;
- sucursal o clave canónica de dispatch;
- provider_channel_id resuelto;
- template/configuración congelada;
- recipient_count planificado;
- dispatch_fingerprint;
- idempotency_key o identidad equivalente;
- estado interno;
- provider_campaign_id nullable;
- created/submitted metadata;
- created_by/submitted_by cuando aplique;
- error/supportRef sanitizado cuando aplique.

No usar el campo único del padre para representar N channels.

## 6. Channel binding

No hardcodear channelId en Angular ni services.

Si el repo no tiene una fuente canónica estable, M1 puede crear persistencia dedicada de binding.

Un binding debe contemplar al menos:

- provider;
- sucursal Suite o clave canónica;
- provider_channel_id;
- estado activo;
- metadata/auditoría;
- vigencia si es necesaria.

La API del navegador no debe poder sustituir arbitrariamente `provider_channel_id`.

Angular selecciona una configuración permitida; backend resuelve el channel real.

## 7. Template catalog

M1 debe investigar si existe endpoint oficial confirmado de iVentas para listar templates.

Si no existe evidencia:

usar catálogo administrado en Suite.

Contrato mínimo:

- provider;
- template_name;
- label negocio;
- activo;
- purpose(s) sugeridos/permitidos si aplica;
- variables requeridas;
- compatibilidad con channels si aplica;
- metadata suficiente para snapshot de dispatch.

No hardcodear templates en Angular.

No implementar media en M1.

## 8. Variables por recipient

Backend construye vars.

El template debe poder declarar un mapping de variables, por ejemplo:

```
1 -> first_name
2 -> expiration_date
3 -> amount
```

La entidad exacta puede ser JSON controlado o modelo normalizado según el repo.

Reglas:

- si falta variable requerida, recipient/batch queda bloqueado;
- no mandar valores inventados;
- no montar `vars[]` manualmente en HTML;
- no aceptar vars arbitrarias del navegador como autoridad.

El primer nombre debe reutilizar la semántica vigente del export si se usa como variable.

## 9. Permiso de envío

M1 debe identificar o crear una capacidad explícita de envío.

No asumir que `can_edit_inputs` equivale automáticamente a permiso de enviar.

Debe distinguirse:

- consultar/crear campañas;
- administrar configuración;
- preflight;
- enviar.

Backend es autoridad.

Si el modelo de permisos vigente no permite una capacidad específica sin una refactorización amplia, documentar el diseño mínimo y protegerlo por pruebas antes de M2.

## 10. Preflight

Crear un servicio backend puro de dispatch/preflight.

Input autorizado conceptual:

- campaign_v2_id;
- template/config seleccionada;
- modo inmediato para M1;
- ningún phone list;
- ningún channelId arbitrario.

Output conceptual:

```json
{
  "campaign_id": 123,
  "frozen_count": 578,
  "suppressed": {
    "blacklist": 3
  },
  "sendable_count": 575,
  "batches": [
    {
      "sucursal": "X",
      "channel_binding_id": 9,
      "recipient_count": 200,
      "ready": true
    }
  ],
  "blocked": {
    "missing_channel": 0,
    "missing_required_variable": 0,
    "invalid_phone": 0
  },
  "dispatch_fingerprint": "...",
  "ready": true
}
```

La forma exacta puede cambiar, la semántica no.

## 11. Fingerprint de dispatch

El fingerprint debe cambiar si cambia cualquiera de:

- conjunto sendable de phones/recipient ids;
- blacklist vigente que altera ese conjunto;
- grouping sucursal/channel;
- channel binding;
- template;
- variables resultantes relevantes;
- configuración de dispatch.

No debe cambiar por:

- orden accidental de filas;
- metadata irrelevante;
- paginación UI.

El fingerprint es backend-generated.

## 12. Paridad obligatoria con Lista para envío

M1 debe demostrar por prueba que:

`phones(preflight sendable plan) == phones(sendable export)`

para el mismo estado de blacklist/configuración.

La comparación debe ser de conjuntos/identidades normalizadas, no solo conteos.

Un conteo igual con teléfonos distintos es fallo.

## 13. Multisucursal en M1

M1 no envía, pero sí debe planear correctamente multisucursal.

Casos:

- una sucursal -> un channel -> un batch;
- varias sucursales -> N batches;
- dos familias misma sucursal/template -> no forzar batches separados por familia;
- recipient sin sucursal resoluble -> bloqueado, nunca reasignado;
- channel faltante -> batch no ready;
- un channel no puede venir del navegador como sustitución libre.

## 14. Estados internos

M1 puede definir estados base de provider campaign/dispatch.

Mínimo conceptual:

- PREPARED / READY;
- BLOCKED;
- SUBMITTING;
- SUBMITTED;
- PROVIDER_ERROR;
- RECONCILIATION_REQUIRED.

M1 no debe producir SUBMITTING/SUBMITTED en ejecución real.

Se definen ahora para evitar migraciones semánticas posteriores.

## 15. Idempotencia

M1 define la identidad que M2 usará.

Debe existir una llave única o mecanismo equivalente que impida dos operaciones concurrentes para el mismo:

- Campaign V2;
- batch/channel;
- configuración/fingerprint.

No confiar en deduplicación del proveedor.

## 16. Endpoints permitidos en M1

Se permiten endpoints read/preflight/config, por ejemplo:

- listado de templates;
- channel bindings;
- preflight dispatch.

No se permite ningún endpoint que realice POST al provider.

Un endpoint llamado `send`, `submit`, `dispatch` o equivalente no debe ejecutar side effects externos en M1.

## 17. Frontend M1

La UI puede mostrar:

- botón/acción "Preparar envío" o "Revisar envío";
- frozen count;
- blacklist/supresiones;
- sendable count;
- batches por sucursal/channel;
- template;
- bloqueos;
- fingerprint/version;
- links a:
  - Descargar cohorte congelada;
  - Descargar lista para envío.

No mostrar botón real de "Enviar" habilitado.

Si se dibuja anticipadamente, debe estar explícitamente deshabilitado por backend state/feature contract, no solo CSS.

## 18. Seguridad

- integration key nunca se usa en M1;
- no provider POST;
- no secretos en frontend;
- no teléfonos completos en logs generales;
- no payload completo en logs;
- no DB mutation de recipients congelados;
- no eliminación de blacklist;
- no eliminación de export manual.

## 19. Persistencia y migraciones

Toda tabla/campo nuevo usa Alembic.

Antes de crear tabla nueva:

- revisar si existe modelo equivalente;
- no acoplar V2 a semántica incompatible de V1;
- conservar histórico actual.

No drop de tablas legacy.

## 20. Pruebas mínimas M1

### Sendable projection

- freeze 5 / blacklist 0 -> sendable 5;
- freeze 5 / blacklist 2 -> sendable 3;
- frozen export sigue conteniendo 5;
- sendable export contiene 3;
- preflight contiene exactamente esos 3.

### Channel

- sucursal con binding válido;
- sucursal sin binding;
- binding inactivo;
- alias Tecnológico correcto;
- navegador no puede inyectar channelId.

### Template/vars

- template inexistente;
- template inactivo;
- variable requerida presente;
- variable requerida faltante;
- nombre compuesto según helper vigente.

### Multisucursal

- dos sucursales -> dos batches;
- misma sucursal con varias familias -> mismo batch cuando template/channel coinciden;
- phone-only sin sucursal -> blocked.

### Fingerprint

- determinístico;
- cambia con blacklist;
- cambia con template;
- cambia con channel;
- cambia si cambia phone set;
- no cambia por orden.

### Permisos

- lectura sin permiso;
- preflight sin permiso;
- scope parcial;
- configuración global protegida.

## 21. Criterio de aceptación M1

M1 es ACCEPTED solo si:

1. no existe provider POST en el flujo;
2. Campaign V2 soporta conceptualmente/persistentemente 1:N provider campaigns;
3. channel resolution es canónica;
4. templates/vars no están hardcodeados en Angular;
5. permiso de envío/preflight está definido;
6. preflight reconstruye desde frozen recipients;
7. blacklist se aplica como supresión dinámica explícita;
8. frozen export permanece exacto;
9. sendable export permanece disponible;
10. preflight y sendable export coinciden por phone set;
11. multisucursal produce N batches;
12. fingerprint/idempotencia quedan listos para M2;
13. pruebas específicas y regresión Campaign V2 pasan.

No ejecutar un envío real para aceptar M1.

## 22. Cierre documental M1

Al aceptar:

- actualizar este archivo a `ACCEPTED`;
- documentar decisiones finales de channel/template/modelo;
- registrar migraciones y endpoints;
- dejar M2 como `DESBLOQUEADO`.

No empezar M2 dentro de la misma conversación.

## 23. Prompt de arranque para una conversación nueva

```
Estamos implementando únicamente Campañas V2 Fase 3 / M1 — Foundation & Preflight.

Lee docs/contratos/campanas_v2/CONTRATO_CAMPANAS_V2_FASE_3_M1.md como contrato autosuficiente y revalida main antes de cambiar código.

Regla crítica: M1 NO puede llamar POST /v2/broadcast ni enviar mensajes reales.

Debes preservar dos descargas:
1) cohorte congelada exacta;
2) lista para envío con supresiones vigentes.

Diseña primero sendable projection compartida, channel/template resolution, modelo Campaign V2 1:N ProviderCampaign, permiso explícito, preflight y dispatch fingerprint.

Trabaja un cambio/prueba a la vez y no adelantes M2.
```
