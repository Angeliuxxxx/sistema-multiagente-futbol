# Datos

## Fuente
`data/la_liga_2014_2025_all_matches_final.csv` es, **por inferencia**, un export de Understat: su esquema (`match_id`, `deep`,
`ppda`, `xpts`, además de `xg`, tiros y tiros a puerta) coincide con las métricas que publica ese sitio. **No está
confirmado** (el archivo no trae metadatos de origen); la procedencia exacta debe verificarse antes de citarla en la tesis.

## Contenido (medido sobre el archivo)
- Rango: 2014-08-23 a 2025-05-25.
- 4.180 partidos y 31 equipos (`team_matches.csv`, derivado, tiene 8.360 filas: una por equipo y partido).
- 19 columnas: `match_id`, `date`, `home_team`, `away_team`, `home_goals`, `away_goals`, `home_xg`, `away_xg`,
  `home_shots`, `away_shots`, `home_sot`, `away_sot`, `home_deep`, `away_deep`, `home_ppda`, `away_ppda`, `home_xpts`,
  `away_xpts`, `season_mapped`.
- Las 12 features del modelo salen de aquí con `shift(1)` (ver CLAUDE.md).

## Decisión: no actualizar los datos
El dataset **no se actualiza**. Understat prohíbe el rastreo (`robots.txt` con `Disallow: /`) y lo respetamos: no se hacen
peticiones al sitio ni se usan librerías de scraping.

Alternativas descartadas:
- **football-data.org:** tiene API pública, pero no trae xG ni PPDA.
- **Mezclar fuentes** (histórico Understat + partidos recientes de otra): el modelo usa `forma_xg` y `forma_ppda`; sin esas
  columnas en los datos nuevos habría que reentrenar sin ellas, lo que reabre la decisión de las 12 features y cambia el
  modelo ya evaluado.

## Limitaciones y trabajo futuro
- Los pronósticos usan la forma de los últimos 5 partidos **a mayo de 2025** (último dato: 2025-05-25). No reflejan fichajes,
  lesiones ni resultados posteriores; para una fecha actual el modelo extrapola desde una forma antigua.
- Equipos que no jugaron en Primera en 2024/25 (p. ej. Cádiz, Almería, Granada) tienen su forma de temporadas anteriores.
- Actualizar exigiría una fuente **con licencia** que incluya xG y PPDA (así no cambian las 12 features ni hay que reentrenar
  por faltar columnas). Si aparece, bastaría regenerar `team_matches.csv` y, solo si cambia la distribución, reentrenar.

## Desfase entrenamiento-inferencia (`dias_desde_ultimo_partido`)

**Qué pasaba.** Al entrenar (notebook 01, celda 11) la feature es `groupby('team')['date'].diff().dt.days`: resta las horas de
inicio reales de dos partidos consecutivos (el 98,5 % de las filas tiene hora) y trunca a días enteros. En inferencia,
`ultima_forma()` hacía `(fecha - último_partido).days`, pero la fecha llegaba sin hora (`YYYY-MM-DD` = 00:00). Resultado: a la
fecha le faltaban entre 0 y 24 h y, por el truncado, la feature salía 1 día menos. Es *training-serving skew*: el mismo cálculo,
pero con entradas distintas. La verificación del notebook 02 no lo detectó porque usaba la fecha con hora del partido real.

**Cuánto afectaba** (`backend/scripts/auditar_dias_descanso.py`, detalle en `docs/mediciones.md`): con 00:00 solo el 43,3 % de
las filas coincidía con la feature de entrenamiento (MAE 0,57 días, sesgo −0,57, siempre hacia abajo). Con la fecha por defecto
(día siguiente al último dato) Barcelona salía con 0 días y Real Madrid con 1, valores que el modelo nunca vio (mínimo 2). Sobre
el log-loss del conjunto de prueba el efecto es pequeño (1,0509–1,0519 según la hora; original 1,0513): el modelo es poco sensible,
pero el sesgo era real y evitable.

**Cómo se corrigió** (sin reentrenar nada; el modelo y las métricas del notebook no cambian):
- `prediction.con_hora()`: si la fecha llega sin hora y algún equipo jugó ese día, se usa la hora **real** de ese partido
  (reproduce exacto la feature de entrenamiento); si no, `HORA_POR_DEFECTO = 17:30`, la hora mediana de los 4.180 partidos y la que
  mejor reproduce la feature (MAE 0,28 días, 71,8 % de coincidencia exacta, sesgo −0,07). Una fecha con hora se respeta.
- Sin fecha, `prediction.fecha_por_defecto()` = último dato + 7 días a las 17:30 (2025-06-01 17:30), con descansos de 6 y 8 días
  para Barcelona y Real Madrid.
- Límite que queda: una hora asumida nunca es la hora real de un partido futuro, así que ~28 % de las features simuladas difiere
  en 1 día. Si el usuario pide expresamente una fecha pegada al último dato (p. ej. 2025-05-26), el descanso 0 que sale es el
  real según la fórmula de entrenamiento, no un error.

**Prueba automática.** `backend/tests/test_desfase_dias_descanso.py` (`python -m tests.test_desfase_dias_descanso` desde `backend/`):
recorre una muestra de partidos reales, pide la fecha sin hora y exige que la feature sea idéntica a la de entrenamiento; también
comprueba que la fecha por defecto no baja del mínimo visto al entrenar. Con la lógica antigua falla en 673 de ~1.190 casos.
