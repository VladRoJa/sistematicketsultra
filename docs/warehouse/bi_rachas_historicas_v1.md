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


### Cierre de septiembre 2024 y taxonomía de contratos (2026-11-07)

La descarga manual de septiembre 2024 se validó por fecha y estructura
y se integró SOLO a la SQLite local mediante manifiesto SHA-256.
El resumen comunicado fue **79/82 meses verificados**: faltan
2020-04, 2020-05, 2020-06, que son huecos de fuente desconocidos
(no interrupciones de membresía acreditadas). Hay **1,503,911**
movimientos de membresía identificada, **243,730** IDSocio históricos
y **1,456,750** grupos socio-mes-sucursal. Ni estas cantidades ni la
ausencia de un movimiento son equivalentes a vigencia pagada.

En el cruce `Tipo` × descripción:
- **CONTRATO**: 821,015 movimientos; 352,736 mencionan anualidad
  o 12 meses, 511,941 domiciliación, 153,556 recurrencia.
  Los textos pueden solaparse: el plazo contractual no prueba
  un pago por adelantado ni 12 cobros liquidados.
- **MENSUAL SIN CONTRATO**: 594,168 movimientos, de los cuales
  122,691 mencionan convenio. También requiere acreditar el pago.
- **ANUALIDAD SIN CONTRATO**: 4,389, con 4,180 menciones
  explícitas de anualidad o 12 meses.
- **SEMANAL SIN CONTRATO**: 49,815. No convertir cuatro
  compras semanales en un mes calendario sin regla de ciclos.
- `CANCELADO` y `FACTURADO` requieren conciliación:
  no validar meses únicamente por estas etiquetas.

La SQLite incluye **42,171** socio-meses con varias transacciones,
**48,123** transacciones adicionales y **11,472** IDSocio vistos
en más de una sucursal. Los IDSocio no deben reasignarse a una nueva
identidad sin comprobar su alcance.

#### Diagnóstico adicional de continuidad de COMPRA (no vigencia)

En `backend`:

```powershell
git pull
.\\.venv\\Scripts\\python.exe -m scripts.ops.audit_gasca_purchase_cadence
```

Consulta solo la SQLite local en modo lectura; recorre cada IDSocio
internamente, sin emitirlo, y por cada `Tipo` informa socio-meses
con venta `ACTIVO`, los que registran compra al mes siguiente
(igual o distinto tipo) y los que no. Un mes de fuente ausente
(abril-junio 2020) o el fin de corte no cuenta como abandono.
**Tampoco cuenta como abandono la falta de otra compra para
una anualidad ya pagada:** estos son patrones de compra, no
cobertura de servicio. Nunca exportar sus resultados como
`mes_cubierto=PAGADO`.

#### Puerta a vigencias reales

Inspeccionar de manera restringida:
1. Reporte `Socios Activos`, que incluye `ID Socio`, último
   pago y fecha de vencimiento;
2. `Cargos Recurrentes`, que incluye `ID Socio`, `PIN`,
   fecha de inicio, próximo pago, meses pendientes y fecha
   fin contrato;
3. Evidencia de pago/estado efectivo por folio, cancelaciones
   y reembolsos; evitar confundir contrato con cobro.

Cotejar 20 casos representativos en ambiente autorizado: mensual,
domiciliado, convenio, anualidad prepagada, semestral, trimestral,
semanal, cancelación, cambio de sucursal, doble transacción,
pago anticipado y huecos de fuente. Crear intervalos pagados
solo cuando la fuente permita fecharlos con evidencia verificable.


## Paquete BI Excel de aprobación — V1 (2026-11-07)

El usuario aprobó entregar un Excel consultable de **dos universos**,
con `ID Socio` como clave principal:
1. **Activos:** todos los del reporte `Socios Activos` actual;
   mostrar solamente `Aplica KPI=Si`. El resto de los activos NO
   se convierte en vencido.
2. **Vencidos candidatos:** los `ID Socio` distintos de `Venta Total`
   no presentes en **ninguno** de los activos, con mejor racha histórica
   observada. El reporte `Socios Vencidos` del 1 al 7 de noviembre es
   solo una muestra; no representa la cartera vencida completa y no
   debe usarse como padrón principal. En la exportación histórica
   `Aplica KPI=NO DISPONIBLE` porque no existe esa columna en Venta
   Total; no afirmar elegibilidad comercial.

### Exportador local

El código `backend/scripts/ops/export_member_streaks_presentation.py`
recorre la SQLite ya consolidada en modo lectura y crea un .xlsx con
`Resumen`, `Activos`, `Vencidos` y `Reglas`. No sube información
personal, no consulta Warehouse ni altera snapshots.

En PowerShell, desde `SuiteUltra-BI\\backend`:

```powershell
git pull
.\\.venv\\Scripts\\python.exe -m scripts.ops.export_member_streaks_presentation --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" --as-of 2026-11-07 --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Propuesta_Rachas_Ultra.xlsx"
```

Ajustar `--active-xlsx` a la ruta del archivo local real; el Excel
no debe subirse a GitHub porque contiene nombre, PIN e ID Socio.
La salida a `data/backfill/gasca_venta_total_enriched` está
ignorada por Git y usa el paquete `XlsxWriter` ya presente en
`requirements.txt`.

**Interpretación de columnas:** los `1` mensuales representan
`compras observadas` con estatus de movimiento `ACTIVO`;
no significan que el mes de servicio esté pagado. La racha de
Activos se ancla al último mes disponible de Venta Total (octubre
2026); la mejor racha histórica se calcula sin requerir que termine
en ese corte. Los meses sin archivo verificado (2020-04 a 2020-06)
permanecen desconocidos y no prueban bajas.

Los precios del escenario $599/$499/$399/$299 por niveles 1–4
son configurables en hoja `Reglas`; **provisionales**. La salida
puede apoyar la decisión de aprobar el **proyecto de validación**,
pero no asignar descuentos reales ni concluir que los vencidos
históricos son `Aplica KPI=Si`. Para certificar meses pagados
se sigue requiriendo cruce de cobro, vigencia y estado con Gasca.

### Criterios de aceptación

- Sin duplicados ID Socio en Activos; falla explícitamente si existen.
- Un ID Socio en Activos `KPI=No` queda fuera de ambas hojas.
- Un activo `KPI=Si` sin compra en Venta Total sigue en Activos,
  con racha 0 y aviso para revisar, no desaparece.
- El resto de ID Socio de Venta Total aparece una sola vez en
  Vencidos candidatos con racha máxima de compras.
- Cada mes de historia es filtrable, y el resumen representa niveles
  tentativos sin equiparar ventas a meses de servicio.
- Ningún dato se escribe en PostgreSQL, snapshots ni RAW.


### Ejecución local del Excel de aprobación (2026-11-07)

El operador ejecutó correctamente el exportador sobre su SQLite local
de 1,503,911 movimientos (79 meses con fuente, faltan 2020-04/05/06)
y el padrón de Socios Activos al 2026-11-07. Resumen agregado
comunicado por el operador, sin adjuntar PII ni archivos XLSX:

| Nivel tentativo por compras | Activos KPI=Sí | Históricos ausentes de Activos |
|---|---:|---:|
| 0 / sin racha observable | 4,109 | 185 |
| 1 (1–3 compras mensuales consecutivas) | 10,603 | 159,311 |
| 2 (4–6) | 3,989 | 26,145 |
| 3 (7–9) | 4,269 | 11,049 |
| 4 (10+) | 10,755 | 13,047 |
| **Total** | **33,725** | **209,737** |

- **135 activos KPI=Sí** no tienen movimientos identificados
  en Venta Total; quedan visibles sin nivel.
- **3,974 activos KPI=Sí adicionales** tienen historial observado
  pero sin compra en octubre de 2026 (último mes del consolidado).
  No declararlos vencidos ni sin pago; podría haber compra en
  noviembre, servicio prepagado o cobro distinto.
- **1,052 activos KPI=No** se excluyen de ambas listas,
  no migran al grupo histórico.
- Los **209,737** históricos no en Activos son un universo de
  identificación, **no** elegibles KPI confirmados. La gran
  proporción con racha de compra 1 requiere validación comercial.
- Se generó localmente
  `data/backfill/gasca_venta_total_enriched/consolidated/UltraGym_Rachas_Direccion.xlsx`;
  contiene PII y debe permanecer bajo acceso restringido,
  fuera de GitHub/CI.

**Gate para dirección:** presentar estas cantidades como
diagnóstico de factibilidad, no como nivel ni tarifa comercial
definitiva. Antes de aprobar aplicación individual de descuentos:
validar ciclos de servicio/vigencias y cobros recurrentes con Gasca;
verificar los 4,109 activos sin compra en el corte; no confundir
meses sin fuente (2020-04 a 2020-06) con interrupción de pago.


## Auditoría focal: activos sin compra en el mes de corte (2026-11-07)

El primer Excel real informó **4,109 socios Activos KPI=Sí** sin
un movimiento de Venta Total con estatus `ACTIVO` en octubre 2026:
135 no tienen movimientos identificados; los otros 3,974 sí tienen
historial pero no compra observada en el corte. No son bajas
certificadas ni necesariamente morosos.

`backend/scripts/ops/audit_active_streak_gaps.py` usa la SQLite
local consolidada (modo lectura) y el mismo `Socios Activos.xlsx`
del primer Excel. **No modifica** universos, tarifas, PostgreSQL,
Warehouse, eventos históricos ni el Excel original de presentación.

Ejecutar desde la carpeta `backend` en Windows PowerShell:

```powershell
git pull
.\\.venv\\Scripts\\python.exe -m scripts.ops.audit_active_streak_gaps --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" --sales-cutoff 2026-10 --as-of 2026-11-07 --output "data\\backfill\\gasca_venta_total_enriched\\consolidated\\Auditoria_Activos_Sin_Compra_Oct2026.xlsx"
```

La salida local (ignorada por Git) tiene:
- **Resumen:** motivo descriptivo según `Fecha Último Pago`
  del padrón y distribución de vencimientos y tipos de la
  última venta observada.
- **Casos:** una fila por socio no anclado en octubre,
  con `ID Socio`, PIN, sucursal, tarifa vigente del padrón,
  último pago, vencimiento y última venta con estatus
  `ACTIVO` (mes/fecha/tipo/folio).
- **Muestra 20:** hasta cuatro casos por grupo y variedad de
  tipo de venta para contrastar manualmente con Gasca.

Grupos **descriptivos** excluyentes:
1. `SIN_HISTORIAL`;
2. `PAGO_PADRON_MES_POSTERIOR` (el mes del último pago
   del padrón es posterior al mes final de Venta Total);
3. `PAGO_PADRON_MES_CORTE`;
4. `PAGO_PADRON_MES_ANTERIOR`;
5. `FECHA_PAGO_NO_DISPONIBLE`.

El `Fecha Vencimiento` del padrón es una señal de estado
de servicio, NO evidencia de que el cobro fue liquidado.
No derivar meses pagados de `Fecha Último Pago` ni de
un plazo como `DOMICILIADO 12 MESES`. Una anualidad
puede seguir vigente sin aparecer en compras del mes.

La salida de consola `[RESUMEN_VALIDACION]` es agregada,
sin PII, y sirve para decidir cuál segmento contrastar con
20 casos en Gasca. Solo cuando se obtengan cobros/intervalos
realmente verificables podrá ajustarse el motor y recalcular
los niveles. No subir los XLSX privados a GitHub ni a CI.


### Resultado real: diagnóstico de 4,109 activos sin compra observada en octubre de 2026

El operador ejecutó `audit_active_streak_gaps` sobre su SQLite y padrón de
2026-11-07 (solo local, sin incorporar PII en GitHub). Resultado
`DIAGNOSTICO_COMPRAS_NO_VIGENCIAS`:

| Señal | Socios |
| --- | ---: |
| Activos KPI=Sí, total | 33,725 |
| Activos sin compra ACTIVO en octubre | 4,109 |
| Último pago del padrón previo a octubre | 3,756 |
| Último pago del padrón en octubre | 218 |
| Sin ventas históricas identificadas | 135 |
| Vencimiento vigente según padrón | 3,743 |
| Vencimiento anterior al corte del padrón | 366 |

Última transacción `ACTIVO` identificada (tipo):
`TRIMESTRAL SIN CONTRATO` 1,545;
`ANUALIDAD SIN CONTRATO` 1,496;
`CONTRATO` 385;
`SEMESTRAL SIN CONTRATO` 308;
`BIMESTRAL SIN CONTRATO` 60;
`MENSUAL SIN CONTRATO` 144;
`SEMANAL SIN CONTRATO` 9;
`SIN VENTA ACTIVA` 162. Los casos sin venta activa incluyen los
135 sin historial; los otros 27 tienen movimientos sin venta `ACTIVO`
identificada. **3,409 / 4,109 (83.0%)** tienen modalidad nominal de más
de un mes (trimestral, anualidad, semestral o bimestral). Esto explica
por qué medir la racha vigente por presencia de compra exclusivamente
en octubre subestima periodos de servicio en membresías prepagadas.

La auditoría produce una muestra de **12 casos**, no 20 porque solo se
presentaron tres grupos de fecha de pago. El archivo generado localmente
fue `Auditoria_Activos_Sin_Compra_Oct2026.xlsx`.

**Decisión de calidad:** no etiquetar a estos 4,109 como pérdida de
racha, morosidad o abandono. Mantener `SIN_RACHA_DE_COMPRA_AL_CORTE /
POR_VALIDAR_VIGENCIA` en análisis ejecutivo. No convertir la
fecha de vencimiento en prueba de pago ni fijar descuento. La vigencia
de 3,743 registros y la discrepancia de los 366 vencimientos anteriores
requieren contraste de producto y ciclos reales. Los 218 con fecha de
último pago en octubre pero sin movimiento ACTIVO de membresía del mes
sugieren revisar alcance de ventas filtradas, fechas, estatus o fuentes
alternativas.

**Siguiente gate focal:** validar primero la muestra de 12 casos en
Gasca (tipos mensual, trimestral, anualidad, etc.), contrastar
`Fecha Último Pago`, `Fecha Vencimiento`, folios de Venta Total,
modalidad comercial y estatus cobrado/ajustado. Verificar expresamente
los 366 vencimientos anteriores al corte. Una vez documentada la
regla de intervalos por producto, corregir el motor *de cobertura* y
recalcular ambos universos; no asignar niveles desde meros meses
de compra.


## Validación de Gasca: carpeta de evidencia de la muestra

`backend/scripts/ops/prepare_gasca_sample_review.py` toma la **misma
muestra local** de hasta 20 casos seleccionados por
`audit_active_streak_gaps.audit` (en el corte 2026-11-07 se
obtuvieron **12 casos**). No solicita descargar nuevos reportes,
no consulta el servidor Gasca, no altera eventos ni aplica tarifas.

En PowerShell, desde la carpeta `backend`:

```powershell
git pull
.\\.venv\\Scripts\\python.exe -m scripts.ops.prepare_gasca_sample_review --active-xlsx "$HOME\\Downloads\\Reporte Socios Activos.xlsx" --as-of 2026-11-07 --sales-cutoff 2026-10 --output ".\\data\\backfill\\gasca_venta_total_enriched\\consolidated\\Revision_12_Casos_Gasca.xlsx"
```

Dos pestañas consultables:
- **Casos a revisar:** ID Socio, PIN, sucursal, tarifa, último pago y
  vencimiento del padrón, tipo/fecha/folio de la última venta y grupo.
  Incluye `Revisión Gasca` editable (valor inicial `PENDIENTE`),
  resumen de cobro/servicio verificado, referencia y observaciones.
- **Movimientos y cobros:** *todos* los folios de Venta Total
  almacenados para esos ID Socio, incluso cancelados, con descripción,
  importe, tipo, estado y fecha. Cada folio tiene `Cobro validado`
  (inicia `PENDIENTE`), fechas de cobertura verificadas en Gasca,
  referencia y observación. Nunca se completan fechas
  automáticamente desde el plazo del contrato.

Protocolo manual en Gasca: buscar por ID Socio y PIN, revisar
folio/estatus, comprobar si existe cargo efectivamente liquidado
(sin reembolso), identificar servicio desde/hasta y registrar la
referencia original; si no se puede demostrar, dejar
`SIN_EVIDENCIA` o `PENDIENTE`, sin asignar meses pagados.

La salida XLSX contiene identificadores y folios de socios; está
ignoradada por Git al guardarse bajo `backend/data/backfill`.
No subir a PR ni CI ni compartir públicamente. El resumen de
consola `[MUESTRA_GASCA]` no incluye PII.

**Aceptación:** la herramienta genera evidencia organizada para
revisión humana sin convertir ninguna venta en mes cubierto. La
certificación, ajuste de reglas de rachas y simulación final
permanecen pendientes de la comprobación real en Gasca.


### Identidad del socio en los Excel de revisión

Se conserva **Nombre** del padrón `Socios Activos` junto a
`ID Socio` y `PIN` en `Casos` y `Muestra 20` del
`Auditoria_Activos_Sin_Compra`, y en ambas pestañas
(`Casos a revisar` / `Movimientos y cobros`) de
`Revision_12_Casos_Gasca`. Los folios de Venta Total se enriquecen
por `ID Socio` desde la muestra, **no** haciendo coincidencias
por nombre ni alterando la base de datos.

Para preservar una revisión ya empezada, emitir una nueva
salida `Revision_12_Casos_Gasca_con_nombres.xlsx` y evitar
`--replace`. Mantener estos Excel con nombres de socios solo
en el directorio privado local ignorado por Git, con acceso
autorizado. Nunca incluir PII en logs ni en CI.
