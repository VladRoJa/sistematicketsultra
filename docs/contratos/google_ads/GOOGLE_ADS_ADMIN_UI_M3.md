# Google Ads M3 — Interfaz administrativa

## Alcance

- Nueva ruta Angular `/#/marketing/google-ads` con `AdminGuard` y enlace en Marketing y Conversión solo para administradores.
- Componentes separados: `.ts`, `.html`, `.css`; servicios HTTP tipados.
- Estado de OAuth M1; botón Conectar/Reconectar en la **misma pestaña** para conservar nonce cookie; URL de Google autorizada mediante lista estricta.
- Comprobación de acceso real vía M2 y consulta diaria con máximo 31 días.
- Indicadores de inversión, clics, impresiones y conversiones reportadas por Google Ads; conversiones no equivalen a ventas pagadas validadas.
- Respuestas únicamente reales: no introducir cifras ficticias en producción.

## Seguridad

- La UI no almacena secretos, tokens ni códigos OAuth.
- El backend M1/M2 continúa validando administrador, configuración y cuenta.
- Kill switches de backend desactivados por defecto: sin credenciales, los botones de consulta no proporcionan información real.
- Ningún endpoint muta campañas Google Ads ni persiste los resultados en Warehouse.
- Finalizado el consentimiento, el callback M1 devuelve una página de confirmación. El administrador regresa a la pantalla y presiona Actualizar estado.

## Pruebas requeridas antes de merge

- Compilar Angular (`npm ci` y `npm run build`) con entorno funcional. En el QA remoto inicial `npm ci` falló por `ERR_INVALID_ARG_TYPE` y error de limpieza `EPERM` bajo Windows, antes de llegar a compilar. No tratarlo como prueba superada.
- Verificar navegación y estado desconectado en móvil y escritorio.
- Validar que usuario no ADMINISTRADOR no acceda a la ruta ni vea el menú; corroborar 403 del backend.
- Revisar configuración privada de cliente OAuth y developer-token antes del consentimiento real.
- Demostrar con datos auténticos el flujo de consentimiento, cuenta y consulta para el video de Google; no simular accesos.

## No incluido

- No hay migraciones, cron, ingesta Warehouse, Funnel ni cambios en los permisos de backend.
- No se genera video, no se envía todavía solicitud de verificación OAuth.
