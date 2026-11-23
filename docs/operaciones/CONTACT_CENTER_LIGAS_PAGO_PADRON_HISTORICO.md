# Contact Center — padrón histórico para ligas de pago

## Propósito

Cubrir socios vencidos que no aparecen en el último snapshot de `socios_activos`
ni en `ventas_nuevos_socios_detalle`. El reporte de vencidos de Gasca contiene
nombre, PIN, teléfono y sucursal, pero **no** el ID Socio. Se usa el CSV
`Ultra_Gym_Padron_Unificado_2026-10-31(1).csv` como evidencia de identidad
para recuperar el ID por combinación **nombre + PIN**. La sucursal es
informativa, no requisito: puede haber cambios de club.

**No confundir estado actual con el del CSV:** `Activo/Vencido` en el CSV
corresponde exclusivamente a su fecha de corte (31 de octubre de 2026).
No se altera el estado operativo de los socios ni otros módulos.

## Cobertura y validación del CSV recibido

- 243,462 filas, 243,462 ID Socio distintos.
- 209,737 vencidos y 33,725 activos al corte.
- 0 conflictos de ID entre pares normalizados nombre + PIN, incluso
  con eliminación de acentos, puntuación y ceros a la izquierda del PIN.
- No incluye teléfono: la búsqueda telefónica se resuelve en el padrón de
  vencidos de Warehouse, y solo entonces se realiza el cruce por nombre + PIN.
- La cobertura real depende de qué vencidos existan en el archivo y de cómo
  coincidan sus nombres/PIN; no hay garantía de 100 %.

## Seguridad y reglas

1. Buscar en `socios_vencidos_cartera` por nombre, PIN o teléfono completo.
2. Resolver el par de identidad en el **único batch activo** importado desde
   CSV, validado por `name_key, pin_key`.
3. Si el ID es único y numérico, entregar la liga
   `https://pago.ultragym.com.mx?sid=ID_SOCIO`.
4. Si no coincide, **mostrar socio sin ID ni liga** y sin botones de copia.
5. Mantener las consultas a snapshots canónicos de activos y altas para socios
   ausentes de la cartera de vencidos. No deducir ID por teléfono o PIN aislado.
6. Máximo 20 resultados; prevalecen vencidos con ID confirmado.
7. El CSV completo nunca debe incorporarse a Git, publicarse en `/uploads`,
   ni copiarse a volúmenes expuestos por Nginx. Se archiva el original con hash
   en un volumen privado exclusivo del backend. Las versiones anteriores
   permanecen inmutables y auditables.
8. Se preservan los guards de Contact Center: únicamente operadores
   autorizados; no se amplía a gerentes ni a otros módulos.

## Operación segura (solo tras autorizar despliegue e importación)

**La migración es necesaria.** Tras desplegar la rama mergeada:
`docker compose exec -T backend flask db upgrade`

El servidor debe disponer del CSV original en el directorio privado del host,
por ejemplo `private/contact-center-payment-reference/incoming/padron.csv`.
No colocarlo en `uploads/` ni en el repositorio. El backend monta ese
directorio como `/app/runtime/payment-reference` solamente para sí mismo.

Primero inspeccionar sin mutaciones:

```bash
docker compose exec -T backend python scripts/import_contact_center_payment_reference.py \
  --file /app/runtime/payment-reference/incoming/padron.csv \
  --cutoff 2026-10-31 --dry-run
```

Confirmar que el conteo esperado es 243462, que no hay conflictos y que el
hash corresponde al archivo aprobado. **Solo con autorización expresa**,
importar y activar la versión:

```bash
docker compose exec -T backend python scripts/import_contact_center_payment_reference.py \
  --file /app/runtime/payment-reference/incoming/padron.csv \
  --cutoff 2026-10-31 \
  --archive-dir /app/runtime/payment-reference/archive --activate
```

Para una versión futura, repetir preflight; la importación y el cambio de batch
activo son transaccionales. Ejecutar fuera del proceso web. El hash impide
registrar por segunda vez el mismo contenido. No purgar versiones
históricas automáticamente.

## QA de aceptación

- Buscar un vencido conocido por PIN, nombre y teléfono.
- Confirmar el mismo ID y la misma liga en cada vía cuando el teléfono
  corresponda al vencido.
- Confirmar que un nombre parecido con distinto PIN **no** recibe liga.
- Confirmar que un socio sin evidencia muestra «ID no verificado».
- Confirmar permisos: gerente no obtiene resultados de ligas.
- Confirmar que no se afectan los resultados previos de activos y altas.
- Revisar velocidad para búsquedas frecuentes y consultas de nombres comunes.
- Verificar versiones del padrón, hash e integridad de la migración.

**Estados separados:** código integrado ≠ migración aplicada ≠ CSV importado
≠ batch activado ≠ validación con socios reales.
