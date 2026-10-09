# Contrato — Checklist Diario de Sistemas V1 / M3
## Historial, BI y Salud Operativa

Estado: BLOQUEADO POR M2  
Gate de entrada: M2 ACCEPTED en main.  
Gate de salida: V1 ACCEPTED de extremo a extremo con BI operativo.

## 0. Uso de este contrato

Este archivo es autosuficiente para una conversación nueva.

La conversación debe implementar **únicamente M3**.

Antes de tocar código:

1. inspeccionar main;
2. confirmar M2 ACCEPTED;
3. validar datos persistidos reales del checklist;
4. revisar patrones BI/Track/Warehouse que puedan reutilizarse sin acoplar dominios;
5. revisar permisos de lectura global/regional/sucursal;
6. explicar un cambio y una prueba a la vez.

Está fuera de alcance:

- creación automática de Ticket V2;
- diagnóstico técnico;
- SLA/resolución de Tickets V2.

## 1. Objetivo

Convertir el histórico del checklist en una vista operacional de **Salud de Sistemas** para validar el MVP con Sistemas antes de abrirlo a gerentes.

M3 debe permitir responder, sin exportaciones manuales:

- quién cumplió hoy;
- quién está pendiente;
- qué sucursales operan normal;
- cuáles tienen fallas;
- qué sistemas están fallando;
- con qué frecuencia;
- dónde se repiten;
- si las fallas se reportan a Soporte;
- cómo evoluciona la situación;
- cómo se comporta el aplazamiento del checklist.

## 2. Principio BI

> Todo indicador debe poder rastrearse hasta los registros fuente.

Fuente:

```text
daily check
→ answers
→ issues
→ attachments
→ prompt/postpone state
```

No crear contadores irreconciliables como única fuente de verdad.

## 3. Historial

Debe existir una vista de historial con filtros mínimos:

- rango de fechas;
- sucursal;
- estado general;
- pregunta/sistema;
- resultado YES/NO/NA.

Cada fila debe permitir abrir el detalle.

## 4. Detalle de checklist

Debe mostrar:

- sucursal;
- gerente;
- business_date;
- submitted_at;
- estado general;
- 13 respuestas;
- incidencias asociadas;
- reported_to_support;
- descripción;
- evidencia;
- contexto de aplazamiento si aplica.

No mostrar diagnóstico inexistente como si fuera dato real.

## 5. Dashboard Salud Operativa

V1 debe incluir una vista principal que muestre el estado del día.

KPIs mínimos:

- sucursales esperadas;
- completados;
- pendientes;
- % cumplimiento;
- normales;
- fallas menores;
- afectación operativa.

Debe distinguir claramente pendiente de falla.

## 6. Matriz por sucursal

Debe existir una vista compacta por sucursal con semáforo.

Agrupaciones sugeridas:

- Cómputo;
- Internet;
- Gasca;
- Suite Ultra;
- Acceso;
- Audio;
- Video;
- Cámaras;
- Estado general.

La agregación exacta debe documentarse para que varias preguntas no generen semántica ambigua.

## 7. Semáforo

Semántica:

- VERDE = sin NO en el ámbito mostrado;
- AMARILLO = falla menor;
- ROJO = afectación operativa;
- GRIS = checklist pendiente;
- NA debe distinguirse de ausencia de dato cuando corresponda.

No depender únicamente del color: incluir label/icono/tooltip accesible.

## 8. Cumplimiento

Métricas mínimas:

- completados / esperados;
- pendientes;
- porcentaje;
- tendencia diaria;
- cumplimiento por sucursal;
- cumplimiento por periodo.

Durante el MVP, “esperados” **no puede significar automáticamente todas las sucursales activas**, porque GERENTE todavía no está habilitado.

M3 debe distinguir:

- universo productivo potencial;
- universo elegible del rollout vigente;
- participantes/checklists esperados del piloto.

El denominador de cumplimiento MVP se calcula únicamente sobre el universo elegible/configurado para el piloto.

M3 debe investigar la fuente canónica de sucursales activas para dejar preparado el rollout posterior, sin contaminar el KPI MVP.

## 9. Fallas

Métricas mínimas:

- total de respuestas NO;
- incidencias por question_key;
- incidencias por sucursal;
- porcentaje de checks con al menos una falla;
- ranking de preguntas/sistemas;
- ranking de sucursales;
- recurrencia.

No sumar NA como falla.

## 10. Soporte

Métricas:

- incidencias reportadas;
- no reportadas;
- % reportado;
- tendencia.

Drill-down debe mostrar las incidencias fuente.

## 11. Aplazamientos

Métricas V1 obligatorias:

- completados sin aplazar;
- completados tras 1 aplazamiento;
- completados tras 2 aplazamientos;
- casos que alcanzaron mandatory;
- distribución por sucursal;
- tendencia.

Definir claramente si “alcanzó mandatory” significa que `mandatory_from_at` ocurrió antes del submit.

## 12. Tiempo

Como mínimo ofrecer:

- día;
- semana;
- mes.

Los cortes deben respetar business_date local.

No mezclar UTC directamente en agrupaciones de negocio.

## 13. Tendencia

Visualizaciones mínimas deben permitir ver evolución de:

- cumplimiento;
- salud general;
- incidencias;
- reported_to_support;
- aplazamientos.

No llenar el dashboard de gráficas redundantes.

Priorizar lectura operativa.

## 14. Drill-down obligatorio

Ejemplos:

```text
Internet
12 fallas
 ↓
Sucursales afectadas
 ↓
Fechas
 ↓
Checklist
 ↓
Incidencia
```

```text
Pendientes hoy
2 sucursales
 ↓
Sucursal
 ↓
estado de prompt/postpone
```

Todo agregado importante debe poder explicar de dónde salió.

## 15. Filtros BI

Mínimo:

- fecha/rango;
- sucursal;
- estado;
- sistema/pregunta.

Si existe concepto regional canónico y permisos lo permiten, puede añadirse región, pero no inventar estructura paralela.

## 16. Permisos

M3 debe investigar y definir scopes reales.

### MVP

Solo:

- SISTEMAS;
- ADMICORP.

deben poder ver el módulo BI/historial, con el alcance explícitamente aprobado para el piloto.

### Fuera del MVP

GERENTE, Regional y otros perfiles permanecen sin acceso hasta aprobación de Sistemas y cambio de rollout.

La estructura puede quedar preparada para futuros scopes por sucursal/región, pero no deben habilitarse implícitamente.

Backend valida todos los filtros y scopes.

No aceptar branch_ids arbitrarios sin autorización.

## 17. APIs BI

La forma exacta se define según el repo.

Separar razonablemente:

- resumen;
- matriz;
- tendencias;
- historial;
- detalle.

Evitar endpoint monolítico gigantesco si complica performance y permisos.

## 18. Performance

Los endpoints deben responder de forma adecuada con histórico creciente.

Investigar índices necesarios, por ejemplo:

- business_date;
- branch_id;
- general_status;
- question_key/answer;
- reported_to_support.

Cambios de índice requieren Alembic.

No añadir materialized views prematuramente si consultas simples indexadas son suficientes.

## 19. No acoplar a Track

Aunque Track/BI ya exista, el Checklist es un dominio propio.

Se pueden reutilizar patrones de UI/servicios, pero no:

- escribir en track_daily_mart;
- reinterpretar métricas financieras;
- forzar este módulo dentro de Warehouse.

## 20. Exports

No son obligatorios salvo que la implementación encuentre un patrón útil y no retrase el gate.

La aceptación principal es visual/operativa dentro de Suite.

Si se agrega export, debe respetar filtros y permisos.

## 21. Empty states

Definir claramente:

- sin checks aún;
- sin fallas;
- sin datos para rango;
- sucursal pendiente hoy.

No mostrar 0 como si fuera dato completo cuando realmente falta checklist.

## 22. Cálculos

### % cumplimiento

```text
completed_expected / active_expected_branches
```

con definición precisa de denominador.

### % reported

```text
issues_reported / issues_total
```

Si issues_total = 0, mostrar N/A o semántica explícita, no división falsa.

## 23. Recurrencia

V1 debe poder identificar repetición al menos por:

- misma sucursal;
- misma question_key;
- varios días.

No intentar deducir que dos incidencias son “la misma avería técnica” sin Ticket V2.

Hablar de recurrencia de señal/falla observada, no diagnóstico.

## 24. Acceptance de datos

Crear fixtures/casos que cubran:

- sucursal normal;
- falla menor;
- afectación;
- pendiente;
- múltiples NO;
- NA;
- reportada/no reportada;
- 0/1/2 aplazamientos;
- mandatory.

Validar agregados contra conteo manual.

## 25. Pruebas backend mínimas

- permisos globales/scope;
- filtros;
- denominadores;
- aggregations;
- NA no cuenta como NO;
- pendientes no cuentan como normales;
- reported ratio;
- postponement buckets;
- timezone en día/semana/mes;
- drill-down coincide con agregado.

## 26. Pruebas frontend mínimas

- KPI cards;
- matriz;
- filtros;
- empty states;
- drill-down;
- responsive razonable;
- no horizontal scroll destructivo;
- no depender solo del color.

## 27. Acceptance integral V1

Además de M3, ejecutar smoke del flujo completo con un usuario piloto SISTEMAS/ADMICORP:

```text
login
→ postpone 1
→ wait/eligible
→ postpone 2
→ mandatory
→ responder
→ NO con incidencia
→ evidencia
→ submit
→ gate liberado
→ aparece en historial
→ aparece en BI
→ drill-down al origen
```

Puede simularse el paso del tiempo en test; no esperar 10 minutos reales.

## 28. Relación futura con Tickets V2

M3 debe dejar identificadores suficientes para un bridge posterior.

BI V1 no debe asumir que:

- issue resuelta = ticket resuelto;
- reported_to_support = ticket creado;
- misma question_key = misma causa técnica.

Métricas futuras posibles, fuera de V1:

- % incidencias que generan ticket;
- tiempo detección -> ticket;
- tiempo resolución;
- reincidencia post-resolución.

## 29. Fuera de alcance M3

- creación automática de ticket;
- workflow de atención;
- asignación a técnico;
- SLA;
- resolución;
- diagnóstico;
- correlación automática de causa raíz.

## 30. Gate de salida

M3 y V1 quedan ACCEPTED solo si:

1. historial funciona;
2. detalle reconstruye checklist;
3. dashboard muestra cumplimiento y salud;
4. pendientes se distinguen de normal;
5. matriz por sucursal funciona;
6. fallas por sistema/pregunta son correctas;
7. soporte reported/no reported es correcto;
8. aplazamientos se miden;
9. día/semana/mes respetan timezone;
10. drill-down coincide con agregados;
11. permisos backend están probados;
12. smoke integral V1 está verde;
13. BI/historial solo es visible para SISTEMAS/ADMICORP durante MVP;
14. GERENTE no aparece como usuario obligado ni contamina el denominador de cumplimiento;
15. Sistemas puede revisar el piloto sin habilitar todavía el rollout productivo a gerentes.

## 31. Estado final esperado

```text
M1 — ACCEPTED
M2 — ACCEPTED
M3 — ACCEPTED
CHECKLIST DIARIO DE SISTEMAS V1 MVP — ACCEPTED
ROLLOUT A GERENTES — PENDIENTE DE APROBACIÓN DE SISTEMAS
```
