# BI — Rachas de mensualidades consecutivas (paquete exploratorio V1)

## Estado y alcance

Este paquete habilita **diagnostico de cobertura**, **reconstruccion con evidencia
de mensualidades cubiertas** y **exportacion Excel**. No extrae ni cambia Gasca,
no altera datos de Suite Ultra ni implementa la promocion en el sistema de
cobranza. No asignar descuentos reales hasta cotejar la fuente y validar
manualmente 20 socios representativos.

### Hallazgo de esquema (GitHub)

- `venta_total_snapshot_rows`: PIN, fecha de transaccion, folio, producto,
  descripcion, estatus, monto. **No tiene inicio/fin de vigencia mensual**.
- `socios_activos_snapshot_rows`: ID Socio, PIN, ultimo pago, vencimiento.
  **No es un ledger historico**.
- `socios_vencidos_cartera`: episodios de vencimiento por PIN/sucursal,
  no pagos mensuales continuos.
- `ventas_nuevos_socios_detalle_snapshot_rows`: fecha pago/renovacion,
  pero el informe es de nuevos socios; no garantiza todas las renovaciones.

Por tanto, no convertir la cantidad de filas de Venta Total en una racha.

## Paso 1: perfil real de cobertura (SOLO LECTURA)

En un backend autorizado, con DB accesible:

```bash
cd backend
python -m scripts.ops.profile_member_streak_sources --output /tmp/fuentes_rachas.json
```

Produce meses con snapshots, cardinalidad, canonicalidad cuando existe, y
una muestra agregada por tipo/estatus de un snapshot reciente de Venta Total.
Las fechas de snapshots **no demuestran** cobertura de los socios desde 2020.
No descarga archivos, no imprime PIN, nombre ni telefono, y hace rollback.

Antes de dar por completa la cobertura, contrastar manualmente contra
la fecha minima y maxima **de las transacciones** de un reporte pertinente,
porque `business_date` no necesariamente es la fecha del movimiento.

## Paso 2: contrato de entrada al motor

Necesitamos un reporte de pagos/vigencias con conversion auditable a una
fila por **mes de servicio pagado**. No usar mes calendario de la fecha
de transaccion sin comprobar el periodo que esta pagando. Las membresias
del dia 15 al dia 14 deben seguir un criterio unico del inicio del ciclo.

**padron.csv** (desde activos y vencidos, tras resolver duplicados)

```csv
id_socio,pin,sucursal,estado,historial_completo,reinicio_promocion
1001,123,VILLAS DEL REY,VENCIDO,NO,NO
1002,456,SAN LUIS,ACTIVO,NO,NO
1003,789,SENDERO,NUEVO,NO,NO
```

**meses_pagados.csv** (solo cuando exista evidencia de servicio pagado)

```csv
id_socio,pin,sucursal,mes_cubierto,estado_evidencia,fuente_ref
1001,123,VILLAS DEL REY,2020-01,PAGADO,folio-001
1001,123,VILLAS DEL REY,2020-02,PAGADO,folio-002
1002,456,SAN LUIS,2026-11,PAGADO,folio-003
```

- `id_socio` es preferido para unir cambios de sucursal. Cuando falta,
  solo se permite `sucursal + pin`; colisiones exigen resolucion.
- `mes_cubierto` debe representar una mensualidad efectiva **verificada**.
  Varias filas del mismo mes no suman varios meses.
- `fuente_ref` debe permitir auditar el folio o registro; nunca generar
  rachas desde resumenes de ventas sin vigencia.
- `historial_completo=SI` es una afirmacion de calidad que debe provenir
  de verificacion real desde el alta; no marcarlo automaticamente.
- `reinicio_promocion=SI` significa que la fila representa el primer
  mes de un **nuevo episodio** despues de romper la racha promocional.
  No es una bandera permanente para futuras mensualidades.

## Paso 3: exportar simulador de cohortes

```bash
cd backend
python -m scripts.ops.export_member_streaks \
  --roster /ruta/padron.csv \
  --coverage /ruta/meses_pagados.csv \
  --as-of 2026-11-07 \
  --output /tmp/rachas_bi.xlsx
```

Cuatro hojas:

- **Reglas:** cuatro brechas y precios editables: 1/$599, 4/$499,
  7/$399, 10/$299. La configuracion es un **supuesto**, no tarifa aprobada.
- **Detalle:** racha maxima observada, vigente, nivel inicial y calidad,
  sin nombres, telefonos ni correos. Contiene claves internas: acceso
  restringido a operadores/BI autorizados.
- **Cohortes_BI:** totales y monto simulado por estado y brecha.
- **Calidad:** cobertura, registros sin enlace, duplicados, evidencia parcial.

Los precios se recalculan en Excel al abrir el archivo; `openpyxl` no
calcula formulas por si mismo. El motor no guarda estado promocional
posterior a la simulacion: las renovaciones reales futuras requieren
auditoria transaccional y regla explicita de tolerancia al vencimiento.

## Regla aprobada de negocio

1. Vencido entrando por primera vez: **mejor racha historica** verificada.
2. Activo entrando: racha consecutiva vigente.
3. Socio nuevo: nivel 1.
4. Tras una interrupcion luego de habilitar promocion: nivel 1 en su
   regreso; la racha historica deja de aplicar.
5. El umbral se determina por meses pagados continuos, no por meses desde
   fecha de alta, ni por cantidad de transacciones.

## Bloqueos para terminar validacion real

1. Ejecutar el perfil read-only en un entorno autorizado y registrar fechas
   reales, canonicalidad y vacios por mes.
2. Localizar reporte que detalle **vigencias/mensualidades cubiertas**.
   Si Venta Total es la fuente, documentar productos, estatus y forma
   de resolver vigencia a partir de contrato; no asumir.
3. Cruzar 20 socios sinteticos primero y luego 20 casos reales contra Gasca
   bajo el canal autorizado, incluyendo pago anticipado, cancelacion,
   migracion de sucursal, varios folios en un mes, huecos y reincidencia.
4. No usar los montos estimados en una campaña real si la calidad es
   PARCIAL_OBSERVADO o SIN_EVIDENCIA.

No se hace merge, despliegue, migracion, cambio de permisos ni envio de
campañas dentro de este paquete.
