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
