# Suite Ultra — Auditoría visual Playwright de Campañas V2

**Estado:** auditor anónimo aprobado; auditoría autenticada pendiente de ejecutarse. Permite QA sintético o datos reales **solo en localhost con autorización explícita**.

## Dos modos (nunca confundir)

**Anónimo / CI:** compila Angular, abre Chromium en 1440×900, 1024×768 y
390×844 y verifica que la ruta protegida /#/marketing/campaigns-v2 redirija
a login. Guarda capturas, sin backend ni credenciales. PASS aquí **no aprueba**
la UI del módulo.

**Autenticado / QA o local:** usa una cuenta autorizada, en un ambiente QA
sintético o una instancia **localhost con datos reales**. Captura Crear Ticket V1 (referencia), Nueva campaña,
Resultados, Historial, Crear desde Excel, Prueba interna, Estado de los canales,
Plantillas/canales/tarifas, Límites de envío y detalle de campaña presembrada
(si existe). No necesita crear campañas ni disparar preview para auditar.

## Seguridad

- Bloquea todas las peticiones HTTP POST, PUT, PATCH y DELETE excepto
  POST /api/auth/login, que se permite exclusivamente durante login QA.
- No pulsa Congelar, Guardar, Autorizar, Enviar, Importar ni acciones mutantes.
- No registra bodies, credenciales, tokens, cookies o localStorage.
- Exige **exactamente una** confirmación: QA sintético o real local de solo lectura,
  el hostname exacto, un usuario autorizado y su contraseña privada.
- El modo real está restringido a localhost / 127.0.0.1 / ::1; rechaza
  dominios externos y destinos API remotos no autorizados.
- Las capturas con datos reales pueden mostrar nombres, teléfonos y métricas:
  **NO subirlas a GitHub, tickets, chats, Drive ni CI**. El directorio
  /artifacts/ está excluido mediante el .gitignore de la raíz.
- Nunca ejecutar esta modalidad frente a una URL de producción. Las capturas
  autenticadas solo permanecen locales; CI solo publica el login anónimo.

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
    SUITE_QA_ALLOWED_API_ORIGIN    (opcional, origen HTTPS exacto si API está en otro host/puerto)
    SUITE_QA_SYNTHETIC_DATA_CONFIRMED=YES

El hostname debe coincidir exactamente con el de --base-url; QA remota exige
HTTPS. Las peticiones /api/ hacia orígenes no permitidos se bloquean:
por defecto solo se autoriza el mismo origen de frontend, más el origen QA
adicional explícitamente declarado. Verificar que frontend QA no apunte a una
API de producción antes de ejecutar. Ejemplo de hostname inválido:

    python scripts/qa/campaign_v2_visual_audit.py --mode authenticated --base-url https://qa.example.invalid

Los resultados quedan en artifacts/campaign-v2-visual/report.json y sus PNG.
No subir capturas autenticadas hasta verificar que son 100% sintéticas.

## Ejecución autenticada con PostgreSQL real local (Windows / PowerShell)

Esta opción usa el frontend local http://localhost:4200 y el backend configurado
en el proxy Angular (normalmente 127.0.0.1:5000). Los endpoints /api se consultan
en el mismo origen. **No altera la base de datos**, aunque el login pueda crear
registros normales de sesión/auditoría. El navegador bloquea otras llamadas HTTP
de escritura. Nunca establecer SUITE_QA_SYNTHETIC_DATA_CONFIRMED=YES
sobre datos reales.

Desde la raíz del repositorio en una terminal PowerShell:

    git pull --ff-only
    py -m pip install playwright==1.55.0
    py -m playwright install chromium
    $env:SUITE_QA_ALLOWED_HOST = "localhost"
    $env:SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED = "YES"
    $env:SUITE_QA_USERNAME = Read-Host "Usuario de la Suite local"
    $secure = Read-Host "Contraseña de la Suite local" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $env:SUITE_QA_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    py scripts/qa/campaign_v2_visual_audit.py --mode authenticated --base-url http://localhost:4200 --out artifacts/campaign-v2-visual
    Remove-Item Env:SUITE_QA_PASSWORD

Previamente verificar que Angular y Flask están levantados, que /api usa el
proxy local y que **ninguna configuración** apunta a producción. Si se desea
permitir explícitamente otra API en un puerto local, usar
SUITE_QA_ALLOWED_API_ORIGIN=http://127.0.0.1:5000; jamás una API remota
en modo real local.

Resultados: artifacts/campaign-v2-visual/report.json y capturas PNG que
contendrán datos reales locales. Compartir únicamente un resumen numérico
del reporte o capturas redactadas. Un exit code 1 es normal cuando se detectan
problemas visuales o pantallas bloqueadas: no significa que se enviaran datos.

## Métricas y gate

Heurísticas: tamaño efectivo de etiqueta flotante (<9.5px), tamaño de valor
(<12px), texto o placeholder de input más ancho que el control y overflow
horizontal por panel. PASS = pruebas automáticas superadas; FAIL_VISUAL =
hallazgo medido; BLOCKED = acceso/dato/caso inaccesible. BLOCKED no es PASS.
El exit code es distinto de cero si hay hallazgos o casos bloqueados.

**Gate:** CI anónimo PASS, auditoría local autenticada con consentimiento explícito
(o QA sintética) y revisión humana de las capturas frente a Crear Ticket V1. Solo después
priorizar correcciones en una PR separada. Esta PR es infraestructura de QA,
sin cambios en TS, HTML, CSS, backend, permisos, DB ni envíos.
