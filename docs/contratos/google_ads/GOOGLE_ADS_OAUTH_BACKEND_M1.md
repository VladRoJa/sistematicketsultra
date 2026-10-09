# Google Ads OAuth — Backend M1

## Alcance

- Integración OAuth 2.0 exclusivamente para **administradores** de Suite Ultra.
- \`POST /api/integrations/google-ads/oauth/start\` (Bearer JWT, ADMINISTRADOR): devuelve URL Google y establece cookie de nonce.
- \`GET /api/integrations/google-ads/oauth/callback\` (sin JWT): verifica estado firmado de 10 minutos, nonce de navegador y PKCE, valida rol actual, intercambia el código por un refresh token y lo cifra con Fernet antes de guardarlo.
- \`GET /api/integrations/google-ads/oauth/status\` (Bearer JWT, ADMINISTRADOR): devuelve configuración, presencia de credenciales y cuenta objetivo; **nunca** devuelve tokens.
- La tabla \`google_ads_oauth_credentials\` tiene una sola fila y requiere migración Alembic.
- Este M1 no consulta Google Ads API, no valida todavía que la cuenta autorizada tenga acceso al cliente objetivo y no ejecuta scheduler ni ingesta Warehouse.

## Seguridad y despliegue

- **OFF por defecto:** \`GOOGLE_ADS_OAUTH_ENABLED\` ausente o distinto de \`true\` devuelve 503 en inicio/callback.
- Colocar secretos únicamente en el entorno privado de producción (p. ej. \`.env.docker\` **nunca versionado**), no en Angular ni en GitHub.
- Variables:
  - \`GOOGLE_ADS_OAUTH_ENABLED=true\`
  - \`GOOGLE_ADS_OAUTH_CLIENT_ID\`: del JSON OAuth de Google Cloud.
  - \`GOOGLE_ADS_OAUTH_CLIENT_SECRET\`: del mismo JSON, secreto.
  - \`GOOGLE_ADS_OAUTH_CUSTOMER_ID=2739125201\` (verificar ID antes de habilitar).
  - \`GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY\`: Fernet de 32 bytes codificados URL-safe Base64. Generar una vez con \`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\` en una terminal privada. Custodiar y respaldar de forma segura.
- El \`redirect_uri\` se fija deliberadamente en \`https://suiteultragym.com/api/integrations/google-ads/oauth/callback\` y debe coincidir exactamente con Google Cloud.
- Iniciar consentimiento mediante POST desde la **misma sesión de navegador** con JWT de administrador; abrir la URL devuelta en la misma pestaña para preservar la cookie Secure/SameSite=Lax.
- Proteger cookie, secretos, token cifrado y respaldos. **No** incluir códigos de autorización, cookies, secretos o tokens en capturas/logs/tickets.
- El permiso \`https://www.googleapis.com/auth/adwords\` permite escritura en Google Ads. El M1 no contiene llamadas de modificación de campañas.
- La autorización existente se reemplaza solo si Google entrega un refresh token válido; un error en el intercambio no debe borrar el anterior.
- La migración precede a cualquier autorización; ejecutar únicamente después de resolver las demás ramas/migraciones que entren en \`main\` y revisar la cabeza de Alembic.
- El botón de inicio no existe todavía en Angular. No activar en producción antes de completar requisitos de publicación/verificación OAuth y el control de despliegue.
- Si cambia \`GOOGLE_ADS_OAUTH_TOKEN_ENCRYPTION_KEY\` sin re-cifrar las credenciales existentes, no podrán descifrarse y habrá que reconectar.
- La página de información pública y privacidad siguen en PR #831 (independiente).

## Validación posterior (sin utilizar credenciales reales en pruebas)

1. \`pytest -q backend/tests/google_ads/\` desde la raíz con entorno Python de backend disponible.
2. Verificar la migración actual de \`main\` antes de un merge (el proyecto mantiene una única cabeza Alembic).
3. Verificar que sin feature flag los endpoints no permiten iniciar consentimiento.
4. Con la integración habilitada, probar un **único** consentimiento desde una cuenta Google autorizada; comprobar que no se filtra un refresh token en HTTP ni logs.
5. En un M2 separado: confirmar \`customers:listAccessibleCustomers\` / permisos sobre cliente objetivo y preparar la sincronización segura de reportes al Warehouse.

## Pendientes de revisión

- Validación del responsable de Ultra Gym sobre política de privacidad y publicación OAuth.
- Revisión de permisos administrativos y custodia de la clave Fernet.
- Verificar CI/pytest, el historial de migraciones y rebase antes de fusionar.
