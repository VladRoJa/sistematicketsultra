# Google Ads API — M2: lecturas verificables y seguras (2026-10-09)

## Objetivo

Incorporar a Flask consultas **exclusivamente de lectura** contra Google Ads API, a partir del refresh token cifrado por OAuth M1. El cliente publicitario objetivo se fija en `GOOGLE_ADS_OAUTH_CUSTOMER_ID` (previsto: `2739125201`) y **nunca** se toma de la petición HTTP.

Se implementan dos rutas administrativas:

1. `GET /api/integrations/google-ads/account-check`: comprueba acceso REAL al customer configurado mediante GAQL `FROM customer`; también obtiene los IDs con acceso directo mediante `customers:listAccessibleCustomers`. Un cliente bajo MCC puede ser accesible aunque **no aparezca** en la lista de acceso directo. El resultado distingue estos casos.
2. `GET /api/integrations/google-ads/campaign-daily?date_from=2026-10-01&date_to=2026-10-09`: consulta métricas por fecha/campaña mediante `googleAds:searchStream` y devuelve desglose, moneda/horario de la cuenta y totales exactos.

Ambos endpoints requieren JWT válido y rol **ADMINISTRADOR** consultado en backend. El resultado no expone refresh token, developer token, secretos OAuth ni access token.

## Contrato de datos

- `cost_micros`: coste original entero devuelto por Google Ads.
- `cost`: cadena decimal de `cost_micros / 1_000_000` en la **moneda real de la cuenta**, no suposición MXN.
- `impressions`, `clicks`: enteros.
- `conversions`: cadena decimal correspondiente a conversiones atribuidas por Google Ads, **NO equivale a compras pagadas**. La conciliación con iVentas/GASCA corresponde a hitos posteriores.
- `segments.date`: fecha del reporte de Google Ads, referida a zona horaria de la cuenta (se incluye `account.timezone`).
- Consultas de 1 a 31 días consecutivos; rango obligatorio e ISO `YYYY-MM-DD`. Sin persistencia, sin agregados históricos y sin calendario/cron.
- Errores devueltos con códigos internos seguros. Respuestas de Google, URLs con parámetros sensibles y credenciales no se devuelven ni registran.
- Guardas de tamaño: más de 100 lotes o 5000 filas devuelve error explícito en vez de reporte recortado.

## Configuración privada en backend

Todas las variables del M1 siguen siendo necesarias para autorizar y leer. Adicionalmente:

- `GOOGLE_ADS_READONLY_ENABLED=true` habilita **solo** estas consultas. Sin la variable quedan deshabilitadas (503).
- `GOOGLE_ADS_DEVELOPER_TOKEN`: token API aprobado por Google Ads, secreto. El acceso **Explorer** puede utilizarse en cuentas de producción pero está limitado por cuota.
- `GOOGLE_ADS_API_VERSION=v25`: versión mayor documentada en octubre 2026. Si se omite, M2 usa v25; mantenerla actualizada antes del sunset.
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID=XXXXXXXXXX` (opcional): obligatorio cuando el acceso a la cuenta destino sea a través de un administrador/MCC que deba enviarse en la cabecera `login-customer-id`; usar ID del **manager**, no del cliente.
- `GOOGLE_ADS_OAUTH_CUSTOMER_ID=2739125201` debe coincidir exactamente con la identidad autorizada en M1. No se permite cambiar de cliente sin revisar su vínculo y reconectar según corresponda.

No colocar variables reales en Git, frontend, capturas ni tickets. La clave Fernet debe permanecer custodiada fuera del repositorio; cambiarla impide leer el token existente.

## Seguridad y límites

- El único POST externo a Google Ads es `googleAds:searchStream`, método de **consulta**; no existen llamadas `mutate`, ni escrituras en la base de datos.
- El OAuth `adwords` permite escritura por su diseño, pero el código M2 solo consulta recursos. El token no se entrega al navegador.
- `GET customers:listAccessibleCustomers` no basta para demostrar acceso al cliente final: la prueba real es ejecutar `SELECT customer.id...` sobre el ID objetivo y verificar coincidencia.
- Se valida el binding `record.customer_id == customer_id` antes de descifrar o llamar a Google.
- Se recupera access token temporal desde refresh token en cada solicitud con timeouts acotados; no se almacena su valor.
- Si Google revoca la autorización, M2 devuelve error seguro y exige reconexión, sin borrar automáticamente el refresh token.
- Todas las llamadas externas tienen dominios fijos HTTPS y redirects deshabilitados.

## Activación controlada

**No habilitar variables aún**. El usuario está preparando verificación OAuth de permisos sensibles, y M3 (pantalla administrativa de conexión y visualización) todavía no existe. No subir credenciales a GitHub, ni enviar a Google un video ficticio.

Cuando el video/flujo de demostración esté listo y se autorice operativamente:

1. Verificar el acceso Explorer/API y la cuenta administradora, si aplica.
2. Configurar variables privadas en el backend después de revisión.
3. Autorizar mediante OAuth M1 desde la misma sesión de navegador.
4. Ejecutar `account-check` con JWT administrador, revisar `customer_id`, moneda y zona horaria.
5. Consultar `campaign-daily` para un rango acotado y contrastar contra panel Google Ads.
6. Solo después diseñar snapshots canónicos y conciliaciones en Warehouse/Funnel.

## Validación automatizada

```bash
cd backend
pytest -q tests/google_ads/
```

M2 no añade ORM ni migraciones Alembic. Mantiene los módulos Tickets, PM, Warehouse, Track y Funnel intactos. La UI y conexión con Warehouse corresponden a hitos posteriores.

Referencias oficiales Google:
- https://developers.google.com/google-ads/api/reference/rpc/v25/CustomerService/ListAccessibleCustomers?transport=rest
- https://developers.google.com/google-ads/api/rest/common/search
- https://developers.google.com/google-ads/api/rest/auth
- https://developers.google.com/google-ads/api/docs/sunset-dates
