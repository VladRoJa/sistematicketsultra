# Google Ads M4 — alias family

Objetivo: aprobar 26 nombres de grupos locales en `track_branch_aliases`, fuente `google_ads_family`. La migración `b14d9e2c6f80` valida que las 26 sucursales estén activas y con IDs canónicos 1–26.

Alias excepcionales aprobados: `Paseo Villalta` → `SALTILLO_VILLALTA` (24) y `Sendero Sur Saltillo` → `SEND_SALTILLO` (18).

**Exclusiones:** `Marca` nacional y `EGADE` de preapertura no se asignan. Otros quince grupos sin actividad tampoco tienen mapping.

**Conciliación:** locales 17,624.73 MXN; excluidos 1,501.64 MXN; total ya registrado 19,126.37 MXN. Este hito no vuelve a sumar gasto, ni cambia valores del Funnel, Meta, CRM o ventas reales.

**Límite:** un nombre no identifica un grupo de anuncios entre campañas diferentes. La futura atribución debe comprobar cuenta, campaña, grupo e identidad canónica, y rechazar grupos nuevos sin aprobación. No conectar `google_ads_family` al Funnel por nombre únicamente.

**QA:** rechazo de cambios en IDs/estatus, alias conflictivos, reimportación segura e idempotente, rollback limitado a los alias originales. CI PostgreSQL 16.
