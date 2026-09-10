# Forecast histórico de bajas

## Objetivo

El Forecast de bajas no debe asumir que las bajas se materializan de forma uniforme durante todos los días del mes. El comportamiento histórico de Ultra muestra que una proporción importante de las bajas suele registrarse durante la primera parte del mes y que el ritmo posterior desacelera.

Por ese motivo, la proyección operativa de bajas utiliza una curva histórica de avance por día del mes en lugar de una extrapolación lineal.

## Fuente

La curva utiliza exclusivamente:

- KPI Desempeño.
- Snapshots `daily`.
- Snapshots `is_canonical = TRUE`.
- Meses completos anteriores al mes que se está pronosticando.
- Total cadena, excluyendo la fila `BECA`.

El mes que se está pronosticando nunca participa en la construcción de su propio factor histórico.

## Construcción de la curva

Para cada mes histórico cerrado y para cada día `N` disponible se calcula:

```text
avance_mes_dia_N = bajas_cadena_dia_N / bajas_cadena_cierre_mes
```

Después se agrupan todos los meses históricos para el mismo día del mes y se obtiene:

- P25 del avance histórico.
- Mediana del avance histórico.
- P75 del avance histórico.
- Número de meses disponibles.

El forecast operativo utiliza la **mediana** porque es más robusta ante correcciones o valores atípicos de algunos cierres.

P25 y P75 se conservan como información de auditoría/sensibilidad, pero no modifican el pronóstico operativo.

## Fórmula operativa

Para una sucursal con bajas reales acumuladas `B` y un factor histórico mediano `H` correspondiente al día de corte de KPI Desempeño:

```text
forecast_cierre_bajas = B / H
```

El remanente mostrado en la columna auxiliar del Forecast es:

```text
forecast_restante = forecast_cierre_bajas - B
```

Por tanto:

```text
pronostico_cierre = bajas_reales_MTD + forecast_restante
```

Ejemplo conceptual:

- Bajas reales al día 7: 50.
- Mediana histórica de avance al día 7: 33.8%.

```text
forecast_cierre = 50 / 0.338 = 147.9
```

La proyección lineal equivalente en un mes de 30 días sería:

```text
50 / 7 * 30 = 214.3
```

La diferencia existe porque el modelo histórico reconoce que las bajas no se distribuyen uniformemente durante el mes.

## Validación a nivel cadena

Se realizó backtesting `leave-one-month-out`: al evaluar un mes histórico, ese mismo mes se excluye de la curva utilizada para pronosticarlo.

Resultados representativos:

| Día | Error promedio histórico | Error promedio lineal | % meses donde gana histórico |
| ---: | ---: | ---: | ---: |
| 7 | 16.7% | 50.5% | 82.1% |
| 9 | 10.8% | 41.6% | 85.4% |
| 14 | 11.7% | 25.6% | 85.0% |
| 16 | 7.6% | 20.8% | 88.1% |
| 23 | 5.0% | 9.6% | 76.2% |

Los primeros días siguen teniendo mucha incertidumbre aun con el modelo histórico. La mejora empieza a ser material aproximadamente desde los días 6–7.

## Validación a nivel sucursal

La curva se construye a nivel cadena y se aplica al acumulado real de cada sucursal. Antes de adoptar esta regla se validó expresamente que el factor de cadena también mejorara la predicción por sucursal.

Se evaluaron 16,852 casos `sucursal + mes` entre los días 6 y 24.

Resultado agregado ponderado por número de casos:

- Error promedio lineal: aproximadamente 29.1%.
- Error promedio con curva histórica de cadena: aproximadamente 14.8%.
- Reducción relativa del error: aproximadamente 49%.
- Casos donde el histórico supera al lineal: aproximadamente 72.5%.

Resultados representativos:

| Día | Error lineal | Error histórico cadena | % casos donde gana histórico |
| ---: | ---: | ---: | ---: |
| 7 | 52.7% | 21.1% | 79.9% |
| 9 | 43.9% | 15.8% | 82.4% |
| 14 | 28.8% | 16.5% | 74.3% |
| 16 | 24.1% | 12.6% | 77.2% |
| 24 | 10.2% | 7.6% | 63.9% |

Esta validación es la razón por la que se utiliza una curva común de cadena para las sucursales en la primera versión del modelo.

## Decisiones deliberadas

### No se usa día de semana

Se exploró un posible ajuste por lunes/martes/miércoles/etc. Aunque se observó señal residual, se decidió no incorporarlo en esta versión para mantener el modelo simple, auditable y respaldado únicamente por una capa que ya mostró una mejora material en backtesting.

### No se usa proyección lineal como fallback silencioso

Si no existe un factor histórico válido para el día solicitado, el Forecast no debe volver silenciosamente al modelo lineal. La ausencia de histórico debe ser visible para evitar mezclar metodologías sin que el usuario lo sepa.

### Días 1–5

El sistema puede calcular el factor histórico de estos días si existe información, pero debe considerarse una proyección de baja confiabilidad. El backtest mostró errores todavía elevados en esta etapa del mes.

## Trazabilidad en el Excel

La hoja `Info` identifica la metodología utilizada y su fuente. La columna auxiliar de bajas conserva la fórmula que transforma las bajas MTD en el remanente histórico, y permanece oculta igual que las demás columnas técnicas del Forecast.

El bloque visible mantiene:

- Meta bajas.
- Bajas reales MTD.
- Pronóstico de cierre.
- Pronóstico de cierre %.
- Diferencia meta vs pronóstico.

## Regla vigente

La versión inicial del modelo queda definida como:

```text
Forecast bajas = Bajas reales MTD / mediana histórica del avance del día de corte
```

con histórico canónico de meses completos anteriores, a nivel cadena, sin ajuste adicional por día de semana.
