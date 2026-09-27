# Contrato v2 — Análisis Deportivo / Salud de la base y Operación deportiva

## 1. Objetivo

La v2 convierte **Aforo y Asistencia** en una herramienta para responder tres preguntas distintas sin llenar una sola pantalla de tarjetas:

1. **Resumen:** ¿qué movimiento tuvo el gimnasio?
2. **Salud de la base:** ¿qué tanto están usando el gimnasio nuestros socios?
3. **Operación deportiva:** ¿la presencia de instructores coincide con la demanda real?

La pantalla actual de Resumen se conserva. Las nuevas métricas se reparten en vistas internas para mantener una lectura simple.

---

## 2. Navegación de la pantalla

Debajo de los filtros generales se agrega un selector compacto:

```text
[ Resumen ] [ Salud de la base ] [ Operación deportiva ]
```

No son tres módulos distintos. Todo sigue dentro de **Aforo y Asistencia**.

Regla visual:

- máximo **4 indicadores principales** en la parte superior de cada vista;
- el resto se muestra con gráficas, distribuciones y detalles;
- las listas largas se abren en modal o detalle, no se cargan completas en la pantalla principal.

La ruta principal se mantiene:

```text
/#/sports-analysis/attendance
```

La vista seleccionada puede conservarse en query string, por ejemplo:

```text
?view=summary
?view=base-health
?view=operations
```

---

## 3. Filtros generales

Se conservan los filtros actuales:

- periodo;
- región;
- sucursal;
- tipo de asistencia.

### Resumen

Todos los filtros funcionan como hoy.

### Salud de la base

Esta vista trabaja únicamente con **socios**.

El filtro de tipo de asistencia no cambia los cálculos de esta vista.

Cuando se filtra una sucursal, se analiza la **base de socios de esa sucursal**, no sólo las personas que entraron físicamente a ese club.

Una visita del socio en cualquier Ultra Gym cuenta como uso de su membresía.

### Operación deportiva

Esta vista compara internamente:

- `SOCIO`;
- `INSTRUCTOR PISO`.

Por eso el filtro de tipo de asistencia no cambia los cálculos de esta vista.

Cuando se filtra una sucursal, aquí sí importa el lugar físico donde ocurrió la entrada, porque estamos midiendo cobertura dentro del club.

---

## 4. Regla para identificar socios

Los indicadores de socios usan **`id_socio`** como identidad principal.

El PIN puede seguir existiendo como dato de apoyo, pero no debe ser la llave principal para contar socios únicos cuando ya exista `id_socio`.

Las visitas que no logren resolverse a un `id_socio`:

- siguen contando como visitas cuando corresponda;
- no se inventan como socios distintos;
- no entran en métricas que necesiten conocer exactamente qué socio es.

El backend debe devolver también el porcentaje de visitas con identidad resuelta para poder detectar problemas de calidad de datos.

Ese porcentaje es información de control y no necesita ocupar una tarjeta principal.

---

## 5. Qué significa "socio activo en el periodo"

Para Salud de la base, un socio es **elegible** si estuvo activo al menos un día dentro del periodo consultado.

No se usará simplemente la lista de socios activos al día de hoy.

Ejemplo:

- periodo consultado: 1 al 30 de septiembre;
- socio dado de alta el 25 de septiembre;
- sólo se consideran como disponibles los días en que realmente estuvo activo dentro del periodo.

Esto evita comparar a un socio que tuvo 6 días disponibles con uno que tuvo todo el mes.

---

## 6. Vista: Resumen

La vista actual se conserva como la lectura rápida de actividad.

Indicadores principales:

- Visitas;
- Socios únicos / Personas únicas;
- Aforo pico;
- Estancia mediana.

Visualizaciones actuales:

- aforo promedio por hora;
- entradas por hora;
- distribución por edad;
- tipo de asistencia;
- ranking de actividad.

### Socios únicos

Cuando el tipo de asistencia sea `SOCIO`, **Socios únicos** se calcula por `id_socio`.

Para tipos de asistencia donde todavía no exista una identidad equivalente, se puede mantener el conteo actual por PIN y usar el texto **Personas únicas**.

La vista Resumen no debe recibir los indicadores de Salud de la base ni los de Operación deportiva.

---

## 7. Vista: Salud de la base

Esta vista responde:

> ¿Qué tanto está usando el gimnasio nuestra base activa?

### 7.1 Indicadores principales

Se muestran como máximo cuatro:

1. **Utilización de la base**
2. **Socios sin visitas**
3. **Frecuencia mediana**
4. **Socios con 14+ días sin venir**

Ejemplo:

```text
UTILIZACIÓN          SIN VISITAS        FRECUENCIA MEDIANA      14+ DÍAS SIN VENIR
80.4%                6,781              1.82 por semana         3,216
27,900 de 34,681     19.6%              Promedio 2.31           Ver detalle
```

---

## 8. Utilización de la base

Fórmula:

```text
socios elegibles con al menos 1 visita
--------------------------------------
socios elegibles en el periodo
```

La visita puede haber ocurrido en cualquier Ultra Gym.

Cuando se filtra una sucursal, el denominador son los socios pertenecientes a esa sucursal y el numerador son los que usaron cualquier club durante el periodo.

El indicador debe mostrar:

- porcentaje;
- socios elegibles;
- socios con visita;
- socios sin visita.

---

## 9. Frecuencia de visita

La frecuencia se expresa como **visitas por semana disponible**.

No se divide simplemente entre las semanas del calendario si el socio sólo estuvo activo parte del periodo.

Cálculo base:

```text
visitas del socio
-----------------
días elegibles / 7
```

La pantalla debe mostrar al menos:

- promedio;
- mediana.

La distribución se presenta en grupos:

```text
0 visitas
menos de 1 por semana
1.00 a 1.99 por semana
2.00 a 2.99 por semana
3.00 o más por semana
```

La distribución es más importante que mostrar únicamente un promedio.

---

## 10. Recencia

La recencia indica cuánto tiempo ha pasado desde la última visita conocida del socio.

Se calcula contra **`date_to` del periodo consultado**, no contra la fecha actual.

Grupos:

```text
0–7 días
8–14 días
15–21 días
22+ días
Sin visita registrada
```

"Sin visita registrada" es el texto seguro mientras el histórico de asistencias no cubra toda la vida del socio.

Sólo se podrá usar "Nunca ha asistido" cuando exista evidencia suficiente desde su fecha de alta.

El detalle de una cohorte debe poder mostrar:

- nombre;
- ID socio;
- sucursal de origen;
- fecha de alta;
- última visita;
- días sin venir;
- visitas por semana.

---

## 11. Activación de socios nuevos

Esta métrica mide qué tan rápido empieza a usar el gimnasio un socio después de darse de alta.

Se consideran socios cuya fecha de alta cae dentro del periodo consultado.

La primera visita puede ocurrir en **cualquier Ultra Gym**.

Grupos:

```text
Mismo día
1–3 días
4–7 días
8+ días
Sin primera visita registrada
```

Un socio que todavía no ha cumplido 7 días desde su alta no debe clasificarse como "sin visita después de 7 días".

Mientras siga dentro de esa ventana puede mostrarse como:

```text
Aún dentro de sus primeros 7 días
```

Esto evita castigar a altas demasiado recientes.

---

## 12. Socios para seguimiento

No se usará el nombre **riesgo de baja** mientras no exista evidencia que demuestre esa relación.

La primera versión usa reglas simples y visibles.

Un socio puede entrar a seguimiento cuando:

```text
está activo
Y
(
    lleva 14 o más días sin venir
    O
    tiene menos de 1 visita por semana
)
```

La lista se abre desde un modal o detalle.

Campos iniciales:

- nombre;
- ID socio;
- sucursal;
- fecha de alta;
- última visita;
- días sin venir;
- frecuencia semanal.

No se integra todavía con Contact Center.

No se agregan todavía teléfono, tarifa, vencimiento ni campañas como requisito de esta versión.

---

## 13. Vista: Operación deportiva

Esta vista responde:

> ¿Tenemos instructores de piso cuando realmente hay socios en el club?

Sólo se usa **`INSTRUCTOR PISO`** para cobertura.

No se suman:

- instructor de clase;
- auxiliar;
- supervisor;
- recepción;
- otros tipos de personal.

---

## 14. Cálculo por intervalos de 15 minutos

La comparación se hace por presencia simultánea, no por total diario.

Ejemplo:

```text
19:00   120 socios   2 instructores   60 socios por instructor
19:15   146 socios   2 instructores   73 socios por instructor
19:30   153 socios   1 instructor    153 socios por instructor
19:45   149 socios   0 instructores  SIN COBERTURA
```

Si hay socios y no hay instructor de piso, no se divide entre cero.

Ese intervalo se clasifica como **Sin cobertura**.

---

## 15. Indicadores principales de Operación deportiva

Máximo cuatro:

1. **Socios por instructor — mediana**
2. **Máximo socios por instructor**
3. **Minutos sin cobertura**
4. **% del tiempo sin cobertura**

"Máximo socios por instructor" sólo se calcula en intervalos donde exista al menos un instructor.

Los intervalos con cero instructores se analizan aparte como falta de cobertura.

No se definen todavía límites de "bueno", "malo", "amarillo" o "rojo".

Primero se medirán datos reales y después se podrán acordar límites operativos.

---

## 16. Visualizaciones de Operación deportiva

### Socios e instructores por horario

Debe permitir ver cómo cambia la demanda y la presencia de instructores durante el día.

### Cobertura por intervalos

Debe permitir localizar rápidamente los bloques donde:

- hay socios y hay instructor;
- hay mucha demanda respecto a los instructores disponibles;
- hay socios y no hay ningún instructor de piso.

La primera versión no necesita asignar colores de riesgo si todavía no existen límites aprobados.

El detalle debe permitir abrir los intervalos concretos de 15 minutos.

---

## 17. Comportamiento por sucursal

Hay dos lecturas distintas y no deben mezclarse.

### Salud de la base

La sucursal representa **a qué base pertenece el socio**.

Si un socio de Sendero Mexicali visita Tec Mexicali, sigue contando como uso de la base de Sendero Mexicali.

### Operación deportiva

La sucursal representa **dónde ocurrió físicamente la visita**.

Si ese mismo socio entra a Tec Mexicali, esa presencia sí forma parte de la demanda operativa de Tec Mexicali.

---

## 18. API propuesta

Se conserva el endpoint actual de Resumen.

Nuevos endpoints separados:

```text
GET /api/sports-analysis/attendance/base-health
GET /api/sports-analysis/attendance/base-health/members
GET /api/sports-analysis/attendance/operations
GET /api/sports-analysis/attendance/operations/coverage-detail
```

Los filtros comunes deben seguir usando:

- date_from;
- date_to;
- region_key;
- branch_id.

El backend realiza los cálculos y aplica permisos.

El frontend sólo muestra los resultados; no debe reconstruir reglas de negocio en HTML o TypeScript.

---

## 19. Respuesta mínima de Salud de la base

El endpoint debe poder entregar, como mínimo:

- socios elegibles;
- socios con visita;
- socios sin visita;
- porcentaje de utilización;
- frecuencia promedio;
- frecuencia mediana;
- distribución de frecuencia;
- distribución de recencia;
- activación de nuevos socios;
- total de socios para seguimiento;
- cobertura de identidad.

Los nombres exactos de campos JSON pueden definirse al implementar, pero el significado de cada dato debe respetar este contrato.

---

## 20. Respuesta mínima de Operación deportiva

El endpoint debe poder entregar, como mínimo:

- mediana de socios por instructor;
- máximo de socios por instructor con instructor presente;
- minutos sin cobertura;
- porcentaje de tiempo sin cobertura;
- serie temporal de socios;
- serie temporal de instructores de piso;
- intervalos de 15 minutos sin cobertura.

---

## 21. Permisos

Se mantiene la regla de la v1:

**Aforo y Asistencia sigue limitado a ADMICORP durante la beta**, hasta que se acuerde una ampliación de permisos.

El backend sigue siendo la fuente real de autorización.

---

## 22. Fuera de alcance de esta v2

Quedan para una fase posterior:

- socios multiclub;
- uso fuera de sucursal de origen como KPI propio;
- tarifa × utilización;
- vencimiento de membresía;
- dinero asociado a baja utilización;
- integración directa con Contact Center;
- campañas automáticas;
- score de riesgo de baja;
- predicción de abandono;
- límites automáticos de carga por instructor.

Estas ideas no se eliminan; simplemente no deben bloquear esta primera versión.

---

## 23. Orden recomendado de implementación

La implementación debe avanzar por bloques pequeños.

### Bloque 1 — Base correcta

- fuente de socios activos;
- elegibilidad por periodo;
- cruce por `id_socio`;
- utilización de la base.

### Bloque 2 — Comportamiento

- frecuencia;
- recencia;
- detalle de socios;
- socios para seguimiento.

### Bloque 3 — Nuevos socios

- activación;
- tiempo hasta primera visita.

### Bloque 4 — Operación deportiva

- presencia de `INSTRUCTOR PISO`;
- socios por instructor;
- minutos sin cobertura;
- detalle de intervalos.

No se deben construir todos los KPIs al mismo tiempo.

---

## 24. Criterios de aceptación

La v2 se considera correctamente implementada cuando:

1. La pantalla tiene las vistas **Resumen**, **Salud de la base** y **Operación deportiva** sin duplicar el módulo.
2. Cada vista tiene como máximo cuatro indicadores principales.
3. Resumen conserva las funciones actuales.
4. Socios únicos usa `id_socio` cuando el tipo es SOCIO.
5. Salud de la base usa socios elegibles en el periodo, no sólo activos al día de hoy.
6. La utilización cuenta una visita en cualquier Ultra Gym como uso de la membresía.
7. La recencia se calcula contra el final del periodo consultado.
8. La frecuencia toma en cuenta los días en que el socio realmente estuvo activo.
9. Activación permite que la primera visita ocurra en cualquier club.
10. Operación deportiva usa exclusivamente `INSTRUCTOR PISO`.
11. Los cálculos de cobertura se hacen por intervalos de 15 minutos.
12. Un intervalo con socios y cero instructores se identifica como **Sin cobertura**.
13. No se muestran etiquetas de riesgo ni límites inventados.
14. Las listas largas se abren en detalle o modal.
15. Los cálculos y permisos viven en backend.
16. La cobertura de identidad queda disponible como dato de control.
