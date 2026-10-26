# Suite Ultra — CAP-V1 / Capacitación automatizada

## Alcance y auditoría (2026-10-26)

Piloto: Tickets > Tapizado multiaparato M1–M4 (UI Angular **real**, no maqueta).
El generador se ejecuta fuera del backend web, sobre una **copia local aislada**
con PostgreSQL de capacitación. No se agregan endpoints, migraciones ni permisos.

Archivos inspeccionados:
- `frontend/src/app/app.routes.ts`: ruta `/#/main/ver-tickets`.
- `frontend/src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.html`:
  botones de recepción, cierre, rechazo e historial.
- `frontend/src/app/pantalla-ver-tickets/modals/tapizado-recepcion-modal.component.{ts,html}`:
  edición provisional, guardado por lote, motivo obligatorio al revertir.
- `frontend/src/app/shared/modal-cierre-ticket/modal-cierre-ticket.component.{ts,html}`:
  solicitud de conformidad con notas obligatorias.
- `frontend/src/app/utils/alertas.ts`: motivo de rechazo SweetAlert.
- `backend/app/routes/internal_documents_routes.py`:
  `INTERNAL_DOCUMENT_ALLOWED_EXTENSIONS` **no contiene mp4** y
  `INTERNAL_DOCUMENT_MAX_FILE_SIZE_BYTES = 50 MiB`.

### Condiciones previas obligatorias

1. Levantar una instancia **no productiva** de Angular + Flask + PostgreSQL,
   con volúmenes y credenciales diferentes de producción. No conectar una
   base productiva detrás del proxy `frontend/proxy.conf.json` ni importar datos
   reales de clientes. Separar explícitamente Compose/project name/volúmenes.
2. Completar migraciones Alembic en esa instancia y habilitar los flags M3/M4.
3. Crear **solo en ese entorno** un ticket Tapizado **En progreso**, con
   al menos tres códigos únicos de inventario de demostración, inicialmente
   `0/N` recibidos; preparar un usuario coordinador con permiso de recepción y
   solicitud y un usuario gerente/creador autorizado a rechazar.
4. Verificar manualmente que ambas cuentas poseen su alcance correcto.
   No habilitar permisos privilegiados nuevos solo para grabar.
5. Anotar ID y códigos del ticket. Usar un dataset reproducible o restaurar
   snapshot de BD de capacitación ANTES de cada nueva toma.
6. Instalar FFmpeg, Python Playwright (el backend usa 1.54.0),
   Chromium de Playwright y `espeak-ng` opcional para narración.

### Ejecutar

Desde la raíz del repositorio (Linux, WSL o entorno Python local):

```bash
python -m pip install playwright==1.54.0
python -m playwright install chromium
python -m unittest discover -s scripts/training/tests -v
# Establecer las cuatro variables solo en la terminal local:
# CAP_ACTOR_USER, CAP_ACTOR_PASSWORD, CAP_REVIEWER_USER, CAP_REVIEWER_PASSWORD
python -m scripts.training.generate \
  --base-url http://127.0.0.1:4200 \
  --isolated-ack BD_DE_CAPACITACION_AISLADA \
  --ticket-id 123 \
  --codes DEMO-01 DEMO-02 DEMO-03 \
  --output artifacts/capacitacion/tapizado \
  --voice espeak
```

El `--isolated-ack` es un **reconocimiento**, no prueba técnica de aislamiento.
Confirmar por separado la cadena de conexión de PostgreSQL y el proxy Flask.
El script restringe navegación/red HTTP(S) a loopback y nunca acepta una URL
externa. Las claves se obtienen desde variables de entorno y no se persisten
en el manifiesto. No conservar `fallo.png` si aparecen datos privados.

### Guion completo

Ingreso → Tickets → Historial de multiaparato → recepción 2/N →
recepción N/N (100%) → solicitud de conformidad → cambio a cuenta revisora →
rechazo con motivo → regreso al operador → reversión con motivo → historial.
Los botones y las escrituras son los reales; no hay inyección de estados
ni rutas API falsas. Se **detiene con error** si el ticket no está en 0/N,
faltan botones, la API niega la acción o el resultado no coincide.

### Productos y regeneración

- `navegacion.webm`: captura original Playwright, resolución 1920x1080.
- `subtitulos.srt`: escenas y subtítulos externos editables.
- `capacitacion.mp4`: H.264 / AAC si hay narración, subtítulos mov_text.
- `manifiesto.json`: fechas, segmentos y datos de demostración, sin credenciales.
- `fallo.png`/`fallo.txt`: únicamente cuando el recorrido falla; no publicar.

La narración automática inicial usa `espeak` (voz robótica offline), sustituible
por una pista profesional en iteración editorial sin alterar la automatización.
El storyboard se edita en `scripts/training/storyboards/`. Para futuros módulos
crear otro guion y otro recorrido manteniendo el exportador común.
Antes de nueva grabación **restaurar el dataset aislado**: el recorrido termina
con N-1 aparatos recibidos, y el usuario debe repetirlo desde 0/N.

### Publicación en Nube corporativa — bloqueada en CAP-V1

No publicar ni cambiar la allowlist mediante un parche rápido. Abrir un cambio
independiente de plataforma documental para evaluar MP4/MIME, límites y tamaños,
streaming/range, permisos de descarga, cuotas, almacenamiento y previsualizador.
Solo después de QA documental podrá incorporarse un paso de publicación con
autenticación y auditoría propias.

### Criterios de aceptación

- Seguridad: destino local solamente, confirmación de BD aislada y cuentas demo.
- Contrato: estado inicial 0/N; parcial 2/N; completo N/N; cierre permitido.
- Autorizaciones: rechazo por usuario autorizado; motivo trazado.
- Regresión: al revertir N-1/N no aparece acción Solicitar cierre.
- Evidencia: historial observable; archivos MP4+SRT+JSON válidos con FFprobe.
- Integración: PR único y CI antes de merge; no despliegue a producción necesario.
- Estado de entrega: **automatización desarrollada; grabación real pendiente**
  hasta disponer de la instancia de prueba y las credenciales DEMO.
