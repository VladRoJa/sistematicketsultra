# Issue #856 / Fase B — Composición de audiencia y presupuesto de referencia

## Contrato funcional

- Preview: dimensiones por teléfonos únicos deduplicados, separadas por sucursal y familia. Identidad múltiple o ausente marcada explícitamente; esto no altera el fingerprint ni la cohorte.
- Cotización preliminar: rango orientativo MXN a partir de todas las tarifas documentadas para los canales explícitos de una plantilla. Si falta alguna tarifa o hay lista legacy de canales universal, no hay rango.
- Preflight: estimación por lote y canal sobre contactos realmente enviables tras blacklist y exclusiones. Versión de tarifa, origen documental y precio unitario visibles.
- Si algún lote no tiene tarifa, quedan destinatarios sin lote, o el preflight está bloqueado: total_estimated_mxn = null. Nunca presentar subtotal cotizado como costo total ni representar ausencia de precio como MXN 0.
- Tarifas: tabla append-only marketing_campaign_v2_cost_rate_revisions, con template_id, provider_channel_id, unit_cost_mxn Decimal, source_reference, usuario y valid_from UTC. Sin precios precargados ni cotizaciones supuestas de iVentas.
- Backend exige alcance global más capacidad de configuración para listar/registrar tarifas, y comprueba canal activo y plantilla compatible. Los datos de costos son estimados manuales, no facturas del proveedor.
- El presupuesto no modifica contratos de envío, fingerprints, campañas congeladas, sellos de idempotencia ni kill switch. La autorización de presupuesto obligatoria corresponde a la Fase D.

## Endpoints

- GET /api/marketing/campaigns-v2/dispatch/cost-rates (admin): revisiones históricas
- POST /api/marketing/campaigns-v2/dispatch/cost-rates (admin): nueva revisión con fuente y actor
- POST /api/marketing/campaigns-v2/preview: recipient_dimensions (agregados, sin teléfonos)
- POST /api/marketing/campaigns-v2/{id}/preflight: budget (read-only, con posible total nulo)

## Migración y validación

- Alembic e4b856c9170d, descendiente de c7e4a9b2d601. No transforma datos existentes y rollback rechaza eliminar historial de tarifas.
- Backend: permisos, revisión de precios, fuente, incompatibilidad de canal, Decimal, presupuesto completo/incompleto; PostgreSQL 16 real aislado.
- Angular: TypeScript, Node tests de rango preliminar y build de producción. Componentes HTML/TS/CSS separados.

## Separación de fases

Fase B no envía WhatsApps, no resuelve colisiones de sucursal o campañas cruzadas (Fase C), y no libera canales HELD ni cuotas de Meta (Fase D).
