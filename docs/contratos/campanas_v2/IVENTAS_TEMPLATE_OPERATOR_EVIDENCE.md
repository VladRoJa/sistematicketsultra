# Campañas V2 — Evidencia de plantillas iVentas para recuperación fallida

## Alcance

Tras crear una campaña derivada de rechazos confirmados, el preflight bloquea
con PROVIDER_TEMPLATE_UNVERIFIED hasta disponer de evidencia específica.

Se reutiliza el lector de inventario existente: no se inventa una consulta API
de iVentas ni se confunde el catálogo local con validación online.

## Operación sin envío

1. Consultar en iVentas el inventario de plantillas, y exportar/copiar el JSON
   original con name, status, channelId y channel { id, name }.
   No fabricar ni editar manualmente los estados.
2. Abrir el Centro de envío de la campaña de recuperación y ejecutar
   «Revisar destinatarios y costo».
3. Desplegar «Verificar plantilla por canal con evidencia de iVentas».
4. Pegar JSON, fecha/hora real de captura (ISO con zona horaria) y una referencia
   rastreable a la consulta/captura conservada internamente.
5. Confirmar origen y registrar. No reserva, aprueba ni envía.
6. Revisar nuevamente el plan completo. Se exige un estado accepted para
   TODOS los canales emisores efectivos. Faltantes o rechazados bloquean.

## Seguridad y auditoría

- JWT, configuración dispatch global y capacidad de envío legacy obligatorias.
- Historial append-only: actor, captura, registro, plantilla/fingerprint local,
  SHA256 del inventario y canales aceptados. No almacena JSON bruto.
- Se admiten capturas de menos de una hora, vigentes por 24 horas desde captura.
- Cambios de plantilla (nombre, variables, compatibilidad) o canal emisor
  invalidan el pase; el preflight normal se ejecuta otra vez antes de aprobar,
  preparar o enviar.
- No hay API de lectura autenticada de iVentas verificada en este repositorio:
  esto es EVIDENCIA ATESTIGUADA POR OPERADOR, no una consulta online oficial.
  Se requiere igualmente comprobación externa antes de enviar realmente.
- Campaña #42 y TEC_MXL #265 no se alteran ni reenvían automáticamente.
- Nueva migración Alembic m1224tmpl110526; desplegar backend/frontend juntos.
