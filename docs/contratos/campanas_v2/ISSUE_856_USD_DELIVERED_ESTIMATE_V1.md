# Campaign V2 — precio automático USD por mensaje entregado (v1)

## Decisión de producto (15/oct/2026)

- Precio general observado en reporte iVentas México: **US$0.0542 por mensaje entregado**. Es referencia declarada por el operador, no un compromiso contractual de precio futuro.
- El costo **no es un requisito manual** de aprobación. No se configuran 26 tarifas. No se inventan conversiones FX.
- Antes del envío: **máximo teórico** = destinatarios aptos × US$0.0542. No es importe a pagar.
- Después del envío: el costo real se obtiene de **entregas cobradas / total reportado por iVentas**. `accepted`, `sent` y `viewed` no son sinónimos de entrega facturable. Si no hay evidencia confirmada, mostrar **sin costo real confirmado**, nunca contabilizar el máximo estimado como pagado.
- Versionado: `IVENTAS_MX_DELIVERED_USD_V1`, cuatro decimales y una huella SHA de versión, precio y cohorte. Si cambia el precio, debe cambiar la versión y pasar revisión; aprobaciones anteriores no se reescriben.

## Seguridad y persistencia

- Ruta de lectura `/preflight`: entrega `budget_usd` automático y conserva `budget` MXN histórico para clientes antiguos.
- Nueva aprobación `/dispatch/approval` con `pricing_currency=USD`; no acepta `expected_total_mxn`. El servidor calcula la cantidad en USD. El operador confirma destinatarios y la misma huella de la revisión.
- Mecanismo de reserva por canal/portafolio, candados PostgreSQL, expiración, HELD, permisos, confirmaciones y kill switches **sin cambios**.
- Migración `a856usd1015`: `approved_estimated_usd NUMERIC(14,4)`, antiguo MXN ahora nullable; ambos importes son mutuamente excluyentes. Las aprobaciones antiguas siguen expresadas en MXN. Una aprobación USD nueva conserva precio/basis/version en el manifiesto.
- La materialización y ejecución vuelven a comprobar el precio, el manifiesto y la huella; una aprobación histórica MXN conserva su ruta de lectura y validación.
- Un costeo estimado nunca concede permisos, no libera retenciones ni envía mensajes.

## Orden obligatorio de despliegue

**No implementado en producción con este PR.** Se necesita autorización de promoción y revisar los heads reales de Alembic. Debido a la nueva columna, ejecutar la migración en una ventana coordinada antes de exponer el nuevo backend; hacerlo mediante la imagen correspondiente, no por archivos modificados manualmente en el servidor. Luego reconstruir backend y frontend, con ambos switches OFF. Verificar `flask db current` y revisar únicamente GET / preflight sin enviar campañas.

El usuario decidió operar sin respaldo nuevo; ello **no elimina** los riesgos de recuperación. No ejecutar una migración automáticamente ni prometer rollback reversible después de aprobaciones USD. No usar `flask db downgrade` si existen aprobaciones USD.

## Evidencia

- Unit tests de estimación con 0, 278 y 1,000 entregas.
- SHA cambia al modificar la cohorte.
- Pruebas sintéticas de reserva y manifiesto (tanto USD como MXN).
- Test de migración PostgreSQL 16 que conserva filas MXN, rechaza filas sin moneda/mezcladas y bloquea downgrade destructivo.
- GitHub Actions con permisos aislados, flags de provider OFF.
