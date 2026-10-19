# Suite Ultra — Auditoría visual Playwright de Campañas V2

**Estado:** infraestructura DRAFT, pendiente de auditoría autenticada con datos sintéticos.

## Dos modos (nunca confundir)

**Anónimo / CI:** compila Angular, abre Chromium en 1440×900, 1024×768 y
390×844 y verifica que la ruta protegida /#/marketing/campaigns-v2 redirija
a login. Guarda capturas, sin backend ni credenciales. PASS aquí **no aprueba**
la UI del módulo.

**Autenticado / QA:** usa una cuenta temporal de un ambiente no productivo
con datos sintéticos. Captura Crear Ticket V1 (referencia), Nueva campaña,
Resultados, Historial, Crear desde Excel, Prueba interna, Estado de los canales,
Plantillas/canales/tarifas, Límites de envío y detalle de campaña presembrada
(si existe). No necesita crear campañas ni disparar preview para auditar.

## Seguridad

- Bloquea todas las peticiones HTTP POST, PUT, PATCH y DELETE excepto
  POST /api/auth/login, que se permite exclusivamente durante login QA.
- No pulsa Congelar, Guardar, Autorizar, Enviar, Importar ni acciones mutantes.
- No registra bodies, credenciales, tokens, cookies o localStorage.
- Exige SUITE_QA_SYNTHETIC_DATA_CONFIRMED=YES, hostname QA explícito,
  usuario temporal y contraseña temporal.
- No ejecutar el modo autenticado en producción o sobre datos reales:
  las capturas pueden contener nombres, teléfonos y métricas. Los artefactos
  autenticados permanecen locales; CI solo publica capturas del login anónimo.

## Ejecución anónima local

Instalar Playwright Python 1.55.0, Chromium y dependencias del frontend.
Compilar Angular con npm ci y npm run build dentro de frontend. Desde la
raíz del repo ejecutar el servidor estático del build:

    python -m http.server 4173 --directory frontend/dist/frontend-angular

Luego, desde otra terminal:

    python scripts/qa/campaign_v2_visual_audit.py --mode anonymous --base-url http://127.0.0.1:4173

En CI lo hace automáticamente el workflow Campaign V2 Playwright Visual Audit.

## Ejecución autenticada en QA sintético

Levantar Suite Ultra completa en QA aislado. La cuenta QA necesita poder ver
Campañas V2 y Herramientas; preparar una campaña sintética ya congelada
para validar el diálogo de detalle. Configurar en una sesión privada
las variables siguientes, sin pegar contraseñas en commits ni en el chat:

    SUITE_QA_USERNAME
    SUITE_QA_PASSWORD
    SUITE_QA_ALLOWED_HOST
    SUITE_QA_SYNTHETIC_DATA_CONFIRMED=YES

El hostname debe coincidir exactamente con el de --base-url; QA remota exige
HTTPS. Ejemplo de formato con un hostname deliberadamente inválido:

    python scripts/qa/campaign_v2_visual_audit.py --mode authenticated --base-url https://qa.example.invalid

Los resultados quedan en artifacts/campaign-v2-visual/report.json y sus PNG.
No subir capturas autenticadas hasta verificar que son 100% sintéticas.

## Métricas y gate

Heurísticas: tamaño efectivo de etiqueta flotante (<9.5px), tamaño de valor
(<12px), texto o placeholder de input más ancho que el control y overflow
horizontal por panel. PASS = pruebas automáticas superadas; FAIL_VISUAL =
hallazgo medido; BLOCKED = acceso/dato/caso inaccesible. BLOCKED no es PASS.
El exit code es distinto de cero si hay hallazgos o casos bloqueados.

**Gate:** CI anónimo PASS, auditoría QA autenticada con datos sintéticos y
revisión humana de todas las capturas frente a Crear Ticket V1. Solo después
priorizar correcciones en una PR separada. Esta PR es infraestructura de QA,
sin cambios en TS, HTML, CSS, backend, permisos, DB ni envíos.
