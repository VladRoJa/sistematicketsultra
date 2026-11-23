# iVentas / Suite Ultra: vinculación de 32 plantillas Costa

## Alcance

Vincular **plantillas existentes en iVentas**; no crearlas de nuevo ni enviar mensajes.

Sucursales: PASEO_2000, CARROUSEL_TJ, PAPALOTE_TJ, SANTA_FE,
MISION_ENS, PABELLON_RTO, LOMA_BONITA.

- 299_n3 y 399_n2 (ocho variantes cada uno): las siete sucursales.
- 499_n1 (ocho variantes): seis sucursales, nunca LOMA_BONITA.
- 449_lb (ocho variantes): solo LOMA_BONITA.
- Propósito Suite REACTIVATION, categoría de origen Marketing.
- Variable prevista 1 → first_name.
- Dos casos para verificar manualmente: 2regresa_299_n3 y 7regresa_399_n2,
  cuyos textos fuente no muestran explícitamente [Nombre].

32 nombres y 168 combinaciones plantilla/canal esperadas (24 por club).

## Comportamiento

El script backend/scripts/marketing/link_costa_iventas_templates.py se ejecuta
dentro de la imagen iventas-template-upload-worker y utiliza únicamente el
archivo seguro de accesos existente. Recupera inventarios autenticados mediante
GET y valida el estado accepted por nombre y canal; no usa POST en iVentas.

Reutiliza el catálogo y la función save_template existente. Solo vincula cuando
todos los canales del alcance están aprobados; no modifica plantillas locales
con configuración distinta. La operación es idempotente. Estados:

- READY: plantilla nueva y aprobada en todos sus canales.
- ALREADY_LINKED: coincidencia exacta con configuración del catálogo.
- PENDING_APPROVAL: falta aprobación o el inventario no contiene algún canal.
- VERIFY_FIELDS: pendiente confirmar número y contenido de variables.
- CONFLICT: existe registro Suite distinto; revisión manual.

La vista previa no escribe. --apply requiere operador con permisos globales
y confirmación literal. Ningún modo crea campañas o envía WhatsApps.

## Operación (solo tras merge/despliegue autorizados)

Construcción de la imagen, sin iniciar un segundo worker permanente:

    docker compose --profile iventas-template-upload build iventas-template-upload-worker

Vista previa sin escrituras:

    docker compose --profile iventas-template-upload run --rm --no-deps iventas-template-upload-worker python -m scripts.marketing.link_costa_iventas_templates

Luego de revisar los resultados, aplicar solo con autorización operativa:

    docker compose --profile iventas-template-upload run --rm --no-deps iventas-template-upload-worker python -m scripts.marketing.link_costa_iventas_templates --apply --actor-id 47 --confirm VINCULAR_COSTA

El ID 47 debe corresponder al operador autorizado y vigente. El script
rechaza al actor que no tenga permisos globales de configuración.

Verificar después en Campañas V2 → Plantillas, canales y tarifas. Las dos
plantillas con variables pendientes se vincularán únicamente tras validar
su contrato real contra iVentas. La vinculación no demuestra entrega.

La prueba de envío posterior usará un solo número autorizado y una plantilla
representativa. No garantiza el funcionamiento individual de las otras 31.
