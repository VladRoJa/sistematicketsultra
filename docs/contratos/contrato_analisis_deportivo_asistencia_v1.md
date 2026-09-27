# Contrato v1 — Análisis Deportivo / Aforo y Asistencia

## 1. Jerarquía funcional

```text
Análisis Deportivo
├── Control de Rutinas
└── Aforo y Asistencia
```

Control de Rutinas conserva su lógica y endpoints actuales. El cambio es de jerarquía de navegación, no una mezcla de dominios.

## 2. Objetivo

Integrar el **Reporte de Estadísticas de Asistencias de Gasca** como fuente estructurada en PostgreSQL para medir visitas, personas únicas, entradas por hora, aforo simultáneo, horas pico, duración de visita, frecuencia, comportamiento por sucursal y segmentación disponible.

## 3. Principio de almacenamiento

El XLSX es únicamente transporte temporal:

```text
Gasca
  ↓
XLSX temporal
  ↓
validación + parser
  ↓
PostgreSQL
  ↓
marts
  ↓
Aforo y Asistencia
```

No se conserva un histórico de Excel. El capturador es responsable de borrar el temporal después de una ingesta correcta.

La trazabilidad se conserva en SQL mediante ejecución, hash SHA-256, conteos, rechazos y fingerprint de cada visita.

## 4. Fecha de negocio

La ingesta recibe explícitamente `business_date`.

El servicio no calcula internamente “ayer”. El scheduler podrá ejecutar normalmente D+1, pero deben poder existir reproceso y backfill por fecha.

Zona de negocio: `America/Tijuana`.

## 5. Tablas

### `warehouse_attendance_runs`

Audita cada ejecución:

- business_date
- status: RUNNING / SUCCESS / FAILED
- trigger_source
- source_sha256
- parser_version
- source_rows
- inserted_rows
- updated_rows
- rejected_rows
- error_message
- started_at_utc / finished_at_utc

### `warehouse_attendance_visits`

Cada fila representa una visita reportada por Gasca.

Campos principales:

- business_date
- sucursal_id
- source_branch_name
- member_pin (VARCHAR)
- entered_at_utc
- exited_at_utc
- duration_seconds
- visit_status
- age / age_is_valid
- city
- postal_code
- member_since
- attendance_type
- has_opening
- source_row_number
- source_fingerprint
- last_run_id

Nombre y apellido no se almacenan en la tabla analítica.

### `warehouse_attendance_rejections`

Registra filas que el parser no puede convertir sin guardar el XLSX ni nombres/apellidos.

### Marts

- `track_attendance_interval_mart`: intervalos de 15 minutos.
- `track_attendance_daily_mart`: resumen diario por sucursal y tipo de asistencia.

## 6. Idempotencia

El fingerprint identifica la visita sin incluir la salida.

Esto permite que una visita que primero llegue `OPEN` y después sea cerrada por Gasca actualice el mismo registro durante un reproceso.

El PIN se almacena como texto para conservar ceros iniciales.

## 7. Estados de visita

- `CLOSED`: entrada y salida válidas del mismo día.
- `OPEN`: Gasca no tiene salida al momento de la captura.
- `CROSS_DAY`: salida en un día posterior.
- `INVALID_TIME`: salida anterior a la entrada.

Una visita `OPEN` no es automáticamente un error. El comportamiento del torniquete puede corregir una salida pendiente en la siguiente lectura.

## 8. Afluencia y aforo

**Afluencia**: entradas producidas en un periodo.

**Aforo simultáneo**: personas presentes al mismo tiempo.

El mart de aforo usa únicamente visitas `CLOSED` del mismo día. Las visitas OPEN, CROSS_DAY e INVALID_TIME se conservan y cuentan como hechos de asistencia cuando corresponde, pero no inflan el aforo.

No se fija todavía un umbral arbitrario de “duración anómala”. Se evaluará con varios días mediante percentiles.

## 9. Resolución de sucursal

Se reutiliza el catálogo Track existente:

```text
track_branch_aliases
source_family = gasca_family
        ↓
track_branch_catalog
        ↓
sucursal_id
```

No se crea un segundo catálogo de alias.

Una visita cuya sucursal no pueda resolverse se conserva con `sucursal_id = NULL` y queda visible como incidencia de calidad para perfiles globales.

Los orígenes que Gasca usa para accesos corporativos o administrativos y que no representan un gimnasio físico se conservan igualmente con `sucursal_id = NULL`, pero se clasifican como **no operativos excluidos**, no como alias faltante. En la validación inicial, `CORP CDMX` pertenece a esta categoría. Estos registros se conservan para auditoría y calidad de datos, pero no participan en visitas, aforo, rankings ni marts por sucursal operativa.

## 10. Segmentación

La v1 usa directamente:

- edad
- ciudad
- sucursal
- fecha de alta
- tipo de asistencia
- Tiene Apertura

Atributos no presentes en el reporte, como sexo, membresía, domiciliado o tarifa, se obtendrán posteriormente desde otra fuente estructurada mediante PIN.

No se infiere sexo por nombre.

## 11. Permisos

El backend es la fuente real de autorización.

Durante la beta inicial, **Aforo y Asistencia sólo está habilitado para el usuario ADMICORP**. La validación se realiza nuevamente en backend en cada endpoint; ocultar el menú no constituye autorización.

**Control de Rutinas conserva exactamente su audiencia y permisos actuales.** Moverlo debajo de Análisis Deportivo sólo cambia su jerarquía de navegación.

El frontend protege únicamente la ruta de Aforo y Asistencia. La ruta `/control-rutinas` mantiene su comportamiento previo y sus endpoints continúan aplicando sus propias reglas de acceso.

## 12. API v1

- `GET /api/sports-analysis/context`
- `GET /api/sports-analysis/attendance/catalogs`
- `GET /api/sports-analysis/attendance/dashboard`
- `GET /api/sports-analysis/attendance/runs` (solo perfiles globales)

Filtros iniciales del dashboard:

- date_from
- date_to
- region_key
- branch_id
- attendance_type

El rango interactivo inicial se limita a 93 días para proteger el backend web. Comparativos históricos más largos deberán usar endpoints agregados específicos si se requieren.

## 13. Dashboard inicial

KPIs:

- visitas
- PIN/personas únicas
- aforo pico
- fecha/hora del pico
- estancia promedio
- estancia mediana

Visualizaciones:

- curva de aforo en intervalos de 15 minutos
- entradas por hora
- distribución por edad
- distribución por tipo de asistencia
- ranking de sucursales
- calidad de datos

## 14. Capturador

El Playwright que descarga Gasca se desarrolla en una rama separada del core.

Requisitos del capturador:

- recibir `business_date` explícita;
- descargar a archivo temporal;
- no ejecutar `limpiar_excel_inplace`;
- invocar la ingesta estructurada dentro del contexto Flask;
- borrar el XLSX temporal tras éxito;
- permitir prueba local y reproceso por fecha;
- no correr dentro de una petición Gunicorn.

El capturador se llevará a PR únicamente después de validarlo localmente.
