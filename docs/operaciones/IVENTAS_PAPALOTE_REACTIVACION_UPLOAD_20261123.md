# Papalote — creación controlada de plantillas de reactivación

## Objetivo y fuente

El inventario de iVentas de PAPALOTE_TJ tiene 102 registros, pero ninguna de
las 24 variantes `regresa_299_n3`, `regresa_399_n2` y `regresa_499_n1`
aparece en el canal configurado. Las plantillas de las otras sucursales
no se modifican. LOMA_BONITA (`449_lb`) queda expresamente fuera.

La fuente de textos es el Markdown facilitado por el operador (23-nov-2026),
normalizado a texto sin marcadores Markdown ni entidades HTML y empaquetado en
`backend/scripts/marketing/data/papalote_regresa_20261123.json`.
Esto **no certifica que el texto coincida al byte con las variantes que ya
existen en otras cuentas**: validar contenido y campos antes de campañas.

## Contratos

- 24 nombres exactos permitidos, exclusivamente `PAPALOTE_TJ`.
- Categoría iVentas: `MARKETING`. Sin imagen ni botones añadidos por la Suite.
- 22 mensajes contienen una aparición de `[Nombre]`, convertida en campo
  personalizado por posiciones UTF-16 mediante `validate_template`.
- `2regresa_299_n3` y `7regresa_399_n2` **no** contienen el marcador
  en el texto aportado. Se muestran `VERIFY_FIELDS`, no se cargan hasta
  comparar si son simples o si el copy necesita corrección.
- Leer primero el inventario autenticado y el historial local de cargas.
  Un nombre presente en cualquier canal de esta cuenta, o con una carga
  previa en Papalote, se **omite** y requiere revisión, no duplicación.
- El script solo **encola** las filas READY mediante
  `create_upload` existente, con `requested_by_user_id`, estados de
  carga y auditoría. Solo trabaja con el canal único y activo de Papalote.
- **No se vincula inmediatamente al catálogo**: al no enviar `catalog`,
  el worker registra `SUBMITTED` y no crea bindings de Suite. Hay que
  comprobar la aprobación en iVentas y después ejecutar la vista previa
  de `link_costa_iventas_templates`, que valida los siete canales.
- No se envían campañas ni WhatsApps, no se activan flags productivos.

## Pasos operativos

Una vez aprobado, mergeado y actualizado el servidor:

```bash
cd /home/adminrdp/sistematicketsultra
git switch main
git pull --ff-only
docker compose --profile iventas-template-upload build iventas-template-upload-worker
```

**Primero solo vista previa**, que consulta Papalote y las colas de Suite sin
escribir nada:

```bash
docker compose --profile iventas-template-upload run --rm --no-deps iventas-template-upload-worker \
  python -m scripts.marketing.queue_papalote_regresa_templates
```

Cotejar los 24 nombres y estados, así como que 22 figuren READY y dos
VERIFY_FIELDS en condiciones normales. **Aplicación** solo con autorización
expresa y operador global autorizado:

```bash
docker compose --profile iventas-template-upload run --rm --no-deps iventas-template-upload-worker \
  python -m scripts.marketing.queue_papalote_regresa_templates \
  --apply --actor-id 47 --confirm CARGAR_PAPALOTE
```

Esto encola las nuevas; el worker habilitado y operativo realiza la creación
en el portal con el flujo ya existente. El script exige
`IVENTAS_TEMPLATE_UPLOAD_ENABLED=true` antes de encolar.

Revisar historial de cargas y posteriormente aprobación real en iVentas.
Solo entonces repetir la vista previa de `link_costa_iventas_templates`
para comprobar canal, aprobación y conflictos antes de su `--apply`.

Las dos simples pendientes deberán resolverse comparando con un registro
aprobado de otra sucursal; no convertirlas a plantillas con una variable
inventada. Cualquier error o estado VERIFY en iVentas requiere inspección
antes de volver a intentar, para evitar duplicados.
