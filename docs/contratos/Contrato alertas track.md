
martes 11:27 a.m.

Pasted text.txt
Documento


Pasted text.txt
Documento


Pasted text.txt
Documento


Pasted text.txt
Documento
la viga esta cancelada

ayer 9:10 a.m.

Pasted text.txt
Documento


Pasted text.txt
Documento


Pasted text.txt
Documento


Pasted text.txt
Documento

si sobre la ocupacion la meta es 2.0 pero cada mes se imponen metas, sobre esas metas es que hay que hacer las alertas, ya que tambien esas metas de ocupacion es lo que se mide para ganar el bono, mira meta ocupacion julio es el punto, y en proyeccion de usuarios al cierre esta en unidades 


Pasted text.txt
Documento


Pasted text.txt
Documento
asi? 




Pasted text.txt
Documento


Pasted text.txt
Documento
SQL Error [42601]: ERROR: syntax error at or near "FROM"
  Position: 5

Error position: line: 2 pos: 4


no se que pase me marca error ahi y esta es la query que estoy corriendo

Pensado durante 13s
Va. Siguiente mini-prueba: F1.4B — agregar driver secundario nacional.

No corras la pesada. Esto usa:

tmp_track_alert_executive_ranking
La idea es que el resultado siga diciendo:

causa_dominante_nacional = PROYECCION_CIERRE
driver_operativo_nacional = OCUPACION
pero además agregue:

driver_secundario_nacional = ARPU_SECUNDARIO
porque en tu F1.4 el ARPU nacional salió -5.83%, no domina, pero sí explica parte de la brecha.

/*
F1.4B — Resumen nacional ejecutivo con driver secundario
Usa tmp_track_alert_executive_ranking.
Solo lectura.
Etapa: investigación / contrato funcional.
*/

WITH regional_rollup AS (
    SELECT
        track_date,
        version_id,
        version_type,
        generation_mode,

        COALESCE(region_key, 'SIN_REGION') AS region_key,
        COALESCE(region_label, 'Sin región asignada') AS region_label,

        COUNT(*) FILTER (WHERE alertability_status = 'ALERTABLE') AS sucursales_alertables,
        COUNT(*) FILTER (WHERE severity_final = 'critico') AS sucursales_criticas,
        COUNT(*) FILTER (WHERE severity_final = 'riesgo') AS sucursales_riesgo,

        SUM(COALESCE(projected_close, 0)) AS proyeccion_cierre_region,
        SUM(COALESCE(meta_faycgo_mes, 0)) AS meta_faycgo_region,

        SUM(COALESCE(projected_close, 0))
        - SUM(COALESCE(meta_faycgo_mes, 0)) AS brecha_proyectada_region_monto,

        SUM(COALESCE(usuarios_activos_actual, 0)) AS usuarios_actuales_region,
        SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)) AS meta_usuarios_cierre_region,
        SUM(COALESCE(brecha_usuarios_ocupacion, 0)) AS brecha_usuarios_region,

        (
            SUM(COALESCE(usuarios_activos_actual, 0))::numeric
            / NULLIF(SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)), 0)
        ) AS pct_alcance_ocupacion_region,

        (
            SUM(COALESCE(projected_close, 0))
            / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
        ) AS arpu_proyectado_region,

        (
            SUM(COALESCE(meta_arpu_mes, 0) * COALESCE(usuarios_activos_actual, 0))
            / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
        ) AS meta_arpu_region_ponderada,

        (
            SUM(COALESCE(ingreso_real_agregadora_mtd, 0))
            / NULLIF(SUM(COALESCE(ingreso_real_total_mtd, 0)), 0)
        ) AS agregadoras_share_region,

        CASE
            WHEN COUNT(*) FILTER (WHERE alertability_status = 'ALERTABLE') = 0 THEN
                'SIN_ALERTABLES'

            WHEN (
                SUM(COALESCE(usuarios_activos_actual, 0))::numeric
                / NULLIF(SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)), 0)
            ) < 0.90
              OR SUM(COALESCE(brecha_usuarios_ocupacion, 0)) <= -500
            THEN 'OCUPACION'

            WHEN (
                (
                    SUM(COALESCE(projected_close, 0))
                    / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
                )
                /
                NULLIF(
                    (
                        SUM(COALESCE(meta_arpu_mes, 0) * COALESCE(usuarios_activos_actual, 0))
                        / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
                    ),
                    0
                )
                - 1
            ) <= -0.07
            THEN 'ARPU'

            WHEN (
                SUM(COALESCE(ingreso_real_agregadora_mtd, 0))
                / NULLIF(SUM(COALESCE(ingreso_real_total_mtd, 0)), 0)
            ) >= 0.25
            THEN 'DEPENDENCIA_AGREGADORAS'

            WHEN (
                SUM(COALESCE(usuarios_activos_actual, 0))::numeric
                / NULLIF(SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)), 0)
            ) < 0.97
              OR SUM(COALESCE(brecha_usuarios_ocupacion, 0)) <= -150
            THEN 'OCUPACION_SECUNDARIA'

            WHEN (
                (
                    SUM(COALESCE(projected_close, 0))
                    / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
                )
                /
                NULLIF(
                    (
                        SUM(COALESCE(meta_arpu_mes, 0) * COALESCE(usuarios_activos_actual, 0))
                        / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
                    ),
                    0
                )
                - 1
            ) <= -0.03
            THEN 'ARPU_SECUNDARIO'

            WHEN (
                SUM(COALESCE(ingreso_real_agregadora_mtd, 0))
                / NULLIF(SUM(COALESCE(ingreso_real_total_mtd, 0)), 0)
            ) >= 0.15
            THEN 'AGREGADORAS_SECUNDARIA'

            ELSE 'SIN_DRIVER_OPERATIVO_DOMINANTE'
        END AS driver_operativo_region

    FROM tmp_track_alert_executive_ranking
    GROUP BY
        track_date,
        version_id,
        version_type,
        generation_mode,
        COALESCE(region_key, 'SIN_REGION'),
        COALESCE(region_label, 'Sin región asignada')
),

national_base AS (
    SELECT
        track_date,
        version_id,
        version_type,
        generation_mode,

        COUNT(*) FILTER (WHERE alertability_status = 'ALERTABLE') AS sucursales_alertables,
        COUNT(*) FILTER (WHERE severity_final = 'critico') AS sucursales_criticas,
        COUNT(*) FILTER (WHERE severity_final = 'riesgo') AS sucursales_riesgo,
        COUNT(*) FILTER (WHERE severity_final = 'atencion') AS sucursales_atencion,
        COUNT(*) FILTER (WHERE severity_final = 'sin_alerta') AS sucursales_sin_alerta,
        COUNT(*) FILTER (WHERE severity_final = 'blocked') AS sucursales_bloqueadas,

        SUM(COALESCE(meta_faycgo_mes, 0)) AS meta_faycgo_nacional,
        SUM(COALESCE(projected_close, 0)) AS proyeccion_cierre_nacional,

        SUM(COALESCE(projected_close, 0))
        - SUM(COALESCE(meta_faycgo_mes, 0)) AS brecha_proyectada_nacional_monto,

        (
            SUM(COALESCE(projected_close, 0))
            / NULLIF(SUM(COALESCE(meta_faycgo_mes, 0)), 0)
            - 1
        ) AS brecha_proyectada_nacional_pct,

        SUM(COALESCE(usuarios_activos_actual, 0)) AS usuarios_actuales_nacional,
        SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)) AS meta_usuarios_cierre_nacional,
        SUM(COALESCE(brecha_usuarios_ocupacion, 0)) AS brecha_usuarios_nacional,

        (
            SUM(COALESCE(usuarios_activos_actual, 0))::numeric
            / NULLIF(SUM(COALESCE(proyeccion_usuarios_cierre_mes, 0)), 0)
        ) AS pct_alcance_ocupacion_nacional,

        SUM(COALESCE(ingreso_real_base_mtd, 0)) AS ingreso_base_mtd_nacional,
        SUM(COALESCE(ingreso_real_agregadora_mtd, 0)) AS ingreso_agregadora_mtd_nacional,
        SUM(COALESCE(ingreso_real_total_mtd, 0)) AS ingreso_total_mtd_nacional,

        (
            SUM(COALESCE(ingreso_real_agregadora_mtd, 0))
            / NULLIF(SUM(COALESCE(ingreso_real_total_mtd, 0)), 0)
        ) AS agregadoras_share_nacional,

        (
            SUM(COALESCE(projected_close, 0))
            / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
        ) AS arpu_proyectado_nacional,

        (
            SUM(COALESCE(meta_arpu_mes, 0) * COALESCE(usuarios_activos_actual, 0))
            / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
        ) AS meta_arpu_nacional_ponderada,

        (
            (
                SUM(COALESCE(projected_close, 0))
                / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
            )
            /
            NULLIF(
                (
                    SUM(COALESCE(meta_arpu_mes, 0) * COALESCE(usuarios_activos_actual, 0))
                    / NULLIF(SUM(COALESCE(usuarios_activos_actual, 0)), 0)
                ),
                0
            )
            - 1
        ) AS brecha_arpu_nacional_pct

    FROM tmp_track_alert_executive_ranking
    GROUP BY
        track_date,
        version_id,
        version_type,
        generation_mode
),

national_classified AS (
    SELECT
        nb.*,

        CASE
            WHEN nb.sucursales_alertables = 0 THEN 'SIN_ALERTABLES'
            WHEN nb.brecha_proyectada_nacional_pct < -0.01 THEN 'PROYECCION_CIERRE'
            ELSE 'SIN_ALERTA_NACIONAL'
        END AS causa_dominante_nacional,

        CASE
            WHEN nb.sucursales_alertables = 0 THEN 'SIN_ALERTABLES'

            WHEN nb.pct_alcance_ocupacion_nacional < 0.90
              OR nb.brecha_usuarios_nacional <= -1500
            THEN 'OCUPACION'

            WHEN nb.brecha_arpu_nacional_pct <= -0.07
            THEN 'ARPU'

            WHEN nb.agregadoras_share_nacional >= 0.25
            THEN 'DEPENDENCIA_AGREGADORAS'

            WHEN nb.pct_alcance_ocupacion_nacional < 0.97
              OR nb.brecha_usuarios_nacional <= -500
            THEN 'OCUPACION_SECUNDARIA'

            WHEN nb.brecha_arpu_nacional_pct <= -0.03
            THEN 'ARPU_SECUNDARIO'

            WHEN nb.agregadoras_share_nacional >= 0.15
            THEN 'AGREGADORAS_SECUNDARIA'

            ELSE 'SIN_DRIVER_OPERATIVO_DOMINANTE'
        END AS driver_operativo_nacional,

        CASE
            WHEN nb.sucursales_alertables = 0 THEN 'SIN_ALERTABLES'

            WHEN (
                nb.brecha_arpu_nacional_pct <= -0.03
                AND NOT (
                    nb.brecha_arpu_nacional_pct <= -0.07
                    AND NOT (
                        nb.pct_alcance_ocupacion_nacional < 0.90
                        OR nb.brecha_usuarios_nacional <= -1500
                    )
                )
            ) THEN 'ARPU_SECUNDARIO'

            WHEN (
                nb.agregadoras_share_nacional >= 0.15
                AND nb.agregadoras_share_nacional < 0.25
            ) THEN 'AGREGADORAS_SECUNDARIA'

            WHEN (
                nb.pct_alcance_ocupacion_nacional < 0.97
                OR nb.brecha_usuarios_nacional <= -500
            )
            AND NOT (
                nb.pct_alcance_ocupacion_nacional < 0.90
                OR nb.brecha_usuarios_nacional <= -1500
            ) THEN 'OCUPACION_SECUNDARIA'

            ELSE 'SIN_DRIVER_SECUNDARIO'
        END AS driver_secundario_nacional

    FROM national_base nb
)

SELECT
    nc.track_date,
    nc.version_id,
    nc.version_type,
    nc.generation_mode,

    nc.sucursales_alertables,
    nc.sucursales_criticas,
    nc.sucursales_riesgo,
    nc.sucursales_atencion,
    nc.sucursales_sin_alerta,
    nc.sucursales_bloqueadas,

    ROUND(nc.meta_faycgo_nacional::numeric, 2) AS meta_faycgo_nacional,
    ROUND(nc.proyeccion_cierre_nacional::numeric, 2) AS proyeccion_cierre_nacional,
    ROUND(nc.brecha_proyectada_nacional_monto::numeric, 2) AS brecha_proyectada_nacional_monto,
    ROUND((nc.brecha_proyectada_nacional_pct * 100)::numeric, 2) AS brecha_proyectada_nacional_pct,

    nc.usuarios_actuales_nacional,
    nc.meta_usuarios_cierre_nacional,
    nc.brecha_usuarios_nacional,
    ROUND((nc.pct_alcance_ocupacion_nacional * 100)::numeric, 2) AS pct_alcance_ocupacion_nacional,

    ROUND(nc.ingreso_base_mtd_nacional::numeric, 2) AS ingreso_base_mtd_nacional,
    ROUND(nc.ingreso_agregadora_mtd_nacional::numeric, 2) AS ingreso_agregadora_mtd_nacional,
    ROUND(nc.ingreso_total_mtd_nacional::numeric, 2) AS ingreso_total_mtd_nacional,
    ROUND((nc.agregadoras_share_nacional * 100)::numeric, 2) AS agregadoras_share_nacional_pct,

    ROUND(nc.arpu_proyectado_nacional::numeric, 2) AS arpu_proyectado_nacional,
    ROUND(nc.meta_arpu_nacional_ponderada::numeric, 2) AS meta_arpu_nacional_ponderada,
    ROUND((nc.brecha_arpu_nacional_pct * 100)::numeric, 2) AS brecha_arpu_nacional_pct,

    nc.causa_dominante_nacional,
    nc.driver_operativo_nacional,
    nc.driver_secundario_nacional,

    (
        SELECT STRING_AGG(
            CONCAT(
                rr.region_label,
                ' [criticas ',
                rr.sucursales_criticas,
                ' / riesgo ',
                rr.sucursales_riesgo,
                ' / brecha $',
                ROUND(rr.brecha_proyectada_region_monto::numeric, 0),
                ' / usuarios ',
                rr.brecha_usuarios_region,
                ' / driver ',
                rr.driver_operativo_region,
                ']'
            ),
            ' || '
            ORDER BY
                rr.sucursales_criticas DESC,
                rr.brecha_proyectada_region_monto ASC NULLS LAST
        )
        FROM regional_rollup rr
        WHERE rr.sucursales_alertables > 0
    ) AS regiones_prioritarias,

    CASE
        WHEN nc.sucursales_alertables = 0 THEN
            'Sin sucursales alertables. Revisar configuración general.'

        WHEN nc.brecha_proyectada_nacional_pct <= -0.15
         AND nc.driver_operativo_nacional = 'OCUPACION' THEN
            'Intervención nacional inmediata: la proyección de cierre está muy por debajo de meta y la ocupación nacional está presionada. Priorizar recuperación de usuarios por región.'

        WHEN nc.brecha_proyectada_nacional_pct <= -0.15
         AND nc.driver_operativo_nacional = 'ARPU' THEN
            'Intervención nacional inmediata: la proyección de cierre está muy por debajo de meta y hay presión fuerte de ARPU. Revisar descuentos, mezcla de ingresos, domiciliados y ticket promedio.'

        WHEN nc.brecha_proyectada_nacional_pct <= -0.15 THEN
            'Intervención nacional inmediata: revisar plan comercial, ritmo FAYCGO y regiones críticas.'

        WHEN nc.sucursales_criticas >= 5 THEN
            'Seguimiento ejecutivo diario: hay múltiples sucursales críticas aunque la brecha nacional todavía podría ser recuperable.'

        WHEN nc.sucursales_riesgo >= 5 THEN
            'Seguimiento preventivo nacional: varias sucursales están en riesgo recuperable.'

        WHEN nc.sucursales_atencion >= 1 THEN
            'Monitorear desviaciones tempranas. No hay incendio nacional.'

        ELSE
            'Sin alertas nacionales relevantes.'
    END AS accion_nacional_sugerida

FROM national_classified nc;

2026-07-09	2478	preview_operativo	manual_preview	25	20	4	1	0	1	26801186.45	20685833.83	-6115352.62	-22.82	33866	37613	-3747	90.04	5892404.20	773625.79	6666029.99	11.61	610.81	648.65	-5.83	PROYECCION_CIERRE	OCUPACION	ARPU_SECUNDARIO	Tijuana / Rosarito / Ensenada [criticas 7 / riesgo 0 / brecha $-1844975 / usuarios -1396 / driver OCUPACION] || CDMX / Ixtapaluca / Tlalnepantla [criticas 4 / riesgo 0 / brecha $-1460481 / usuarios -1265 / driver OCUPACION] || Monterrey / Saltillo / Chihuahua [criticas 3 / riesgo 1 / brecha $-1318013 / usuarios -617 / driver OCUPACION] || Mexicali / San Luis [criticas 3 / riesgo 2 / brecha $-777588 / usuarios -325 / driver OCUPACION_SECUNDARIA] || Culiacán / La Paz [criticas 3 / riesgo 1 / brecha $-714297 / usuarios -305 / driver OCUPACION_SECUNDARIA]	Intervención nacional inmediata: la proyección de cierre está muy por debajo de meta y la ocupación nacional está presionada. Priorizar recuperación de usuarios por región.

Pensado durante 4s
Sí, F1.4B quedó perfecto para contrato.

Ya tenemos la lectura nacional completa:

causa_dominante_nacional = PROYECCION_CIERRE
driver_operativo_nacional = OCUPACION
driver_secundario_nacional = ARPU_SECUNDARIO
La interpretación ejecutiva queda muy clara:

La proyección nacional de cierre está -22.82% debajo de meta,
con una brecha estimada de -$6.1M.

El driver operativo principal es ocupación:
faltan 3,747 usuarios contra la meta nacional de cierre.

El driver secundario es ARPU:
ARPU proyectado $610.81 vs meta ponderada $648.65,
brecha de -5.83%.
Y las regiones prioritarias también quedaron bien ordenadas:

1. Tijuana / Rosarito / Ensenada
2. CDMX / Ixtapaluca / Tlalnepantla
3. Monterrey / Saltillo / Chihuahua
4. Mexicali / San Luis
5. Culiacán / La Paz
Decisión
Esto ya lo marcaría como:

F1.4B — Resumen nacional ejecutivo validado para contrato funcional
Hallazgo para el contrato final
El contrato debe separar tres niveles:

1. Resultado afectado:
   PROYECCION_CIERRE

2. Driver principal:
   OCUPACION

3. Driver secundario:
   ARPU_SECUNDARIO
Eso evita que la alerta diga solo “vamos abajo en dinero” y permite explicar:

Vamos abajo principalmente porque faltan usuarios,
y adicionalmente el ARPU nacional está presionado.
Con esto ya tenemos cubiertos los tres niveles de lectura:

F1.2 — sucursal
F1.3 — región
F1.4 — nacional
El siguiente bloque de investigación ya sería empezar a convertir todo esto en contrato funcional escrito, no más query por ahora, salvo que quieras validar algún caso borde.


va

hoy 7:35 a.m.
Listo, te dejé el .md para meterlo al repo:

track_alertas_inteligentes_contrato_funcional_v0_1.md

Ruta sugerida en el repo:

docs/contracts/track_alertas_inteligentes_contrato_funcional_v0_1.md



Te paso el original que habiamos creado o este ya incluye todo?

Este .md ya incluye todo lo que acabamos de validar:

F1.2 — sucursal
F1.3 — regional
F1.4 / F1.4B — nacional
drivers principal/secundario
ocupación contra meta mensual
curva esperada
alertabilidad
LA_VIGA / SERRANIA
performance con temp table
pendientes antes de implementación
criterios de aceptación
Pero sí te diría algo: si el original que habíamos creado tenía decisiones anteriores de F0 o estructura de producto que no recuerdas si están aquí, pásamelo y lo fusionamos bien.

Mi lectura es:

Este archivo ya sirve como contrato funcional principal v0.1.
El original solo lo necesitaríamos para no perder cosas como:

- lifecycle detallado de alertas
- nombres de tablas candidatas
- endpoints candidatos
- permisos por rol
- auditoría de vista/atendida/cerrada
- diseño UI inicial
Si me lo pasas, no lo reemplazo a ciegas: lo comparo contra este y te devuelvo una versión consolidada para repo.



Markdown.md pegado
Archivo
hay que hacer uno solo de ambos. Este ya seria el contrato completo. Solo me gustaria que pongas las reglas de negocio hasta arriba por que se que este modulo va a pasar por varias revisiones

Procesó durante 22s
Listo. Hice un solo contrato completo fusionando el original que subiste con lo validado en F1.2/F1.3/F1.4, y puse Reglas de negocio maestras hasta arriba para que sobrevivan a revisiones futuras. 


suite_ultra_track_alertas_inteligentes_contrato_funcional_completo_f1.md

Ruta sugerida en el repo:

docs/contracts/suite_ultra_track_alertas_inteligentes_contrato_funcional_completo_f1.md



Biblioteca
/
Suite Ultra
/
suite_ultra_track_alertas_inteligentes_contrato_funcional_completo_f1.md


# Suite Ultra — Contrato Funcional Completo F1

## Alertas Inteligentes Track / Cumplimiento de Metas

**Módulo:** Centro de Alertas Track  
**Proyecto:** Suite Ultra / Track BI  
**Estado del documento:** contrato funcional consolidado  
**Etapa:** cierre funcional previo a contrato técnico  
**Implementación:** no iniciada  
**Base documental:** contrato provisional F1 + validaciones F0/F1.2/F1.3/F1.4  
**Fecha base de validación:** 2026-07-09  
**Fuente principal esperada:** Track Daily Mart + Warehouse/Snapshots canónicos  

---

# 0. Reglas de negocio maestras

> Esta sección debe mantenerse arriba del documento porque el módulo pasará por varias revisiones.  
> Cualquier cambio futuro debe respetar estas reglas o documentar explícitamente por qué se modifica el contrato.

## 0.1 FAYCGO / bono es el resultado ejecutivo final

La alerta debe evaluar el cumplimiento contra metas ejecutivas del mes.

```text
FAYCGO / Bono = resultado ejecutivo final
```

La causa dominante más común será:

```text
PROYECCION_CIERRE
```

porque la pregunta ejecutiva principal es:

```text
¿La sucursal, región o empresa va a cerrar el mes contra meta?
```

---

## 0.2 Ocupación y ARPU son drivers críticos

El módulo no debe decir solamente “vas abajo en dinero”.

Debe separar:

```text
Resultado afectado → driver principal → driver secundario
```

Ejemplo validado:

```text
causa_dominante_nacional = PROYECCION_CIERRE
driver_operativo_nacional = OCUPACION
driver_secundario_nacional = ARPU_SECUNDARIO
```

Interpretación:

```text
Vamos abajo principalmente porque faltan usuarios,
y adicionalmente el ARPU nacional está presionado.
```

---

## 0.3 Palancas de soporte

Las métricas de soporte explican qué puede mover la operación.

```text
Venta nueva
Reactivaciones
Bajas
Crecimiento neto
Domiciliados
Tienda
Clientes nuevos
Agregadoras
Ingreso base
Ingreso agregadora
Ritmo vs histórico
Ritmo vs región
```

Estas métricas no reemplazan a FAYCGO, ocupación o ARPU.  
Sirven para explicar la causa operativa y orientar la acción.

---

## 0.4 La ocupación mensual se mide contra meta mensual, no contra 2.0 usuarios/m²

El objetivo estratégico de 2.0 usuarios/m² se conserva como norte de largo plazo, pero no debe disparar alertas mensuales de bono.

Regla validada:

```text
meta_usuarios_cierre_mes = proyeccion_usuarios_cierre_mes
ocupacion_actual = usuarios_activos_actual / m2_sin_circulaciones
meta_ocupacion_mes = proyeccion_usuarios_cierre_mes / m2_sin_circulaciones
pct_alcance_ocupacion = usuarios_activos_actual / proyeccion_usuarios_cierre_mes
brecha_usuarios = usuarios_activos_actual - proyeccion_usuarios_cierre_mes
```

La métrica accionable para gerente/regional es:

```text
usuarios faltantes contra meta mensual
```

---

## 0.5 El avance esperado no debe ser lineal por defecto

No se debe usar una regla plana como:

```text
día 15 = 50%
```

El avance real debe compararse contra el avance histórico esperado para:

```text
sucursal + día de corte + calendario + comportamiento histórico
```

La curva puede ser:

```text
curva propia de sucursal
curva regional
curva nacional
fallback lineal controlado
```

Regla:

```text
Si la curva propia de una sucursal contradice la curva nacional, gana la curva propia.
```

---

## 0.6 La curva de sucursales nuevas inicia con operación pública real

La curva no debe iniciar desde la primera venta registrada.

Para sucursales nuevas, el periodo de aprendizaje inicia cuando exista evidencia de operación pública real, validada por venta retail física reconstruida desde Venta Total.

Regla validada para retail físico mensual:

```text
retail_total >= 3000
retail_rows >= 5
retail_families >= 2
```

Confianza de curva:

```text
36+ meses de operación pública real → robusta
12 a 35 meses → fuerte
6 a 11 meses → media
3 a 5 meses → híbrida
1 a 2 meses → baja
0 meses → fallback
en apertura → no alertable
```

---

## 0.7 LA_VIGA se excluye de alertas futuras

`LA_VIGA` debe tratarse como proyecto cancelado.

```text
LA_VIGA → EXCLUIR_CANCELADA
```

No debe ser solo ocultamiento visual.  
Debe conservarse historia, pero quedar fuera del universo alertable futuro.

---

## 0.8 SERRANIA no debe alertarse mientras siga en apertura

`SERRANIA` debe mostrarse como no alertable mientras no tenga operación pública/metas suficientes.

```text
SERRANIA → EN_APERTURA_NO_ALERTABLE
```

No debe generar alertas de bajo desempeño operativo hasta cumplir condiciones de alertabilidad.

---

## 0.9 Base y agregadoras deben separarse

La evaluación debe distinguir:

```text
ingreso_base_mtd
ingreso_agregadoras_mtd
ingreso_total_mtd
```

Regla:

```text
ingreso_total = ingreso_base + ingreso_agregadoras
```

Una sucursal puede parecer sana por ingreso total, pero estar débil en ingreso base o depender demasiado de agregadoras.

---

## 0.10 El backend es la fuente real de permisos

El frontend solo oculta o guía UI.

Regla obligatoria:

```text
Gerente → solo sucursales asignadas
Regional → solo región/sucursales asignadas
Admin/Dirección → vista nacional
```

Los permisos críticos deben validarse en backend.

---

## 0.11 Visual-first

El módulo no debe ser una tabla como vista principal.

Regla UX:

```text
Gerente entiende su estado en menos de 10 segundos.
Regional identifica prioridades en menos de 3 minutos.
Dirección ve una lectura nacional en una sola pantalla.
```

Las tablas pueden existir como drill-down, no como experiencia principal.

---

## 0.12 Trazabilidad obligatoria

Toda alerta debe poder responder:

```text
cuándo se generó
a quién correspondía
quién la vio
quién la atendió
qué comentario dejó
por qué canal se notificó
si venció o se cerró
```

---

## 0.13 Anti-spam

Reglas F1:

```text
Máximo una alerta activa por sucursal + tipo + mes.
Si el problema continúa, se actualiza la alerta existente.
Si la severidad sube, se registra escalamiento.
Si la severidad baja, se registra mejora.
Si se resuelve, se cierra o queda como resuelta.
Regional recibe resumen agrupado, no 30 alertas individuales.
Gerente solo ve alertas accionables de su sucursal.
WhatsApp automático no entra en F1.
```

---

# 1. Objetivo del módulo

El módulo de **Alertas Inteligentes Track** debe funcionar como un sistema de alerta temprana para anticipar desviaciones de cumplimiento antes del cierre mensual.

No debe ser solo un dashboard informativo.

Debe ayudar a responder:

```text
¿La sucursal va en buen ritmo, atención, riesgo o crítico?
¿La sucursal va encaminada a cumplir FAYCGO?
¿La sucursal va encaminada a alcanzar bono?
¿Qué métrica está provocando la desviación?
¿El problema viene de ocupación, ARPU o ambos?
¿Qué palanca debe mover el gerente?
¿Qué sucursal debe atender primero el regional?
¿Qué alerta fue vista, ignorada o atendida?
```

La lógica ejecutiva del módulo será:

```text
FAYCGO / Bono = resultado ejecutivo final
Ocupación + ARPU = drivers críticos
Venta nueva + reactivaciones + bajas + domiciliados + tienda + agregadoras = palancas de soporte
```

El módulo no debe decir solamente:

```text
“La sucursal va mal.”
```

Debe decir algo accionable:

```text
“La sucursal está en riesgo de no cumplir FAYCGO porque su ocupación proyectada y ARPU están debajo del ritmo esperado. La brecha principal viene de baja venta nueva, pocas reactivaciones y bajas elevadas. Acción sugerida: intervenir esta semana en recuperación de usuarios y domiciliados.”
```

---

# 2. Estado del proyecto

```text
Etapa actual: contrato funcional consolidado
Estado: no implementación
Uso de queries: exploración, validación y definición de reglas
```

Las queries de investigación no deben convertirse directamente en código productivo ni en tablas definitivas sin cerrar:

```text
contrato técnico
migraciones Alembic
servicios backend
endpoints
permisos
payloads JSON
UI
pruebas de contrato
estrategia de performance
```

---

# 3. Principio rector de producto

El módulo debe ser:

```text
visual, explicable, accionable y trazable
```

## 3.1 Visual

No debe depender de tablas pesadas.

La vista principal debe usar:

```text
tarjetas
gráficas
semáforos
comparaciones
rankings visuales
barras de avance
lectura ejecutiva corta
acciones sugeridas
```

## 3.2 Explicable

Cada alerta debe decir:

```text
contra qué meta compara
contra qué ritmo esperado compara
qué curva histórica usó
qué fórmula usó
qué fecha de corte tomó
si incluye agregadoras
si compara contra sucursal, región o nacional
qué datos entran y qué datos quedan fuera
```

## 3.3 Accionable

Cada alerta debe terminar en una acción clara:

```text
revisar venta nueva
recuperar bajas
impulsar reactivaciones
revisar domiciliados
revisar tienda
cuidar dependencia de agregadoras
priorizar ciertas sucursales
intervenir con ciertos gerentes
```

## 3.4 Trazable

Debe quedar registro de:

```text
cuándo se generó
a quién le corresponde
quién la vio
quién la atendió
qué comentario dejó
por qué canal se notificó
si venció o se cerró
```

---

# 4. Audiencias y niveles de lectura

El sistema debe tener lecturas diferentes para:

```text
Gerente de sucursal
Regional
Administración / Dirección
```

## 4.1 Lectura gerente

```text
Mi sucursal → mi estado → mi brecha → mi causa → mi acción
```

## 4.2 Lectura regional

```text
Mi región → ranking de riesgo → causa dominante → prioridad de intervención → seguimiento de gerentes
```

## 4.3 Lectura dirección

```text
Nacional → brecha total → driver principal → driver secundario → regiones prioritarias → acción ejecutiva
```

---

# 5. Niveles F1 validados

## 5.1 F1.2 — Sucursal

Una fila por sucursal.

Debe responder:

```text
¿Esta sucursal está sana, en atención, riesgo o crítico?
¿Cuál es su alerta principal?
¿Qué drivers explican la alerta?
¿Cuánto dinero se proyecta perder contra meta?
¿Cuántos usuarios faltan contra meta de ocupación mensual?
¿Qué acción debe tomar gerente/regional?
```

## 5.2 F1.3 — Región

Una fila por región.

Debe responder:

```text
¿Cuántas sucursales críticas tiene la región?
¿Cuál es la brecha total de FAYCGO?
¿Cuántos usuarios faltan en la región?
¿Cuál es la causa dominante regional?
¿Cuál es el driver operativo regional?
¿Qué sucursales son prioritarias?
¿Qué acción debe tomar el regional?
```

## 5.3 F1.4 — Nacional

Una fila nacional.

Debe responder:

```text
¿Cuál es la brecha nacional contra meta?
¿Cuántas sucursales están críticas?
¿Cuántos usuarios faltan nacionalmente?
¿Cuál es la causa dominante nacional?
¿Cuál es el driver principal?
¿Cuál es el driver secundario?
¿Qué regiones deben atacarse primero?
¿Qué debe hacer dirección?
```

---

# 6. Fuente oficial de cálculo

La fuente principal para evaluar alertas será:

```text
track_daily_mart
```

Con versión válida seleccionada desde:

```text
track_daily_versions
```

## 6.1 Regla de versión

```text
Día actual / preview:
preview_operativo + manual_preview + success + is_current = true

Día cerrado:
cierre_canonico + official_closed_day + success + is_current = true

Evitar usar base_nocturna_canonica como cierre ejecutivo si ya existe cierre_canonico.
```

## 6.2 Consideración importante

No se debe filtrar únicamente por `is_current = true` sin distinguir `version_type`, porque puede existir una versión current para:

```text
preview_operativo
base_nocturna_canonica
cierre_canonico
```

La selección debe ser explícita según el contexto de lectura.

---

# 7. Reglas de alertabilidad

Una sucursal es alertable solo si cumple:

```text
is_track_active = true
operational_status = ACTIVA
meta_faycgo_mes > 0
m2_sin_circulaciones > 0
proyeccion_usuarios_cierre_mes > 0
```

## 7.1 Casos bloqueados

```text
LA_VIGA → EXCLUIR_CANCELADA
SERRANIA → EN_APERTURA_NO_ALERTABLE
sin meta FAYCGO → SIN_META_FAYCGO
sin m² → SIN_M2
sin meta usuarios cierre → SIN_META_USUARIOS_CIERRE
sin región → SIN_REGION
```

## 7.2 Estados bloqueados

Si una sucursal no es alertable:

```text
severity_final = blocked
alerta_principal = CONFIGURACION / NO ALERTABLE
```

---

# 8. Jerarquía de métricas

## 8.1 Nivel 1 — Resultado ejecutivo final

Estas métricas responden si se cumple o no el objetivo principal.

| Métrica | Función |
|---|---|
| Cumplimiento FAYCGO | Meta ejecutiva mensual |
| Avance hacia bono | Meta de incentivo |
| Ingreso proyectado cierre | Estimación de cierre |
| Brecha proyectada | Diferencia contra meta |
| Estado ejecutivo | Buen ritmo, Atención, Riesgo, Crítico |

## 8.2 Nivel 2 — Métricas críticas

### Ocupación

La ocupación mide densidad de usuarios respecto al espacio disponible.

Debe ayudar a explicar:

```text
venta nueva insuficiente
reactivaciones bajas
bajas elevadas
crecimiento neto débil
falta de base de usuarios para sostener FAYCGO
riesgo estructural del club
```

### ARPU

Definición funcional propuesta para F1:

```text
ARPU = ingreso_real_total_mtd / usuarios_activos_promedio_mtd
```

Si no se tiene usuarios activos promedio confiable, debe etiquetarse como:

```text
ARPU estimado
```

En la validación F1 se utilizó aproximación con usuarios actuales cuando no existía promedio MTD confiable.

El ARPU mide calidad de ingreso por usuario.

Debe ayudar a explicar:

```text
usuarios con baja monetización
promociones agresivas
baja calidad de ingreso
ticket bajo
baja aportación de domiciliados
dependencia de agregadoras
ingreso total aparentemente sano pero base débil
```

## 8.3 Nivel 3 — Métricas de soporte

| Métrica | Explica principalmente |
|---|---|
| Venta nueva | Captación y crecimiento de base |
| Reactivaciones | Recuperación de usuarios |
| Bajas | Pérdida de usuarios |
| Crecimiento neto | Balance real de usuarios |
| Domiciliados | Estabilidad de ingreso |
| Tienda | Ingreso adicional |
| Clientes nuevos | Captación comercial |
| Agregadoras | Ingreso complementario |
| Ingreso base | Salud real del ingreso |
| Ingreso agregadora | Dependencia externa |
| Ritmo vs histórico | Calidad del avance |
| Ritmo vs región | Comparativo operativo |

---

# 9. Capa previa obligatoria: ritmo esperado inteligente

Antes de generar alertas, el sistema debe calcular una proyección histórica o ritmo esperado inteligente.

No se debe usar avance lineal por defecto.

## 9.1 Problema

Una regla plana como:

```text
día 15 = deberías llevar 50%
```

puede ser injusta porque:

```text
no todos los días venden igual
hay días de alto flujo
lunes y martes podrían concentrar más venta
algunas sucursales no abren domingo
algunos días del mes pesan más
clubes viejos tienen histórico desde 2023
clubes nuevos tienen poco histórico
agregadoras pueden comportarse distinto al ingreso base
```

## 9.2 Regla actualizada

```text
El avance real debe compararse contra el avance histórico esperado para esa sucursal, ese día de corte y ese calendario.
```

Ejemplo correcto:

```text
La sucursal lleva 42% al día 15.
Según su curva histórica propia debería llevar 53%.
Brecha real: -11 pts.
Estado: Riesgo.
```

Ejemplo incorrecto:

```text
La sucursal lleva 42% al día 15.
Como es mitad de mes debería llevar 50%.
```

---

# 10. Curvas de ritmo esperado

## 10.1 Curva por sucursal

Debe ser la curva principal para clubes viejos.

Aplica cuando hay historial suficiente.

| Historial | Uso |
|---|---|
| 36+ meses confiables | Curva propia robusta |
| 12–35 meses confiables | Curva propia fuerte |
| 6–11 meses confiables | Curva media con respaldo regional/nacional |
| 3–5 meses confiables | Mezcla propia parcial + regional |
| 1–2 meses confiables | Regional/nacional |
| 0 meses confiables | Nacional o lineal controlada |

## 10.2 Curva regional

Fallback para sucursales nuevas o con datos incompletos.

```text
curva_regional = comportamiento promedio de sucursales comparables de la misma región
```

## 10.3 Curva nacional

Sirve para validar patrones generales y como fallback.

Debe usarse para probar hipótesis como:

```text
¿Lunes y martes son realmente los días más fuertes a nivel nacional?
```

No debe asumirse sin datos.

## 10.4 Curva lineal

Debe ser último recurso.

```text
curva_lineal = día_actual / días_del_mes
```

Solo aplica si no hay datos suficientes propios, regionales o nacionales confiables.

---

# 11. Hipótesis de lunes y martes

Debe validarse con datos antes de convertirse en regla.

## 11.1 Análisis requerido

Agrupar venta diaria por:

```text
día de semana
sucursal
región
nacional
clubes viejos
clubes nuevos
ingreso base
ingreso agregadoras
ingreso total
mes
calendario con domingos abiertos/cerrados
```

## 11.2 Preguntas a responder

```text
¿Lunes y martes son realmente los picos nacionales?
¿Aplica igual en todas las regiones?
¿Aplica igual en todas las sucursales?
¿Aplica para ingreso base o solo para ingreso total?
¿Las agregadoras tienen otro patrón?
¿Qué pasa con sucursales que no abren domingo?
¿Ese patrón sirve para sucursales nuevas?
```

## 11.3 Regla

```text
Si la curva propia de una sucursal contradice la curva nacional, gana la curva propia.
```

---

# 12. Domingos y días no operativos

El sistema no debe castigar a una sucursal por un día en el que no opera o históricamente no vende.

Regla funcional:

```text
Si una sucursal no abre domingo o históricamente tiene venta domingo cercana a cero, el domingo debe tener peso bajo o cero en su curva esperada.
```

La curva esperada debe redistribuir el peso sobre los días realmente productivos.

---

# 13. Separación ingreso base vs agregadoras

La evaluación debe distinguir:

```text
ingreso_base_mtd
ingreso_agregadoras_mtd
ingreso_total_mtd
```

Regla:

```text
ingreso_total = ingreso_base + ingreso_agregadoras
```

## 13.1 Por qué importa

Una sucursal puede parecer sana por ingreso total, pero estar débil en ingreso base.

Debe poder generarse una alerta como:

```text
El cumplimiento total parece aceptable, pero depende demasiado de agregadoras. El ingreso base está debajo del ritmo histórico.
```

---

# 14. Tipos iniciales de alerta F1

## 14.1 Alerta de cumplimiento FAYCGO

Se genera cuando la sucursal va debajo del ritmo esperado para cumplir FAYCGO.

Regla conceptual:

```text
cumplimiento_mtd = ingreso_real_total_mtd / meta_faycgo_mes
brecha_ritmo = cumplimiento_mtd - ritmo_esperado_al_corte
```

## 14.2 Alerta de proyección de cierre

Se genera cuando la proyección de cierre está debajo de la meta mensual.

Regla conceptual:

```text
proyeccion_cierre = ingreso_real_total_mtd / expected_pace
brecha_proyectada = proyeccion_cierre - meta_faycgo_mes
brecha_proyectada_pct = proyeccion_cierre / meta_faycgo_mes - 1
```

## 14.3 Alerta de ocupación en riesgo

Se genera cuando la ocupación mensual está debajo de la meta mensual de usuarios al cierre.

Regla validada:

```text
pct_alcance_ocupacion = usuarios_activos_actual / proyeccion_usuarios_cierre_mes
brecha_usuarios = usuarios_activos_actual - proyeccion_usuarios_cierre_mes
```

## 14.4 Alerta de ARPU bajo

Se genera cuando el ingreso por usuario está debajo del esperado.

Regla conceptual:

```text
arpu_mtd = ingreso_real_total_mtd / usuarios_activos_promedio_mtd
brecha_arpu = arpu_mtd - arpu_objetivo
```

Regla validada en F1 con proyección:

```text
arpu_projected = projected_close / usuarios_activos_actual
brecha_arpu_pct = arpu_projected / meta_arpu_mes - 1
```

## 14.5 Alerta de dependencia de agregadoras

Se genera cuando el cumplimiento total se ve aceptable o parcial, pero depende demasiado de agregadoras.

Regla conceptual:

```text
participacion_agregadoras = ingreso_real_agregadora_mtd / ingreso_real_total_mtd
```

## 14.6 Alerta regional de sucursales críticas

Se genera cuando una región tiene sucursales en Riesgo o Crítico.

Regla conceptual:

```text
ranking = sucursales_de_region ordenadas por severidad + brecha + impacto
```

---

# 15. Severidades

## 15.1 Estados operativos

| Estado | Significado |
|---|---|
| Buen ritmo / sin_alerta | La sucursal va alineada o arriba del ritmo esperado |
| Atención | Hay desviación menor que debe vigilarse |
| Riesgo | La desviación puede comprometer FAYCGO/bono |
| Crítico | Requiere intervención inmediata |
| Blocked | No alertable por configuración, apertura o exclusión |

## 15.2 Equivalente técnico

| Operación | Técnico |
|---|---|
| Buen ritmo | INFO |
| Atención | WARNING |
| Riesgo | ERROR |
| Crítico | CRITICAL |

## 15.3 Proyección de cierre

```text
>= -1%       → sin_alerta
-1% a -5%   → atencion
-5% a -15%  → riesgo
< -15%      → critico
```

## 15.4 Ritmo FAYCGO

```text
avance_real - avance_esperado >= -1%      → sin_alerta
avance_real - avance_esperado >= -3%      → atencion
avance_real - avance_esperado >= -7%      → riesgo
avance_real - avance_esperado < -7%       → critico
```

## 15.5 Ocupación por sucursal

```text
Si usuarios_actuales >= meta_usuarios_cierre:
    sin_alerta

Si pct_alcance < 90% o brecha_usuarios <= -150:
    critico

Si pct_alcance < 97% o brecha_usuarios <= -50:
    riesgo

Si no:
    atencion
```

## 15.6 ARPU

```text
>= -1%       → sin_alerta
-1% a -3%   → atencion
-3% a -7%   → riesgo
< -7%       → critico
```

## 15.7 Agregadoras

```text
< 15%        → sin_alerta
15% a 25%   → atencion
25% a 35%   → riesgo
>= 35%      → critico
```

---

# 16. Severidad final y alerta principal por sucursal

La severidad final debe priorizar las alertas que afecten el resultado ejecutivo.

Orden de prioridad:

```text
1. PROYECCION_CIERRE
2. FAYCGO_RITMO
3. OCUPACION
4. ARPU
5. DEPENDENCIA_AGREGADORAS
```

Si una sucursal está bloqueada o no alertable:

```text
severity_final = blocked
alerta_principal = CONFIGURACION / NO ALERTABLE
```

---

# 17. Driver regional

El driver regional no debe calcularse solo por conteo de sucursales.  
Debe calcularse con métricas agregadas regionales.

Regla propuesta:

```text
OCUPACION:
ocupación regional < 90%
o brecha usuarios región <= -500

ARPU:
brecha ARPU región <= -7%

DEPENDENCIA_AGREGADORAS:
share agregadoras región >= 25%

OCUPACION_SECUNDARIA:
ocupación región < 97%
o brecha usuarios región <= -150

ARPU_SECUNDARIO:
brecha ARPU región <= -3%

AGREGADORAS_SECUNDARIA:
share agregadoras región >= 15%
```

Hallazgo validado:

```text
La causa dominante regional casi siempre puede ser PROYECCION_CIERRE,
pero el driver operativo debe explicar si la presión viene principalmente de ocupación, ARPU o agregadoras.
```

---

# 18. Driver nacional

Misma lógica regional, pero con umbrales nacionales.

Regla propuesta:

```text
OCUPACION:
ocupación nacional < 90%
o brecha usuarios nacional <= -1500

ARPU:
brecha ARPU nacional <= -7%

DEPENDENCIA_AGREGADORAS:
share agregadoras nacional >= 25%

OCUPACION_SECUNDARIA:
ocupación nacional < 97%
o brecha usuarios nacional <= -500

ARPU_SECUNDARIO:
brecha ARPU nacional <= -3%

AGREGADORAS_SECUNDARIA:
share agregadoras nacional >= 15%
```

Validación F1.4B del 2026-07-09:

```text
causa_dominante_nacional = PROYECCION_CIERRE
driver_operativo_nacional = OCUPACION
driver_secundario_nacional = ARPU_SECUNDARIO
```

Resumen de validación:

```text
Sucursales alertables: 25
Críticas: 20
Riesgo: 4
Atención: 1
Bloqueadas: 1

Meta FAYCGO nacional: $26,801,186.45
Proyección cierre nacional: $20,685,833.83
Brecha nacional: -$6,115,352.62
Brecha nacional %: -22.82%

Usuarios actuales: 33,866
Meta usuarios cierre: 37,613
Brecha usuarios: -3,747
Alcance ocupación nacional: 90.04%

ARPU proyectado nacional: $610.81
Meta ARPU ponderada: $648.65
Brecha ARPU: -5.83%
```

---

# 19. Estados de alerta

Estados funcionales iniciales:

| Estado | Descripción |
|---|---|
| Generada | El sistema creó la alerta |
| Enviada | Se notificó por algún canal |
| Vista | El usuario la abrió o marcó como vista |
| Atendida | El responsable indicó acción tomada |
| Cerrada | La alerta se resolvió o se cerró |
| Vencida | Pasó el tiempo permitido sin atención |

---

# 20. Canales de notificación

## 20.1 Suite

Canal principal.

Debe existir un centro/panel de alertas visible al abrir Suite.

Debe mostrar:

```text
alertas pendientes
alertas críticas
estado de sucursal/región
fecha de corte
métricas afectadas
acción sugerida
botón para ver detalle
botón para marcar vista
botón para marcar atendida
comentario opcional
copiar mensaje WhatsApp
```

## 20.2 Correo

Debe servir para formalizar y dejar evidencia.

En F1 puede ser resumen, no necesariamente envío complejo.

Debe incluir:

```text
resumen ejecutivo
sucursales afectadas
métrica afectada
brecha
criterio usado
acción sugerida
link a Suite
```

## 20.3 WhatsApp

En F1 no será automático.

Debe contemplar:

```text
plantilla lista para copiar/pegar
botón “copiar mensaje para WhatsApp”
mensaje claro para gerente/regional
registro opcional de que el mensaje fue copiado
```

Automatización WhatsApp queda para futuro.

---

# 21. Diseño visual de pantallas

## 21.1 Centro de Alertas Track

Vista inicial del módulo.

Debe ser visible, clara y priorizada.

### Para gerente

Debe mostrar:

```text
estado de su sucursal
alertas activas
alerta más importante
avance real vs esperado
driver principal
acción sugerida
```

Ejemplo:

```text
Sucursal: Independencia
Estado: Riesgo

FAYCGO:
42% real vs 50% esperado
Brecha: -8 pts

Foco:
Ocupación baja + ARPU bajo

Acción:
Revisar venta nueva, reactivaciones, bajas y domiciliados.
```

### Para regional

Debe mostrar:

```text
total de sucursales críticas
total en riesgo
total en atención
total en buen ritmo
ranking visual de prioridad
causa dominante regional
alertas no vistas/no atendidas
```

### Para dirección

Debe mostrar:

```text
brecha nacional
sucursales críticas
usuarios faltantes nacionales
driver principal
driver secundario
regiones prioritarias
acción ejecutiva sugerida
```

---

## 21.2 Vista Gerente

Debe contener:

```text
tarjeta principal de estado
gráfica de avance real vs esperado
proyección de cierre vs meta
indicador de ocupación
indicador de ARPU
palancas de soporte
acción sugerida
trazabilidad de la alerta
```

## 21.3 Vista Regional

Debe contener:

```text
resumen visual regional
ranking de sucursales críticas
comparativo visual de brechas
top causas regionales
estado de atención de gerentes
acciones sugeridas por prioridad
```

## 21.4 Vista Nacional

Debe contener:

```text
resumen nacional ejecutivo
brecha nacional FAYCGO
usuarios faltantes nacionales
driver principal
driver secundario
regiones prioritarias
acción nacional sugerida
```

## 21.5 Detalle de alerta

Debe contener:

```text
explicación completa
regla usada
fórmula
curva histórica usada
fecha de corte
fuente de datos
valores actuales
valores esperados
brecha
gráfico asociado
comentarios
eventos de trazabilidad
```

---

# 22. Gráficas recomendadas para F1

## 22.1 Avance real vs avance esperado

Gráfica principal.

Debe mostrar:

```text
línea real MTD
línea esperada histórica
brecha actual
fecha de corte
```

## 22.2 Proyección de cierre

Debe mostrar:

```text
cierre proyectado
meta FAYCGO
gap proyectado
```

## 22.3 Ocupación

Debe mostrar:

```text
usuarios actuales
meta usuarios cierre
brecha usuarios
ocupación actual
meta ocupación mensual
estado
```

## 22.4 ARPU

Debe mostrar:

```text
ARPU actual/proyectado
ARPU esperado/meta
tendencia
brecha
```

## 22.5 Ranking regional

Debe mostrar sucursales ordenadas por:

```text
severidad
brecha
impacto en región
usuarios faltantes
```

## 22.6 Breakdown de causa

Debe mostrar visualmente si la desviación viene más de:

```text
ocupación
ARPU
venta nueva
reactivaciones
bajas
tienda
domiciliados
agregadoras
```

---

# 23. Salida esperada por nivel

## 23.1 Sucursal

Campos mínimos:

```text
track_date
version_id
version_type
generation_mode
sucursal_canon
track_label
region_key
region_label
alertability_status
severity_final
alerta_principal
curve_confidence
meta_faycgo_mes
proyeccion_cierre_faycgo
brecha_proyectada_monto
brecha_proyectada_pct
usuarios_activos_actual
meta_usuarios_cierre_mes
brecha_usuarios_ocupacion
pct_alcance_meta_ocupacion
arpu_proyectado
meta_arpu_mes
brecha_arpu_pct
agregadoras_share_pct
drivers_detectados
accion_sugerida
```

## 23.2 Región

Campos mínimos:

```text
track_date
version_id
version_type
generation_mode
region_key
region_label
sucursales_alertables
sucursales_criticas
sucursales_riesgo
sucursales_atencion
sucursales_sin_alerta
sucursales_bloqueadas
meta_faycgo_region
proyeccion_cierre_region
brecha_proyectada_region_monto
brecha_proyectada_region_pct
usuarios_actuales_region
meta_usuarios_cierre_region
brecha_usuarios_region
pct_alcance_ocupacion_region
ingreso_base_mtd_region
ingreso_agregadora_mtd_region
ingreso_total_mtd_region
agregadoras_share_region_pct
arpu_proyectado_region
meta_arpu_region_ponderada
brecha_arpu_region_pct
causa_dominante_region
driver_operativo_region
sucursales_prioritarias
accion_regional_sugerida
```

## 23.3 Nacional

Campos mínimos:

```text
track_date
version_id
version_type
generation_mode
sucursales_alertables
sucursales_criticas
sucursales_riesgo
sucursales_atencion
sucursales_sin_alerta
sucursales_bloqueadas
meta_faycgo_nacional
proyeccion_cierre_nacional
brecha_proyectada_nacional_monto
brecha_proyectada_nacional_pct
usuarios_actuales_nacional
meta_usuarios_cierre_nacional
brecha_usuarios_nacional
pct_alcance_ocupacion_nacional
ingreso_base_mtd_nacional
ingreso_agregadora_mtd_nacional
ingreso_total_mtd_nacional
agregadoras_share_nacional_pct
arpu_proyectado_nacional
meta_arpu_nacional_ponderada
brecha_arpu_nacional_pct
causa_dominante_nacional
driver_operativo_nacional
driver_secundario_nacional
regiones_prioritarias
accion_nacional_sugerida
```

---

# 24. Ejemplos de lectura ejecutiva

## 24.1 Nacional

```text
La operación nacional proyecta cerrar 22.82% debajo de la meta FAYCGO,
con una brecha estimada de -$6.1M.

El principal driver operativo es ocupación:
faltan 3,747 usuarios contra la meta nacional de cierre.

El driver secundario es ARPU:
ARPU proyectado $610.81 vs meta ponderada $648.65,
brecha de -5.83%.

Las regiones prioritarias son:
Tijuana/Rosarito/Ensenada,
CDMX/Ixtapaluca/Tlalnepantla
y Monterrey/Saltillo/Chihuahua.
```

## 24.2 Regional

```text
La región tiene brecha proyectada contra FAYCGO,
con sucursales críticas y usuarios faltantes.
La causa dominante es PROYECCION_CIERRE.
El driver operativo puede ser OCUPACION, ARPU o secundario,
según las métricas agregadas de la región.
```

## 24.3 Sucursal

```text
La sucursal está crítica por proyección de cierre.
La brecha se explica por ritmo FAYCGO, usuarios faltantes,
ARPU presionado o dependencia de agregadoras.
La acción sugerida debe ser concreta para gerente/regional.
```

---

# 25. Acciones sugeridas

## 25.1 Sucursal

Ejemplos:

```text
Plan de recuperación inmediato:
revisar venta nueva, reactivaciones, bajas y seguimiento diario con regional.

Priorizar recuperación de usuarios:
venta nueva, reactivaciones y control de bajas.
Enfocar meta en usuarios faltantes.

Revisar mezcla de ingresos:
descuentos, domiciliados y ticket promedio.

Revisar dependencia de agregadoras y reforzar ingreso base.
```

## 25.2 Región

Ejemplos:

```text
Intervención regional inmediata:
la región trae brecha fuerte de cierre y ocupación crítica.
Priorizar recuperación de usuarios.

Intervención regional inmediata:
la región trae brecha fuerte de cierre y presión de ARPU.
Revisar mezcla de ingresos, descuentos, domiciliados y ticket promedio.

Seguimiento preventivo regional:
varias sucursales están en riesgo recuperable.
```

## 25.3 Nacional

Ejemplos:

```text
Intervención nacional inmediata:
la proyección de cierre está muy por debajo de meta
y la ocupación nacional está presionada.
Priorizar recuperación de usuarios por región.

Intervención nacional inmediata:
la proyección de cierre está muy por debajo de meta
y hay presión fuerte de ARPU.
Revisar descuentos, mezcla de ingresos, domiciliados y ticket promedio.

Seguimiento ejecutivo diario:
hay múltiples sucursales críticas aunque la brecha nacional todavía podría ser recuperable.
```

---

# 26. Reglas anti-spam

El módulo no debe generar ruido.

Reglas F1:

```text
1. Máximo una alerta activa por sucursal y tipo de problema.
2. Si el problema continúa, se actualiza la alerta existente.
3. Si la severidad sube, se registra escalamiento.
4. Si la severidad baja, se registra mejora.
5. Si se resuelve, se cierra o queda como resuelta.
6. El regional recibe resumen agrupado, no 30 alertas individuales.
7. El gerente solo ve alertas accionables de su sucursal.
8. No todo debe mandar correo.
9. WhatsApp automático no entra en F1.
10. Toda alerta debe tener responsable claro.
```

---

# 27. Modelo conceptual de datos

Pendiente de cerrar en contrato técnico.

Conceptualmente se necesitan estas entidades.

---

## 27.1 Alerta

Representa una alerta activa o histórica.

| Campo | Descripción |
|---|---|
| id | Identificador |
| alert_type | Tipo de alerta |
| audience_type | gerente, regional, admin |
| severity | INFO, WARNING, ERROR, CRITICAL |
| status | generada, enviada, vista, atendida, cerrada, vencida |
| track_date | Fecha de corte |
| month | Mes evaluado |
| branch_id | Sucursal |
| region_id | Región |
| responsible_user_id | Responsable |
| metric_primary | Métrica principal |
| metric_support | Métricas secundarias |
| executive_goal | FAYCGO, bono, ocupación, ARPU |
| current_value | Valor actual |
| expected_value | Valor esperado |
| gap_value | Brecha absoluta |
| gap_pct | Brecha porcentual |
| curve_type | sucursal, regional, nacional, lineal |
| rule_key | Regla usada |
| explanation | Lectura ejecutiva |
| suggested_action | Acción sugerida |
| payload_json | Datos completos para auditoría |
| created_at | Creación |
| viewed_at | Vista |
| attended_at | Atención |
| closed_at | Cierre |

---

## 27.2 Evento de alerta

Representa trazabilidad.

| Campo | Descripción |
|---|---|
| id | Identificador |
| alert_id | Alerta relacionada |
| event_type | generated, sent, viewed, attended, commented, escalated, closed |
| user_id | Usuario |
| channel | suite, email, whatsapp_manual |
| comment | Comentario opcional |
| created_at | Fecha del evento |

---

## 27.3 Curva histórica esperada

Representa el ritmo esperado por sucursal/región/nacional.

| Campo | Descripción |
|---|---|
| id | Identificador |
| curve_scope | branch, region, national |
| branch_id | Si aplica |
| region_id | Si aplica |
| metric_key | ingreso_base, ingreso_agregadora, ingreso_total |
| day_of_month | Día del mes |
| weekday | Día de semana |
| expected_daily_weight | Peso diario esperado |
| expected_cumulative_weight | Peso acumulado esperado |
| sample_months | Meses usados |
| confidence | alta, media, baja |
| includes_sundays | Si considera domingos |
| generated_at | Fecha de cálculo |

---

# 28. Endpoints conceptuales propuestos

Pendiente de confirmar nombres después del contrato técnico.

## 28.1 Alertas

```text
GET /api/track/alerts/summary
GET /api/track/alerts
GET /api/track/alerts/<id>
POST /api/track/alerts/<id>/view
POST /api/track/alerts/<id>/attend
POST /api/track/alerts/<id>/comment
POST /api/track/alerts/<id>/close
```

## 28.2 Regional

```text
GET /api/track/alerts/regional-summary
GET /api/track/alerts/regional-ranking
GET /api/track/alerts/unattended
```

## 28.3 Curvas / ritmo esperado

```text
GET /api/track/alerts/expected-pace
GET /api/track/alerts/expected-pace/branch/<branch_id>
GET /api/track/alerts/expected-pace/regional/<region_id>
```

## 28.4 Generación manual / debug controlado

```text
POST /api/track/alerts/run-preview
POST /api/track/alerts/generate-for-date
```

Estos endpoints de generación deben quedar restringidos a admin/sistemas.

---

# 29. Permisos

El backend debe ser la fuente real de permisos.

## 29.1 Gerente

Puede ver:

```text
alertas de su sucursal
estado de su sucursal
detalle de sus alertas
marcar vista
marcar atendida
comentar
```

No debe ver sucursales no asignadas.

## 29.2 Regional

Puede ver:

```text
alertas de sus sucursales
resumen regional
ranking regional
estado de atención de gerentes
detalle de alertas de su región
```

## 29.3 Admin / Dirección

Puede ver:

```text
todo nacional
todas las regiones
todas las sucursales
estados de atención
reglas usadas
auditoría
```

---

# 30. Decisiones de performance para investigación

Durante la investigación, la query pesada puede tardar varios minutos porque recalcula:

```text
venta_total_snapshots
venta_total_snapshot_rows
retail histórico
curva histórica
branch_curve
region_curve
national_curve
```

Para acelerar pruebas se validó usar una tabla temporal:

```text
tmp_track_alert_executive_ranking
```

Flujo de investigación:

```text
1. Correr query pesada una sola vez.
2. Materializar tmp_track_alert_executive_ranking.
3. Ejecutar F1.3 regional, F1.4 nacional y cambios de textos/umbrales desde la temp table.
```

Esta decisión es solo para investigación.

En implementación productiva se deberá decidir si el cálculo será:

```text
bajo demanda
snapshot diario
job programado
tabla materializada
combinación de mart + alertas persistidas
```

---

# 31. Criterios de aceptación F1

F1 se considera aceptable si:

```text
1. Un gerente puede abrir Suite y entender el estado de su sucursal en menos de 10 segundos.
2. Un regional puede identificar sus sucursales prioritarias en menos de 3 minutos.
3. Dirección puede leer una vista nacional clara sin navegar tablas.
4. Las alertas no dependen de una tabla como vista principal.
5. Cada alerta tiene severidad visual.
6. Cada alerta muestra avance real vs avance esperado.
7. El avance esperado usa curva histórica cuando exista historial suficiente.
8. Si se usa curva lineal, debe mostrarse como fallback.
9. Cada alerta muestra fecha de corte.
10. Cada alerta muestra fórmula o regla usada.
11. Cada alerta muestra causa probable.
12. Cada alerta distingue ocupación, ARPU y métricas de soporte.
13. Cada alerta muestra acción sugerida.
14. Se separa ingreso base vs agregadoras.
15. Se puede marcar alerta como vista.
16. Se puede marcar alerta como atendida.
17. Se puede comentar una alerta.
18. Se evita duplicar alertas activas iguales.
19. El regional ve ranking visual, no solo tabla.
20. El gerente ve una lectura simplificada.
21. Backend valida permisos reales.
22. Cambios de base de datos van con Alembic.
23. No hay lógica compleja en Angular HTML.
24. Toda lógica de cálculo vive en backend/servicios.
25. El frontend consume endpoints, no calcula reglas críticas.
```

---

# 32. Riesgos y mitigaciones

## 32.1 Spam de alertas

Mitigación:

```text
agrupar
deduplicar
actualizar alertas existentes
priorizar severidad
resumen regional
```

## 32.2 Gerentes ignoran alertas

Mitigación:

```text
centro visible al abrir Suite
estados vista/atendida
trazabilidad
alertas pocas y claras
mensaje accionable
```

## 32.3 Alertas injustas

Mitigación:

```text
usar curva histórica
no usar lineal por defecto
separar sucursales viejas/nuevas
considerar domingos
mostrar fórmula
mostrar fuente
```

## 32.4 Se usa para regañar sin contexto

Mitigación:

```text
explicación operativa
acción sugerida
desglose de causa
comentario del gerente
trazabilidad transparente
```

## 32.5 Datos duplicados/no canónicos

Mitigación:

```text
usar Track Daily Mart canónico o versión declarada
guardar version_id cuando aplique
mostrar fecha de corte
no mezclar snapshots sin regla
```

## 32.6 Mezclar base y agregadoras

Mitigación:

```text
separar ingreso base
separar ingreso agregadoras
separar ingreso total
alerta específica de dependencia de agregadoras
```

## 32.7 Dashboard demasiado analítico

Mitigación:

```text
visual-first
lectura en capas
tablas solo drill-down
tarjetas y gráficas simples
```

## 32.8 Centrarse solo en ingreso

Mitigación:

```text
usar FAYCGO como resultado
ocupación y ARPU como drivers
soporte operativo como explicación
```

## 32.9 Centrarse solo en ocupación/ARPU

Mitigación:

```text
mantener tienda, domiciliados, clientes nuevos, reactivaciones, bajas y agregadoras como métricas de soporte alertables
```

## 32.10 Alertar tarde

Mitigación:

```text
curva esperada diaria
tendencia reciente
proyección de cierre
comparación histórica
```

---

# 33. Qué sí entra en MVP F1

```text
Centro de Alertas Track dentro de Suite
Vista gerente
Vista regional
Vista nacional ejecutiva
Severidades: Buen ritmo, Atención, Riesgo, Crítico
Métricas críticas: ocupación y ARPU
Métrica ejecutiva: FAYCGO / bono
Métricas soporte iniciales
Avance real vs esperado
Ritmo esperado histórico para sucursales con historial
Fallback nacional/regional/lineal
Separación base vs agregadoras
Tarjetas visuales
Gráfica real vs esperado
Ranking visual regional
Trazabilidad básica
Comentarios
Marcar vista
Marcar atendida
Plantilla WhatsApp para copiar
Correo resumen conceptual o preparado
Backend como fuente de permisos
```

---

# 34. Qué NO entra en MVP F1

```text
WhatsApp automático
Machine learning
Configurador visual de reglas
Motor de reglas editable por usuario
Predicción avanzada por eventos especiales
Feriados/promociones especiales
Alertas por 30 métricas desde el inicio
Penalizaciones automáticas
Automatizaciones sin trazabilidad
Dashboard basado principalmente en tablas
Lógica crítica en frontend
Cambios manuales en producción
Curvas históricas ultra sofisticadas por producto/familia
Integración externa avanzada de correo/WhatsApp
```

---

# 35. Plan por fases

## 35.1 Fase 0 — Inspección

Objetivo:

```text
revisar tablas reales
identificar fuente real para ingreso diario
identificar fuente real para cierre mensual
validar Track Daily Mart
validar campos de ingreso base/agregadoras
validar metas FAYCGO
validar usuarios/m2
validar sucursales/regiones
validar historial disponible
validar canonicalidad/versiones
```

Resultado:

```text
contrato técnico final con nombres reales de tablas, campos, modelos y endpoints
```

## 35.2 Fase 1 — Curva histórica / ritmo esperado

Objetivo:

```text
construir avance esperado no lineal
validar lunes/martes
validar domingos
separar viejas/nuevas
generar curva sucursal/regional/nacional
```

Resultado:

```text
expected pace confiable para alimentar alertas
```

## 35.3 Fase 2 — Motor de alertas

Objetivo:

```text
evaluar FAYCGO
evaluar ocupación
evaluar ARPU
evaluar soporte
generar alerta explicable
evitar duplicados
guardar trazabilidad
```

Resultado:

```text
alertas generadas y consultables por backend
```

## 35.4 Fase 3 — UI visual F1

Objetivo:

```text
Centro de Alertas Track
vista gerente
vista regional
vista nacional
detalle de alerta
gráficas principales
```

Resultado:

```text
módulo usable por gerente/regional/dirección sin depender de tablas
```

## 35.5 Fase 4 — Notificaciones

Objetivo:

```text
resumen correo
plantilla WhatsApp
trazabilidad de canal
registro de vista/atención
```

Resultado:

```text
alertas visibles y con evidencia de atención
```

---

# 36. Pendientes para contrato técnico

Antes de implementación hay que cerrar:

```text
1. Tabla real del Track Daily Mart.
2. Campos reales de ingreso base MTD.
3. Campos reales de ingreso agregadora MTD.
4. Campo real de ingreso total.
5. Fuente real de metas FAYCGO.
6. Fuente real de bono, si existe.
7. Fuente real de usuarios activos.
8. Fuente real de proyección de usuarios cierre.
9. Fuente real de m2 sin circulaciones.
10. Fuente real de sucursal/región.
11. Cómo identificar sucursales nuevas vs viejas.
12. Cómo identificar canonicalidad/versiones.
13. Cómo reconstruir venta diaria desde MTD.
14. Si existen cierres diarios o solo acumulados.
15. Si venta total permite histórico 2023–2026 por día.
16. Si agregadoras están diarias, MTD o por snapshot.
17. Si domingos cerrados están explícitos o se infieren por venta cero.
18. Si hay tabla de usuarios/sucursales/permisos suficiente.
19. Si conviene persistir curvas o calcular on demand.
20. Si el scheduler debe generar alertas después del mart.
21. Lifecycle productivo de alertas.
22. Dedupe productivo por mes + sucursal + tipo.
23. Payload JSON final.
24. Migraciones Alembic.
25. Servicios backend.
26. Endpoints finales.
27. Pruebas de contrato y fixtures.
28. Plan de índices/performance.
29. Política de cierre automático de alertas cuando la condición desaparece.
```

---

# 37. Frase final del contrato

El módulo de **Alertas Inteligentes Track** debe ser un centro visual de intervención operativa, no un reporte tabular.

Debe evaluar FAYCGO/bono como resultado ejecutivo, explicar desviaciones mediante ocupación y ARPU como drivers críticos, usar métricas de soporte para identificar palancas accionables, calcular ritmo esperado con curvas históricas no lineales, separar ingreso base y agregadoras, y registrar trazabilidad suficiente para evitar la excusa de “no lo vi”.

F1 debe priorizar claridad, justicia operativa y acción sobre complejidad.

