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
- Meses de cobertura **futuros** (prepagos) se ignoran al calcular
  la racha hasta la fecha de corte; se cuentan aparte en Calidad.
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


## Hallazgo 2026-11-07: Gasca permite re-descargar histórico enriquecido

Se comparó el RAW almacenado de diciembre de 2024 (upload 8692)
con una descarga manual actual del mismo mes desde Gasca, sin difundir
datos de socios:

| Métrica | RAW anterior | Descarga actual |
| --- | ---: | ---: |
| Movimientos con folio | 68,319 | 68,463 |
| Movimientos con PIN | 0 | 43,557 |
| Movimientos con IDSocio | 0 | 43,557 |
| Movimientos candidatos a membresía identificada | 0 | 25,313 |
| Folios distintos coincidentes | — | 62,763 |

Esto invalida la hipótesis de que los reportes anteriores a 2025 no
tienen forma de identificar socios. **El XLSX que entrega hoy Gasca para
un rango de 2024 sí incluye IDSocio, PIN y Tipo**, aunque el archivado
en Warehouse no. Los datos originales de Gasca tienen 32 encabezados
(incluidos RFC, Razon Social, Telefono, Api e IDSocio), frente a las
25 columnas de los archivos más antiguos.

La comparación prueba el caso diciembre de 2024; NO demuestra que
2023 y todos los meses de 2024 tengan IDs. Se verifica mes a mes.

### Descargador histórico Playwright (RAW FIRST)

El script `app.warehouse.backfill.redownload_venta_total_history`
**reutiliza** login de Gasca y los helpers de UI del runner existente,
pero evita `_limpiar_excel_inplace`, que volvería a serializar el Excel
y podría convertir folios/IDSocio largos. Nunca escribe base de datos ni
cambia canonicalidad.

Primero plan, sin iniciar sesión:

```bash
cd backend
python -m app.warehouse.backfill.redownload_venta_total_history \
  --from-month 2024-12 --to-month 2024-12
```

Piloto de solo **un mes** en entorno autorizado:

```bash
cd backend
python -m app.warehouse.backfill.redownload_venta_total_history \
  --from-month 2024-12 --to-month 2024-12 --execute
```

Tras verificar el piloto y la cuenta de acceso autorizado, se puede
planificar un lote pequeño (no es necesario ejecutar meses completos
en el primer intento):

```bash
cd backend
python -m app.warehouse.backfill.redownload_venta_total_history \
  --from-month 2024-01 --to-month 2024-12 --limit 3 --execute
```

Los archivos se guardan localmente en
`backend/data/backfill/gasca_venta_total_enriched/YYYY-MM/`:

- `venta_total_YYYY_MM_gasca_original.xlsx`: XLSX original de Gasca.
- `venta_total_YYYY_MM_gasca_original.json`: manifiesto con hash,
  fecha solicitada, número de filas y conteos de PIN/IDSocio,
  **sin información de personas**.

Un lote repetido que encuentre un XLSX y manifiesto con SHA idéntico
se salta. Archivos incompletos o de contenido inesperado **no se
sobrescriben**. El flag `--execute` es obligatorio para usar Playwright.
Entre peticiones se deja un mínimo de 2 segundos.

**Seguridad:** los XLSX sí contienen PII (PIN, ID Socio, nombre, teléfono,
RFC): conservar fuera del repositorio, limitar permisos y retención,
no enviarlos por logs ni adjuntarlos a PR/CI. Solo operadores autorizados.

**Gate:** el resultado es un RAW aislado. Antes de integrar a Warehouse
se necesita definir ingesta no canónica, preservar `id_socio` en esquema
(si se elige estructurar), deduplicar folios/renglones y verificar
periodos pagados. El parser de Venta Total hoy conserva PIN y Tipo
pero no `id_socio` en sus modelos persistidos. **No usar las descargas
para emitir precios automáticamente.**



## 2026-11-07: lote histórico recuperado; consolidación local

El operador recuperó diciembre de 2020, luego 2020-01 a 2020-12
(8 nuevos, 1 omitido, 3 meses sin filas: abril-junio 2020), el 2021 y
2022 completos, y continuó con históricos hasta el lote final de
34 meses: 33 descargados, 1 error. **No asumir que todos los meses
están íntegros**: el último mes fallido se identifica escaneando el
directorio local. Un mes faltante no implica baja del socio.

### Consolidación de señales comerciales, SIN crear vigencias

Desde **PowerShell** en `SuiteUltra-BI\\backend`, tras actualizar
la rama del PR #1228:

```powershell
git pull
.\\.venv\\Scripts\\python.exe -m scripts.ops.consolidate_gasca_member_sales --from-month 2020-01 --to-month 2026-10
```

No requiere credenciales ni conexión a PostgreSQL. Revisa manifiestos,
valida SHA-256 del RAW original, lee PIN e IDSocio como texto, identifica
transacciones con `Tipo` compatible con membresías, y elimina
renglones exactamente idénticos dentro de la misma fuente. **El hecho
de ser `Contrato` o `Mensual sin contrato` NO prueba vigencia ni pago
correspondiente a ese calendario.** Cada registro queda marcado
`MOVIMIENTO_SIN_VIGENCIA`.

Produce dos archivos locales **fuera de Git**:

- `data/backfill/gasca_venta_total_enriched/consolidated/member_sales_202001_202610.sqlite`
  contiene `purchase_events` y vista `member_month_sale_signals`, con
  `id_socio`, PIN, folio, tipo, fecha, estatus y descripción. **Confidencial**.
- `.../member_sales_202001_202610_quality.json`: reporte agregado
  por mes, clasificaciones, errores, meses sin fuente y conteos. Este
  reporte no incluye PII.

El resumen `[SUMMARY]` contiene `meses_ok`, `meses_sin_verificar`,
`movimientos_candidatos_distintos`, `ids_socios_distintos`, y
`socios_mes_sucursal`. Se permite repetir con `--replace` para
**reconstruir solo la SQLite local**, jamás borrar RAW ni alterar
Warehouse. En el CSV/Excel de rachas no debe aparecer ninguna
`mes_cubierto=PAGADO` inventada desde esta vista.

Próximo gate: definir por producto (mensual, anual, semestral, domiciliado,
convenio, reactivación, abono, cortes) cómo se atribuye cada cobro al
**intervalo de servicio** y contrastar una muestra de socios contra
Gasca antes de usar la simulación de precios.


### Resultado real de consolidación comunicado por operador (2026-11-07)

El consolidador local recorrió 82 meses (2020-01 a 2026-10):
**78 meses OK**, faltan `2020-04`, `2020-05`, `2020-06`
(descargas parciales de reportes sin filas válidas) y `2024-09`
(sin archivo verificado). La SQLite tiene **1,474,919 movimientos
de membresía candidatos distintos**, **242,784 IDSocio observados**
y **1,428,327 agrupaciones socio-mes-sucursal**. Estas cantidades
NO equivalen a vigencias mensuales, cuentas activas o miembros
únicos certificados.

Septiembre 2024 es un hueco recuperable importante para continuidad:
```powershell
.\\.venv\\Scripts\\python.exe -m app.warehouse.backfill.redownload_venta_total_history --from-month 2024-09 --to-month 2024-09 --execute
```
Si se recupera, reconstruir la SQLite local con salida previa
reemplazable explícitamente (NO toca RAW ni PostgreSQL):
```powershell
.\\.venv\\Scripts\\python.exe -m scripts.ops.consolidate_gasca_member_sales --from-month 2020-01 --to-month 2026-10 --replace
```

Para examinar la taxonomía de ventas y clases de contratos SIN
identificadores personales, en la misma carpeta `backend`:
```powershell
.\\.venv\\Scripts\\python.exe -m scripts.ops.profile_gasca_member_sales
```

La herramienta abre SQLite `mode=ro`, informa distribución
`tipo/estatus`, duración o cobro recurrente sugeridos por
descripción y repeticiones de venta en un mes, pero **jamás**
convierte una venta en mes de vigencia. Este es el gate previo a
resolver vigencias por tipo de producto y constancia efectiva de pago.
