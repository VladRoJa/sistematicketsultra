# Suite Ultra — Contrato Provisional F1

## Alertas Inteligentes Track / Cumplimiento de Metas

**Estado del documento:** provisional
**Etapa:** contrato funcional antes de inspección técnica
**Siguiente paso:** inspección de estructura real de datos para cerrar contrato técnico final
**Módulo:** Centro de Alertas Track
**Fuente principal esperada:** Track Daily Mart + Warehouse/Snapshots canónicos

---

# 1. Objetivo del módulo

El módulo de **Alertas Inteligentes Track** debe funcionar como un sistema de alerta temprana para anticipar desviaciones de cumplimiento antes del cierre mensual.

No debe ser solo un dashboard informativo.

Debe ayudar a responder:

* ¿La sucursal va en buen ritmo, atención, riesgo o crítico?
* ¿La sucursal va encaminada a cumplir FAYCGO?
* ¿La sucursal va encaminada a alcanzar bono?
* ¿Qué métrica está provocando la desviación?
* ¿El problema viene de ocupación, ARPU o ambos?
* ¿Qué palanca debe mover el gerente?
* ¿Qué sucursal debe atender primero el regional?
* ¿Qué alerta fue vista, ignorada o atendida?

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

Debe decir:

```text
“La sucursal está en riesgo de no cumplir FAYCGO porque su ocupación proyectada y ARPU están debajo del ritmo esperado. La brecha principal viene de baja venta nueva, pocas reactivaciones y bajas elevadas. Acción sugerida: intervenir esta semana en recuperación de usuarios y domiciliados.”
```

---

# 2. Principio rector de producto

El módulo debe ser:

```text
visual, explicable, accionable y trazable
```

## Visual

No debe depender de tablas pesadas.

La vista principal debe usar:

* tarjetas,
* gráficas,
* semáforos,
* comparaciones,
* rankings visuales,
* barras de avance,
* lectura ejecutiva corta,
* acciones sugeridas.

## Explicable

Cada alerta debe decir:

* contra qué meta compara,
* contra qué ritmo esperado compara,
* qué curva histórica usó,
* qué fórmula usó,
* qué fecha de corte tomó,
* si incluye agregadoras,
* si compara contra sucursal, región o nacional,
* qué datos entran y qué datos quedan fuera.

## Accionable

Cada alerta debe terminar en una acción clara:

* revisar venta nueva,
* recuperar bajas,
* impulsar reactivaciones,
* revisar domiciliados,
* revisar tienda,
* cuidar dependencia de agregadoras,
* priorizar ciertas sucursales,
* intervenir con ciertos gerentes.

## Trazable

Debe quedar registro de:

* cuándo se generó,
* a quién le corresponde,
* quién la vio,
* quién la atendió,
* qué comentario dejó,
* por qué canal se notificó,
* si venció o se cerró.

---

# 3. Principio visual obligatorio

El módulo debe ser **visual-first**.

La experiencia principal no debe ser una tabla de números.

Las tablas pueden existir como apoyo o detalle, pero no como vista principal.

## Regla UX

```text
El usuario debe entender el estado principal en menos de 10 segundos.
El usuario debe entender la situación operativa en menos de 3 minutos.
```

## Implicación

Para gerente:

```text
Mi sucursal → mi estado → mi brecha → mi causa → mi acción
```

Para regional:

```text
Mi región → ranking de riesgo → causa dominante → prioridad de intervención → seguimiento de gerentes
```

---

# 4. Separación por audiencia

El sistema debe tener lecturas diferentes para:

1. Gerente de sucursal.
2. Regional.
3. Administración / dirección, como vista futura o extendida.

---

# 5. Alertas para gerente

## Objetivo

El gerente debe saber rápidamente:

* cómo va su sucursal,
* qué está fallando,
* qué tan lejos está de meta,
* qué debe cuidar hoy,
* qué debe cuidar esta semana,
* qué palanca debe mover para acercarse a FAYCGO/bono.

## Tipo de lectura

Simple, directa, visual y accionable.

## Estructura mínima de una alerta de gerente

| Campo              | Descripción                                                           |
| ------------------ | --------------------------------------------------------------------- |
| Sucursal           | Sucursal del gerente                                                  |
| Estado             | Buen ritmo, Atención, Riesgo o Crítico                                |
| Fecha de corte     | Día Track usado                                                       |
| Objetivo afectado  | FAYCGO, bono, ocupación, ARPU u otro                                  |
| Avance real        | Cumplimiento actual                                                   |
| Avance esperado    | Ritmo esperado inteligente                                            |
| Brecha             | Diferencia entre real y esperado                                      |
| Driver principal   | Ocupación, ARPU o ambos                                               |
| Métricas soporte   | Venta nueva, reactivaciones, bajas, domiciliados, tienda, agregadoras |
| Lectura            | Explicación corta                                                     |
| Acción sugerida    | Qué debe hacer                                                        |
| Estado de atención | Generada, vista, atendida, cerrada, vencida                           |

## Ejemplo conceptual

```text
Sucursal: Independencia
Estado: Riesgo
Fecha de corte: día 15

FAYCGO:
42% real vs 50% esperado
Brecha: -8 pts

Foco principal:
Ocupación baja + ARPU bajo

Lectura:
La sucursal no está generando suficiente base de usuarios ni suficiente ingreso por usuario para llegar a FAYCGO.

Acción sugerida:
Revisar venta nueva, reactivaciones, bajas y domiciliados esta semana.
```

---

# 6. Alertas para regional

## Objetivo

El regional debe saber:

* qué sucursales están críticas,
* qué sucursales están en riesgo,
* cuál tiene mayor brecha,
* dónde intervenir primero,
* qué gerente no ha visto/atendido alertas,
* qué métrica explica la caída regional,
* si el problema es regional o puntual.

## Tipo de lectura

Comparativa, priorizada y orientada a intervención.

## Estructura mínima de una alerta regional

| Campo                                | Descripción                               |
| ------------------------------------ | ----------------------------------------- |
| Región                               | Región evaluada                           |
| Estado regional                      | Buen ritmo, Atención, Riesgo o Crítico    |
| Fecha de corte                       | Día Track usado                           |
| Sucursales críticas                  | Ranking visual                            |
| Sucursales en riesgo                 | Ranking secundario                        |
| Brecha regional                      | Diferencia acumulada vs esperado          |
| Driver dominante                     | Ocupación, ARPU, bajas, venta nueva, etc. |
| Sucursales que explican mayor brecha | Top impacto                               |
| Gerentes pendientes                  | No vistas / no atendidas                  |
| Acción sugerida                      | Intervención recomendada                  |

## Ejemplo conceptual

```text
Región Norte
Estado: Crítico
Fecha de corte: día 15

Sucursales prioritarias:
1. Chihuahua — -12 pts vs ritmo esperado
2. Saltillo Villalta — -9 pts
3. Sendero Saltillo — -7 pts

Causa dominante:
Ocupación insuficiente + ARPU bajo

Lectura:
La región no está fallando solo en ingreso; la brecha viene de poca generación/retención de usuarios y menor ingreso promedio por usuario.

Acción sugerida:
Priorizar intervención con Chihuahua y Saltillo Villalta.
```

---

# 7. Jerarquía de métricas

## Nivel 1 — Resultado ejecutivo final

Estas métricas responden si se cumple o no el objetivo principal.

| Métrica                   | Función                               |
| ------------------------- | ------------------------------------- |
| Cumplimiento FAYCGO       | Meta ejecutiva mensual                |
| Avance hacia bono         | Meta de incentivo                     |
| Ingreso proyectado cierre | Estimación de cierre                  |
| Brecha proyectada         | Diferencia contra meta                |
| Estado ejecutivo          | Buen ritmo, Atención, Riesgo, Crítico |

---

## Nivel 2 — Métricas críticas

Estas explican estructuralmente el cumplimiento.

## 2.1 Ocupación

Definición formal:

```text
ocupación = proyección_usuarios_cierre_mes / m2_sin_circulaciones
```

La ocupación mide densidad de usuarios respecto al espacio disponible.

Debe ayudar a explicar:

* venta nueva insuficiente,
* reactivaciones bajas,
* bajas elevadas,
* crecimiento neto débil,
* falta de base de usuarios para sostener FAYCGO,
* riesgo estructural del club.

## 2.2 ARPU

Definición funcional propuesta para F1:

```text
ARPU = ingreso_real_total_mtd / usuarios_activos_promedio_mtd
```

Si no se tiene usuarios activos promedio confiable, debe etiquetarse como:

```text
ARPU estimado
```

El ARPU mide calidad de ingreso por usuario.

Debe ayudar a explicar:

* usuarios con baja monetización,
* promociones agresivas,
* baja calidad de ingreso,
* ticket bajo,
* baja aportación de domiciliados,
* dependencia de agregadoras,
* ingreso total aparentemente sano pero base débil.

---

## Nivel 3 — Métricas de soporte

Estas explican las causas operativas.

| Métrica            | Explica principalmente          |
| ------------------ | ------------------------------- |
| Venta nueva        | Captación y crecimiento de base |
| Reactivaciones     | Recuperación de usuarios        |
| Bajas              | Pérdida de usuarios             |
| Crecimiento neto   | Balance real de usuarios        |
| Domiciliados       | Estabilidad de ingreso          |
| Tienda             | Ingreso adicional               |
| Clientes nuevos    | Captación comercial             |
| Agregadoras        | Ingreso complementario          |
| Ingreso base       | Salud real del ingreso          |
| Ingreso agregadora | Dependencia externa             |
| Ritmo vs histórico | Calidad del avance              |
| Ritmo vs región    | Comparativo operativo           |

---

# 8. Capa previa obligatoria: ritmo esperado inteligente

Antes de generar alertas, el sistema debe calcular una proyección histórica o ritmo esperado inteligente.

No se debe usar avance lineal por defecto.

## Problema

Una regla plana como:

```text
día 15 = deberías llevar 50%
```

puede ser injusta porque:

* no todos los días venden igual,
* hay días de alto flujo,
* lunes y martes podrían concentrar más venta,
* algunas sucursales no abren domingo,
* algunos días del mes pesan más,
* los clubes viejos tienen histórico desde 2023,
* los clubes nuevos tienen poco histórico,
* las agregadoras pueden comportarse distinto al ingreso base.

## Regla actualizada

```text
El avance real debe compararse contra el avance histórico esperado para esa sucursal, ese día de corte y ese calendario.
```

Ejemplo:

```text
La sucursal lleva 42% al día 15.
Según su curva histórica propia debería llevar 53%.
Brecha real: -11 pts.
Estado: Riesgo.
```

No:

```text
La sucursal lleva 42% al día 15.
Como es mitad de mes debería llevar 50%.
```

---

# 9. Curvas de ritmo esperado

## 9.1 Curva por sucursal

Debe ser la curva principal para clubes viejos.

Aplica cuando hay historial suficiente.

Criterio funcional preliminar:

| Historial             | Uso                                |
| --------------------- | ---------------------------------- |
| 12+ meses confiables  | Curva propia principal             |
| 6–11 meses confiables | Curva propia con respaldo regional |
| 3–5 meses confiables  | Mezcla propia parcial + regional   |
| 1–2 meses confiables  | Regional/nacional                  |
| 0 meses confiables    | Nacional o lineal controlada       |

Para los 21 gyms viejos, la expectativa es usar curva propia porque hay historial desde 2023.

---

## 9.2 Curva regional

Fallback para sucursales nuevas o con datos incompletos.

```text
curva_regional = comportamiento promedio de sucursales comparables de la misma región
```

---

## 9.3 Curva nacional

Sirve para validar patrones generales y como fallback.

Debe usarse para probar hipótesis como:

```text
¿Lunes y martes son realmente los días más fuertes a nivel nacional?
```

No debe asumirse sin datos.

---

## 9.4 Curva lineal

Debe ser último recurso.

```text
curva_lineal = día_actual / días_del_mes
```

Solo aplica si no hay datos suficientes propios, regionales o nacionales confiables.

---

# 10. Hipótesis de lunes y martes

Debe validarse con datos antes de convertirse en regla.

## Análisis requerido

Agrupar venta diaria por:

* día de semana,
* sucursal,
* región,
* nacional,
* clubes viejos,
* clubes nuevos,
* ingreso base,
* ingreso agregadoras,
* ingreso total,
* mes,
* calendario con domingos abiertos/cerrados.

## Preguntas a responder

* ¿Lunes y martes son realmente los picos nacionales?
* ¿Aplica igual en todas las regiones?
* ¿Aplica igual en todas las sucursales?
* ¿Aplica para ingreso base o solo para ingreso total?
* ¿Las agregadoras tienen otro patrón?
* ¿Qué pasa con sucursales que no abren domingo?
* ¿Ese patrón sirve para sucursales nuevas?

## Regla

```text
Si la curva propia de una sucursal contradice la curva nacional, gana la curva propia.
```

---

# 11. Domingos y días no operativos

El sistema no debe castigar a una sucursal por un día en el que no opera o históricamente no vende.

## Regla funcional

```text
Si una sucursal no abre domingo o históricamente tiene venta domingo cercana a cero, el domingo debe tener peso bajo o cero en su curva esperada.
```

La curva esperada debe redistribuir el peso sobre los días realmente productivos.

---

# 12. Separación ingreso base vs agregadoras

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

## Por qué importa

Una sucursal puede parecer sana por ingreso total, pero estar débil en ingreso base.

Debe poder generarse una alerta como:

```text
El cumplimiento total parece aceptable, pero depende demasiado de agregadoras. El ingreso base está debajo del ritmo histórico.
```

---

# 13. Tipos iniciales de alerta F1

## 13.1 Alerta de cumplimiento FAYCGO

Se genera cuando la sucursal va debajo del ritmo esperado para cumplir FAYCGO.

Regla conceptual:

```text
cumplimiento_mtd = ingreso_real_total_mtd / meta_faycgo_mes
brecha_ritmo = cumplimiento_mtd - ritmo_esperado_al_corte
```

---

## 13.2 Alerta de ocupación en riesgo

Se genera cuando la ocupación proyectada de cierre está debajo del objetivo.

Regla conceptual:

```text
ocupacion_proyectada = proyeccion_usuarios_cierre_mes / m2_sin_circulaciones
brecha_ocupacion = ocupacion_proyectada - ocupacion_objetivo
```

---

## 13.3 Alerta de ARPU bajo

Se genera cuando el ingreso por usuario está debajo del esperado.

Regla conceptual:

```text
arpu_mtd = ingreso_real_total_mtd / usuarios_activos_promedio_mtd
brecha_arpu = arpu_mtd - arpu_objetivo
```

---

## 13.4 Alerta de dependencia de agregadoras

Se genera cuando el cumplimiento total se ve aceptable, pero depende demasiado de agregadoras.

Regla conceptual:

```text
participacion_agregadoras = ingreso_real_agregadora_mtd / ingreso_real_total_mtd
```

---

## 13.5 Alerta regional de sucursales críticas

Se genera cuando una región tiene sucursales en Riesgo o Crítico.

Regla conceptual:

```text
ranking = sucursales_de_region ordenadas por severidad + brecha + impacto
```

---

# 14. Severidades

## Estados operativos

| Estado     | Significado                                         |
| ---------- | --------------------------------------------------- |
| Buen ritmo | La sucursal va alineada o arriba del ritmo esperado |
| Atención   | Hay desviación menor que debe vigilarse             |
| Riesgo     | La desviación puede comprometer FAYCGO/bono         |
| Crítico    | Requiere intervención inmediata                     |

## Equivalente técnico

| Operación  | Técnico  |
| ---------- | -------- |
| Buen ritmo | INFO     |
| Atención   | WARNING  |
| Riesgo     | ERROR    |
| Crítico    | CRITICAL |

---

# 15. Estados de alerta

Estados funcionales iniciales:

| Estado   | Descripción                            |
| -------- | -------------------------------------- |
| Generada | El sistema creó la alerta              |
| Enviada  | Se notificó por algún canal            |
| Vista    | El usuario la abrió o marcó como vista |
| Atendida | El responsable indicó acción tomada    |
| Cerrada  | La alerta se resolvió o se cerró       |
| Vencida  | Pasó el tiempo permitido sin atención  |

---

# 16. Canales de notificación

## 16.1 Suite

Canal principal.

Debe existir un centro/panel de alertas visible al abrir Suite.

Debe mostrar:

* alertas pendientes,
* alertas críticas,
* estado de sucursal/región,
* fecha de corte,
* métricas afectadas,
* acción sugerida,
* botón para ver detalle,
* botón para marcar vista,
* botón para marcar atendida,
* comentario opcional,
* copiar mensaje WhatsApp.

---

## 16.2 Correo

Debe servir para formalizar y dejar evidencia.

En F1 puede ser resumen, no necesariamente envío complejo.

Debe incluir:

* resumen ejecutivo,
* sucursales afectadas,
* métrica afectada,
* brecha,
* criterio usado,
* acción sugerida,
* link a Suite.

---

## 16.3 WhatsApp

En F1 no será automático.

Debe contemplar:

* plantilla lista para copiar/pegar,
* botón “copiar mensaje para WhatsApp”,
* mensaje claro para gerente/regional,
* registro opcional de que el mensaje fue copiado.

Automatización WhatsApp queda para futuro.

---

# 17. Diseño visual de pantallas

## 17.1 Centro de Alertas Track

Vista inicial del módulo.

Debe ser visible, clara y priorizada.

### Para gerente

Debe mostrar:

* estado de su sucursal,
* alertas activas,
* alerta más importante,
* avance real vs esperado,
* driver principal,
* acción sugerida.

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

* total de sucursales críticas,
* total en riesgo,
* total en atención,
* total en buen ritmo,
* ranking visual de prioridad,
* causa dominante regional,
* alertas no vistas/no atendidas.

---

## 17.2 Vista Gerente

Debe contener:

1. Tarjeta principal de estado.
2. Gráfica de avance real vs esperado.
3. Proyección de cierre vs meta.
4. Indicador de ocupación.
5. Indicador de ARPU.
6. Palancas de soporte.
7. Acción sugerida.
8. Trazabilidad de la alerta.

---

## 17.3 Vista Regional

Debe contener:

1. Resumen visual regional.
2. Ranking de sucursales críticas.
3. Comparativo visual de brechas.
4. Top causas regionales.
5. Estado de atención de gerentes.
6. Acciones sugeridas por prioridad.

---

## 17.4 Detalle de alerta

Debe contener:

* explicación completa,
* regla usada,
* fórmula,
* curva histórica usada,
* fecha de corte,
* fuente de datos,
* valores actuales,
* valores esperados,
* brecha,
* gráfico asociado,
* comentarios,
* eventos de trazabilidad.

---

# 18. Gráficas recomendadas para F1

## 18.1 Avance real vs avance esperado

Gráfica principal.

Debe mostrar:

* línea real MTD,
* línea esperada histórica,
* brecha actual,
* fecha de corte.

## 18.2 Proyección de cierre

Debe mostrar:

* cierre proyectado,
* meta FAYCGO,
* gap proyectado.

## 18.3 Ocupación

Debe mostrar:

* ocupación actual/proyectada,
* objetivo,
* estado,
* brecha.

## 18.4 ARPU

Debe mostrar:

* ARPU actual,
* ARPU esperado,
* tendencia,
* brecha.

## 18.5 Ranking regional

Debe mostrar sucursales ordenadas por:

* severidad,
* brecha,
* impacto en región.

## 18.6 Breakdown de causa

Debe mostrar visualmente si la desviación viene más de:

* ocupación,
* ARPU,
* venta nueva,
* reactivaciones,
* bajas,
* tienda,
* domiciliados,
* agregadoras.

---

# 19. Reglas anti-spam

El módulo no debe generar ruido.

Reglas F1:

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

---

# 20. Modelo conceptual de datos

Pendiente de cerrar hasta inspección real.

Pero conceptualmente se necesitan estas entidades.

---

## 20.1 Alerta

Representa una alerta activa o histórica.

Campos conceptuales:

| Campo               | Descripción                                          |
| ------------------- | ---------------------------------------------------- |
| id                  | Identificador                                        |
| alert_type          | Tipo de alerta                                       |
| audience_type       | gerente, regional, admin                             |
| severity            | INFO, WARNING, ERROR, CRITICAL                       |
| status              | generada, enviada, vista, atendida, cerrada, vencida |
| track_date          | Fecha de corte                                       |
| month               | Mes evaluado                                         |
| branch_id           | Sucursal                                             |
| region_id           | Región                                               |
| responsible_user_id | Responsable                                          |
| metric_primary      | Métrica principal                                    |
| metric_support      | Métricas secundarias                                 |
| executive_goal      | FAYCGO, bono, ocupación, ARPU                        |
| current_value       | Valor actual                                         |
| expected_value      | Valor esperado                                       |
| gap_value           | Brecha absoluta                                      |
| gap_pct             | Brecha porcentual                                    |
| curve_type          | sucursal, regional, nacional, lineal                 |
| rule_key            | Regla usada                                          |
| explanation         | Lectura ejecutiva                                    |
| suggested_action    | Acción sugerida                                      |
| payload_json        | Datos completos para auditoría                       |
| created_at          | Creación                                             |
| viewed_at           | Vista                                                |
| attended_at         | Atención                                             |
| closed_at           | Cierre                                               |

---

## 20.2 Evento de alerta

Representa trazabilidad.

| Campo      | Descripción                                                     |
| ---------- | --------------------------------------------------------------- |
| id         | Identificador                                                   |
| alert_id   | Alerta relacionada                                              |
| event_type | generated, sent, viewed, attended, commented, escalated, closed |
| user_id    | Usuario                                                         |
| channel    | suite, email, whatsapp_manual                                   |
| comment    | Comentario opcional                                             |
| created_at | Fecha del evento                                                |

---

## 20.3 Curva histórica esperada

Representa el ritmo esperado por sucursal/región/nacional.

Campos conceptuales:

| Campo                      | Descripción                                     |
| -------------------------- | ----------------------------------------------- |
| id                         | Identificador                                   |
| curve_scope                | branch, region, national                        |
| branch_id                  | Si aplica                                       |
| region_id                  | Si aplica                                       |
| metric_key                 | ingreso_base, ingreso_agregadora, ingreso_total |
| day_of_month               | Día del mes                                     |
| weekday                    | Día de semana                                   |
| expected_daily_weight      | Peso diario esperado                            |
| expected_cumulative_weight | Peso acumulado esperado                         |
| sample_months              | Meses usados                                    |
| confidence                 | alta, media, baja                               |
| includes_sundays           | Si considera domingos                           |
| generated_at               | Fecha de cálculo                                |

---

# 21. Endpoints conceptuales propuestos

Pendiente de confirmar nombres después de inspección.

## Alertas

```text
GET /api/track/alerts/summary
GET /api/track/alerts
GET /api/track/alerts/<id>
POST /api/track/alerts/<id>/view
POST /api/track/alerts/<id>/attend
POST /api/track/alerts/<id>/comment
POST /api/track/alerts/<id>/close
```

## Regional

```text
GET /api/track/alerts/regional-summary
GET /api/track/alerts/regional-ranking
GET /api/track/alerts/unattended
```

## Curvas / ritmo esperado

```text
GET /api/track/alerts/expected-pace
GET /api/track/alerts/expected-pace/branch/<branch_id>
GET /api/track/alerts/expected-pace/regional/<region_id>
```

## Generación manual / debug controlado

```text
POST /api/track/alerts/run-preview
POST /api/track/alerts/generate-for-date
```

Estos endpoints de generación deben quedar restringidos a admin/sistemas.

---

# 22. Permisos

El backend debe ser la fuente real de permisos.

## Gerente

Puede ver:

* alertas de su sucursal,
* estado de su sucursal,
* detalle de sus alertas,
* marcar vista,
* marcar atendida,
* comentar.

No debe ver sucursales no asignadas.

## Regional

Puede ver:

* alertas de sus sucursales,
* resumen regional,
* ranking regional,
* estado de atención de gerentes,
* detalle de alertas de su región.

## Admin / Dirección

Puede ver:

* todo nacional,
* todas las regiones,
* todas las sucursales,
* estados de atención,
* reglas usadas,
* auditoría.

---

# 23. Criterios de aceptación F1

F1 se considera aceptable si:

1. Un gerente puede abrir Suite y entender el estado de su sucursal en menos de 10 segundos.
2. Un regional puede identificar sus sucursales prioritarias en menos de 3 minutos.
3. Las alertas no dependen de una tabla como vista principal.
4. Cada alerta tiene severidad visual.
5. Cada alerta muestra avance real vs avance esperado.
6. El avance esperado usa curva histórica cuando exista historial suficiente.
7. Si se usa curva lineal, debe mostrarse como fallback.
8. Cada alerta muestra fecha de corte.
9. Cada alerta muestra fórmula o regla usada.
10. Cada alerta muestra causa probable.
11. Cada alerta distingue ocupación, ARPU y métricas de soporte.
12. Cada alerta muestra acción sugerida.
13. Se separa ingreso base vs agregadoras.
14. Se puede marcar alerta como vista.
15. Se puede marcar alerta como atendida.
16. Se puede comentar una alerta.
17. Se evita duplicar alertas activas iguales.
18. El regional ve ranking visual, no solo tabla.
19. El gerente ve una lectura simplificada.
20. Backend valida permisos reales.
21. Cambios de base de datos van con Alembic.
22. No hay lógica compleja en Angular HTML.
23. Toda lógica de cálculo vive en backend/servicios.
24. El frontend consume endpoints, no calcula reglas críticas.

---

# 24. Riesgos y mitigaciones

## Riesgo 1 — Spam de alertas

Mitigación:

* agrupar,
* deduplicar,
* actualizar alertas existentes,
* priorizar severidad,
* resumen regional.

## Riesgo 2 — Gerentes ignoran alertas

Mitigación:

* centro visible al abrir Suite,
* estados vista/atendida,
* trazabilidad,
* alertas pocas y claras,
* mensaje accionable.

## Riesgo 3 — Alertas injustas

Mitigación:

* usar curva histórica,
* no usar lineal por defecto,
* separar sucursales viejas/nuevas,
* considerar domingos,
* mostrar fórmula,
* mostrar fuente.

## Riesgo 4 — Se usa para regañar sin contexto

Mitigación:

* explicación operativa,
* acción sugerida,
* desglose de causa,
* comentario del gerente,
* trazabilidad transparente.

## Riesgo 5 — Datos duplicados/no canónicos

Mitigación:

* usar Track Daily Mart canónico o versión declarada,
* guardar version_id cuando aplique,
* mostrar fecha de corte,
* no mezclar snapshots sin regla.

## Riesgo 6 — Mezclar base y agregadoras

Mitigación:

* separar ingreso base,
* ingreso agregadoras,
* ingreso total,
* alerta específica de dependencia de agregadoras.

## Riesgo 7 — Dashboard demasiado analítico

Mitigación:

* visual-first,
* lectura en capas,
* tablas solo drill-down,
* tarjetas y gráficas simples.

## Riesgo 8 — Centrarse solo en ingreso

Mitigación:

* usar FAYCGO como resultado,
* ocupación y ARPU como drivers,
* soporte operativo como explicación.

## Riesgo 9 — Centrarse solo en ocupación/ARPU

Mitigación:

* mantener tienda, domiciliados, clientes nuevos, reactivaciones, bajas y agregadoras como métricas de soporte alertables.

## Riesgo 10 — Alertar tarde

Mitigación:

* curva esperada diaria,
* tendencia reciente,
* proyección de cierre,
* comparación histórica.

---

# 25. Qué sí entra en MVP F1

* Centro de Alertas Track dentro de Suite.
* Vista gerente.
* Vista regional.
* Severidades: Buen ritmo, Atención, Riesgo, Crítico.
* Métricas críticas: ocupación y ARPU.
* Métrica ejecutiva: FAYCGO / bono.
* Métricas soporte iniciales.
* Avance real vs esperado.
* Ritmo esperado histórico para sucursales con historial.
* Fallback nacional/regional/lineal.
* Separación base vs agregadoras.
* Tarjetas visuales.
* Gráfica real vs esperado.
* Ranking visual regional.
* Trazabilidad básica.
* Comentarios.
* Marcar vista.
* Marcar atendida.
* Plantilla WhatsApp para copiar.
* Correo resumen conceptual o preparado.
* Backend como fuente de permisos.

---

# 26. Qué NO entra en MVP F1

* WhatsApp automático.
* Machine learning.
* Configurador visual de reglas.
* Motor de reglas editable por usuario.
* Predicción avanzada por eventos especiales.
* Feriados/promociones especiales.
* Alertas por 30 métricas desde el inicio.
* Penalizaciones automáticas.
* Automatizaciones sin trazabilidad.
* Dashboard basado principalmente en tablas.
* Lógica crítica en frontend.
* Cambios manuales en producción.
* Curvas históricas ultra sofisticadas por producto/familia.
* Integración externa avanzada de correo/WhatsApp.

---

# 27. Plan por fases

## Fase 0 — Inspección

Objetivo:

* revisar tablas reales,
* identificar fuente real para ingreso diario,
* identificar fuente real para cierre mensual,
* validar Track Daily Mart,
* validar campos de ingreso base/agregadoras,
* validar metas FAYCGO,
* validar usuarios/m2,
* validar sucursales/regiones,
* validar historial disponible,
* validar canonicalidad/versiones.

Resultado:

```text
contrato técnico final con nombres reales de tablas, campos, modelos y endpoints
```

---

## Fase 1 — Curva histórica / ritmo esperado

Objetivo:

* construir avance esperado no lineal,
* validar lunes/martes,
* validar domingos,
* separar viejas/nuevas,
* generar curva sucursal/regional/nacional.

Resultado:

```text
expected pace confiable para alimentar alertas
```

---

## Fase 2 — Motor de alertas

Objetivo:

* evaluar FAYCGO,
* evaluar ocupación,
* evaluar ARPU,
* evaluar soporte,
* generar alerta explicable,
* evitar duplicados,
* guardar trazabilidad.

Resultado:

```text
alertas generadas y consultables por backend
```

---

## Fase 3 — UI visual F1

Objetivo:

* Centro de Alertas Track,
* vista gerente,
* vista regional,
* detalle de alerta,
* gráficas principales.

Resultado:

```text
módulo usable por gerente/regional sin depender de tablas
```

---

## Fase 4 — Notificaciones

Objetivo:

* resumen correo,
* plantilla WhatsApp,
* trazabilidad de canal,
* registro de vista/atención.

Resultado:

```text
alertas visibles y con evidencia de atención
```

---

# 28. Pendientes para inspección

Antes del contrato final hay que inspeccionar:

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

---

# 29. Frase final del contrato provisional

El módulo de Alertas Inteligentes Track debe ser un centro visual de intervención operativa, no un reporte tabular.

Debe evaluar FAYCGO/bono como resultado ejecutivo, explicar desviaciones mediante ocupación y ARPU como drivers críticos, usar métricas de soporte para identificar palancas accionables, calcular ritmo esperado con curvas históricas no lineales, separar ingreso base y agregadoras, y registrar trazabilidad suficiente para evitar la excusa de “no lo vi”.

F1 debe priorizar claridad, justicia operativa y acción sobre complejidad.
