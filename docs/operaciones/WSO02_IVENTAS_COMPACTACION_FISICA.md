# WSO-02 — Ventana de mantenimiento para compactación física de iVentas

**Preparado:** 2026-11-02. **Estado:** PLAN / NO EJECUTADO. **Origen:** PR #1200, merged en main.
**Alcance estricto:** `public.marketing_iventas_raw_pages`, `public.marketing_iventas_contact_tags`, `public.marketing_iventas_contacts`.
**No incluido:** eliminar datos adicionales; cambiar flags, permisos, canonicalidad, índices por separado, migraciones o compactar Venta Total/otras tablas.

## Resultado del proceso lógico (producción, confirmado por el operador)

- 174/174 corridas elegibles depuradas (9,240,870 contactos). `canonicas_afectadas=0`.
- Cabeceras de `marketing_iventas_sync_runs` y contadores originales conservados; estado `payload_pruned_at` registrado.
- Fondo del problema: tamaño físico después de DELETE: contacts ~12 GB (heap 7,394 MB, índices 4,856 MB), raw_pages ~1,024 MB, tags ~628 MB. Base actual ~49 GB.
- Capacidad: 83 GB libres sobre `/dev/sda3`; WAL: ~1.1 GB; 26 sesiones `idle` y ninguna transacción larga reportada, cero slots de replicación. **Esta fotografía caduca; revalidar en la ventana.**

## Gate 0 — respaldo: OBLIGATORIO, actualmente NO PASADO

El procedimiento vigente `backend/scripts/ops/backup_postgres.sh` hace `pg_basebackup -Fp -X stream`, `pg_verifybackup`, compresión tar.gz, `rclone copy` y retención. `install_postgres_backup.sh` agenda el cron a las **02:15**, si sigue instalado.

Preflight actual de backup: `max(MIN_FREE_GB (60), 2 * SUM(pg_database_size) + 10 GiB)`. La estimación previa rondaba **122 GB libres**, pero solo hay ~83 GB en el dispositivo actual. **No cambiar este umbral, no asumir respaldo reciente, no eliminar respaldos viejos y no ejecutar VACUUM FULL sin gate aprobado.**

Ruta de preferencia:
1. Acreditar volumen de respaldo **independiente** del disco de PostgreSQL con espacio suficiente para el preflight (no solo un subdirectorio del mismo `/dev/sda3`).
2. Usar el **script canónico existente** con `BASE_DIR` apuntando al volumen adicional, sin editar archivos ni credenciales del servidor. Verificar primero `--preflight`, luego ejecutar backup solo cuando el almacenamiento externo esté listo.
3. Confirmar `pg_verifybackup` **PASS**, copia remota **completada** y evidencia del respaldo reciente. Probar restauración en un entorno separado cuando sea viable; integridad verificada no equivale por sí sola a restauración demostrada.
4. Si no hay volumen independiente ni respaldo reciente verificable, **bloquear compactación**; obtener almacenamiento externo o diseñar backup remoto directo *como otro paquete*, no improvisar un `pg_dump` local.
5. Confirmar que el respaldo puede recuperar estado de datos **posterior a WSO-02** y que corresponde al clúster correcto. Si hay una copia anterior, no es evidencia suficiente de estado actual.

### Diagnóstico del respaldo — solo lectura

```bash
cd ~/sistematicketsultra
sudo tail -n 35 /var/log/backup_postgres.log
sudo find /root/base-backups -maxdepth 1 -type f -name 'base_*.tar.gz' \
  -printf '%TY-%Tm-%Td %TH:%TM %s %f\n' | sort -r | head -n 10
df -h .
findmnt -T /root/base-backups -o SOURCE,TARGET,AVAIL
docker compose exec -T db psql -X -U postgres -d sistema_tickets -Atqc \
  "SELECT pg_size_pretty(SUM(pg_database_size(datname))) FROM pg_database"
```

No enviar `.pgpass`, el contenido de `rclone.conf` ni otros secretos.

## Gate 1 — preflight inmediato a la ventana

- Acordar y comunicar **interrupción de funcionalidades que leen iVentas** (Funnel, Contact Center, marketing, campañas). No prometer duración hasta medir un piloto de compactación.
- Evitar sincronización programada marketing (08:20/12:20/16:20/20:20 `America/Tijuana`), backup 02:15 si cron instalado y jobs nocturnos de Track. No iniciar durante una carga iVentas activa.
- Registrar servicios actualmente corriendo con `docker compose ps -a`; **volver a arrancar solo los que estaban corriendo**.
- Volver a medir disco, WAL, tamaño de tablas, sesiones activas y vínculos canónicos:
```bash
cd ~/sistematicketsultra
docker compose ps -a
df -h .
docker compose exec -T db df -h /var/lib/postgresql/data
docker compose exec -T db psql -X -U postgres -d sistema_tickets -v ON_ERROR_STOP=1 <<'SQL'
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_relation_size(relid)) AS heap,
       pg_size_pretty(pg_indexes_size(relid)) AS indices
FROM pg_stat_user_tables
WHERE relname IN ('marketing_iventas_raw_pages',
                  'marketing_iventas_contact_tags',
                  'marketing_iventas_contacts')
ORDER BY pg_total_relation_size(relid) DESC;
SELECT COUNT(*) FILTER (WHERE payload_pruned_at IS NOT NULL) AS depuradas,
       COUNT(*) FILTER (WHERE is_canonical AND payload_pruned_at IS NOT NULL) AS canonicas_afectadas
FROM marketing_iventas_sync_runs;
SELECT pid, state, wait_event_type, now()-xact_start AS xact_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND (state <> 'idle' OR xact_start IS NOT NULL);
SQL
```
- **Abortar antes de comenzar** si no existe backup acreditado, hay operaciones iVentas activas, hay sesiones con transacciones largas, o la reserva de disco es insuficiente para reescribir la tabla y sus índices más WAL. No inferir recuperación exacta en GB por contar filas.
- Confirmar en el mismo dispositivo de `PGDATA` al menos 50 GiB libres **en cada cambio de tabla**. Umbral de seguridad operacional, no garantía contra un WAL excesivo.

## Gate 2 — mantenimiento físico, NO ejecutar sin nueva autorización específica

1. Pausar entradas de trabajo de marketing y usuarios de forma controlada. Durante ventana, detener `backend`, `marketing-scheduler` y los servicios activos que acceden a iVentas. Considerar `reports-scheduler` y `campaign-v2-dispatch-worker` según el listado de procesos, sin detener `db`, sin `docker compose down` y sin tocar volúmenes.
2. Con comprobación de sesiones/locks, ejecutar **una tabla por vez** desde una conexión PostgreSQL autónoma (`VACUUM FULL` no puede ejecutarse dentro de transacción explícita). Un `lock_timeout` reducido impide una cola de bloqueo indefinida. `VACUUM FULL` adquiere `ACCESS EXCLUSIVE`: bloquea SELECT, INSERT, UPDATE y DELETE de esa tabla.
3. Orden elegido: `marketing_iventas_raw_pages` (1 GB) → `marketing_iventas_contact_tags` (628 MB) → `marketing_iventas_contacts` (12 GB). Registrar `df -h` y `pg_total_relation_size` antes y después de **cada tabla**.
4. No ejecutar las tres en una misma orden. Si cualquier tabla falla, no avanzar a la siguiente hasta explicar el motivo.
5. **No cancelar a ciegas:** si es necesario abortar, comprobar primero actividad del proceso, seguridad de WAL y retorno de servicio; PostgreSQL conserva atomicidad, pero una interrupción puede alargar la ventana.

Plantilla por tabla (solo tras gates y autorización, reemplazar exactamente la tabla):

```bash
# NO EJECUTAR AHORA. EJEMPLO: solo tabla raw_pages.
docker compose exec -T db psql -X -U postgres -d sistema_tickets \
  -v ON_ERROR_STOP=1 <<'SQL'
SET lock_timeout = '5s';
VACUUM (FULL, ANALYZE, VERBOSE) public.marketing_iventas_raw_pages;
SQL
```

Para monitorear desde una segunda terminal:
```sql
SELECT pid, command, phase, heap_blks_scanned, heap_blks_total
FROM pg_stat_progress_cluster;
```
`VACUUM FULL` se informa en `pg_stat_progress_cluster`, no en `pg_stat_progress_vacuum`.

## Gate 3 — verificación final y recuperación del servicio

- Cero canónicas con `payload_pruned_at IS NOT NULL`; 174 corridas depuradas o diferencia explicada, conteos detallados por corrida ya depurada cero mediante consulta acotada.
- Comparar los tamaños físicos de las tres relaciones y `df -h`. Registrar **GB efectivamente devueltos** al sistema operativo.
- Confirmar backend y workers restaurados al estado previo; `docker compose ps`, logs y GET de salud sin bloqueo. La raíz `/` del backend puede dar un 404 rápido y normal.
- Probar Funnel Original, Contact Center, Campaign V2, historial iVentas y sincronización nueva; nunca marcar validado solo con CI o sesión disponible.
- Revisar el estado de respaldo automático después de la compactación. El umbral `2 × SUM(pg_database_size)+10 GiB` puede continuar siendo superior al espacio libre aun si se recuperan varios gigabytes: **WSO-02 no cierra por sí solo el incidente de backup**.
- Registrar tamaños antes/después, backup verificado, salida de mantenimiento, bloqueos, incidencias y validación funcional; cierre explícito de ventana.

## Puertas de autorización

- Autorizado por el propietario **preparar este plan**, no ejecutarlo todavía.
- Requiere confirmación de respaldo reciente y restaurable y aprobación de **ejecución de VACUUM FULL** durante ventana (distinta de la autorización de 174 borrados, ya completados).
- Sin merge ni despliegue de este documento sin revisión. Este runbook no instala servicios ni cambia esquemas.

## Gate 0.A — Diagnóstico real del servidor (2026-11-02)

El operador verificó:

- `/dev/sda3`: 314 GB de sistema de archivos, 218 GB usados, **83 GB libres**. `lsblk` solo muestra el disco `sda` de 320 GB y particiones EFI/ext4; **no hay volumen independiente montado**.
- `/root/base-backups`: siete archivos `base_2026-09-18_021501.tar.gz` a `base_2026-09-24_021501.tar.gz`, cada uno entre 8.85 y 9.43 GB decimales; suma aproximada **64 GB decimales (~59.6 GiB)**. Todos son anteriores a WSO-01/WSO-02.
- Logs del cron oficial 2026-10-29 a 2026-11-02: **ERROR espacio insuficiente**, último `libre=70GB requerido=122GB`. El espacio de 83 GB es más reciente y refleja liberaciones ya realizadas; el requisito se recalcula y puede cambiar.
- No se encontró respaldo local posterior al 24 de septiembre; **el inventario remoto aún no está comprobado**.

### Ruta de recuperación sin disco nuevo — condicionada

1. **Solo lectura:** inventariar copias remotas en el destino ya configurado por el script, `gdrive:sistematickets-backups/base`, con rclone y configuración actual. Nunca imprimir tokens/configuración.
2. Si hay coincidencia por nombres y tamaños, ejecutar **`rclone check` en modo solo lectura** para comparar hashes/bytes cuando el proveedor los permita; exigir verificación exitosa de **cada** archivo local candidato a retirada. Si no se pueden verificar, no eliminarlos.
3. Preparar propuesta explícita de retiro **solo de copias locales que ya están acreditadas en remoto**, preferiblemente manteniendo al menos la más reciente local mientras se crea una copia nueva. Se requiere consentimiento específico para retirar esos respaldos antiguos. Liberar seis de los siete podría recuperar alrededor de 50 GiB, pero está sujeto a los tamaños reales. Antes de autorizar, comprobar que se cuenta con margen suficiente para `pg_basebackup` + compresión + WAL, y que las siete copias remotas no dependan de los originales.
4. Después de retirar copias **solo si autorizado y verificadas**, ejecutar preflight canónico con `BASE_DIR` local y luego backup nuevo `pg_basebackup`, `pg_verifybackup`, `rclone copy`. Registrar su éxito y evidencia; restauración de prueba preferible si se puede hacer en infraestructura separada.
5. **Solución permanente:** modificar por otro paquete el destino de almacenamiento / retención para que las copias nuevas no vuelvan a bloquearse cada noche; priorizar disco separado o flujo remoto verificable. No bajar arbitrariamente el umbral ni dejar todas las copias exclusivamente en un disco sin redundancia.

#### Verificación remota previa — sin modificar archivos

```bash
# Lista nombre/tamaño en el remoto; solo lectura.
sudo rclone --config /home/adminrdp/.config/rclone/rclone.conf \
  lsf gdrive:sistematickets-backups/base \
  --files-only --format sp --include 'base_*.tar.gz' | sort -r | head -n 20
```

**Aún no ejecutar** `rclone delete`, `rm`, `pg_basebackup` ni `VACUUM FULL`. La comprobación de hash será el siguiente gate tras contrastar listado.
