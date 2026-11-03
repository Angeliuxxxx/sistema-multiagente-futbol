# Datos

## Fuente
`data/la_liga_2014_2025_all_matches_final.csv` es, **por inferencia**, un export de Understat: su esquema (`match_id`, `deep`,
`ppda`, `xpts`, además de `xg`, tiros y tiros a puerta) coincide con las métricas que publica ese sitio. **No está
confirmado** (el archivo no trae metadatos de origen); la procedencia exacta debe verificarse antes de citarla en la tesis.

## PDF del corpus RAG (no versionados)
Los PDF de `data/` son documentos de terceros y el repositorio es público, así que **no se versionan** (`data/*.pdf` en
`.gitignore`). Cada persona los descarga de su fuente y los coloca en `data/` con **estos nombres exactos** (los notebooks
03 y 05 los leen por ruta):

| Archivo | Lo usa | Fuente |
|---|---|---|
| `Primera_y_Segunda_Division.pdf` | 05 | «Normas Reguladoras y Bases de Competición de los Campeonatos Nacionales de Liga de Primera y Segunda División, temporada 2026-2027». Lo publica la **RFEF** (LaLiga organiza en coordinación con ella): <https://rfef.es/sites/default/files/2026-06/1._CNL_Primera_y_Segunda_Division.pdf> (en la RFEF se llama `1._CNL_Primera_y_Segunda_Division.pdf`; hay que renombrarlo) |
| `reglamento laliga 2025-2026.pdf` | 03 (y el exploratorio 04) | Primera página: «REGLAMENTO · TEMPORADA 2025/26», 41 páginas, PDF creado el 2025-09-19. **El archivo no indica quién lo emite** (el título de los metadatos es una plantilla sin rellenar), así que su origen oficial está por confirmar |
| `Reglas de Juego 2026_27_paginas individuales.pdf` | 03, 05 | Reglas de Juego IFAB 2026/27 en español: <https://theifab.com/documents>. Hay variantes «páginas dobles» e «individuales» con numeración distinta; el corpus usa **«páginas individuales»** y las citas de página del sistema dependen de ella |
| `Primera División de España - Wikipedia, la enciclopedia libre.pdf` | 03 | Artículo «Primera División de España» de es.wikipedia.org, exportado a PDF el 2026-08-10 (revisión `oldid=174757811`): <https://es.wikipedia.org/wiki/Primera_División_de_España> |
| `El Clásico - Wikipedia, la enciclopedia libre.pdf` | 03 | Artículo «El Clásico», exportado a PDF el 2026-08-10 (revisión `oldid=174777709`): <https://es.wikipedia.org/wiki/El_Clásico> |

Los PDF de Wikipedia son una captura de esa revisión; si cambia el artículo, el índice regenerado puede diferir del versionado. El texto de Wikipedia está bajo
CC BY-SA; los PDF no traen el pie de licencia, así que la versión exacta no consta en el archivo (Wikimedia usa hoy la 4.0).

`data/reglamento.pdf` (205 páginas, Reglamento General de la LNFP ratificado por el CSD, julio de 2024) **no lo usa ningún notebook ni el backend**: es un resto sin uso, ignorado por Git.

## Contenido (medido sobre el archivo)
- Rango: 2014-08-23 a 2025-05-25.
- 4.180 partidos y 31 equipos (`team_matches.csv`, derivado, tiene 8.360 filas: una por equipo y partido).
- 19 columnas: `match_id`, `date`, `home_team`, `away_team`, `home_goals`, `away_goals`, `home_xg`, `away_xg`,
  `home_shots`, `away_shots`, `home_sot`, `away_sot`, `home_deep`, `away_deep`, `home_ppda`, `away_ppda`, `home_xpts`,
  `away_xpts`, `season_mapped`.
- Las 12 features del modelo salen de aquí con `shift(1)` (ver CLAUDE.md).

## Decisión: datos actualizados con un segundo modelo (B), sin tocar el modelo A
Esta sección **sustituye** a la decisión anterior («no actualizar los datos»). Seguimos sin rastrear Understat (su `robots.txt` lo
prohíbe) y el dataset del modelo A no cambia: termina el 2025-05-25. Para predecir partidos actuales se añade un **modelo B** que no usa
xG ni PPDA, con datos de football-data.co.uk (CSV descargados a mano; su `robots.txt` veta a los rastreadores de IA) y de la
API oficial de football-data.org (token gratis en `.env`). Detalle, resultados y limitaciones: `docs/modelo_b.md`.

Qué se conserva: el modelo A con sus 12 features y su evaluación (decisión del proyecto); sigue accesible con `modelo="a"`.
Qué se reabre: solo se prueba, como ablación, qué pasa al sustituir xG y PPDA por tiros; el resultado (sin diferencia demostrable
en el mismo test) está en `docs/modelo_b.md`.

## Limitaciones del modelo A
- Los pronósticos de A usan la forma de los últimos 5 partidos **a mayo de 2025**; no reflejan nada posterior.
- Equipos que no jugaron en Primera en 2024/25 (p. ej. Cádiz, Almería, Granada) tienen su forma de temporadas anteriores.

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
