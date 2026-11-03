# Modelo B: predicción con datos hasta ayer

El modelo A (12 features con xG y PPDA) no puede predecir partidos actuales: esas dos métricas no existen para nada posterior a
mayo de 2025 en una fuente que podamos usar con licencia. El modelo **B** conserva el diseño de A (XGBoost, `class_weight`
balanceado, split cronológico, `TimeSeriesSplit`, forma = media de los 5 partidos anteriores con `shift(1)`) y cambia solo las
features, por otras que SÍ existen para todas las temporadas. **A no se modifica**: sigue disponible con `modelo="a"`.

## Features de B (12, 6 por equipo, misma estructura que A)
`forma_goles_favor`, `forma_goles_contra`, `forma_puntos`, `forma_tiros_puerta`, `forma_tiros`, `dias_desde_ultimo_partido`.
Tiros y tiros a puerta sustituyen a xG y PPDA. El descanso se mide en **días de calendario** (no en horas) para que entrenamiento y
predicción lo calculen igual (ver el desfase del modelo A en `docs/datos.md`). Variante B1 = solo las 4 de resultados (8 features).

## Fuentes
| Tramo | Fuente | Cómo entra |
|---|---|---|
| 2014-08 → 2025-05 | histórico del proyecto (`la_liga_2014_2025_all_matches_final.csv`) | ya estaba |
| 2025-08 → ayer | CSV de football-data.co.uk (`data/2025-2026.csv`, `data/2026-2027.csv`), **descargados a mano** desde el navegador | resultados y tiros |
| Partidos posteriores al último CSV, y calendario | API de football-data.org (plan gratis, token en `.env`) | resultados sin tiros; las medias de forma ignoran los tiros que faltan |

`football-data.co.uk/robots.txt` veta a los rastreadores de IA, así que **ningún proceso automático descarga esos CSV**: se
actualizan a mano. La API oficial cubre mientras tanto los resultados (no los tiros).

## Resultados (`python -m scripts.entrenar_modelo_b`, desde `backend/`)
Mismos hiperparámetros por búsqueda aleatoria (30 combinaciones, `TimeSeriesSplit(5)`) y mismo corte que A (train < 2022-08-01).
Log-loss: menor es mejor. «±» es dos errores estándar de la diferencia **partido a partido**.

**Tramo 1 — el mismo test que A** (1.140 partidos, 2022-08 → 2025-05):

| Modelo | Log-loss | Accuracy |
|---|---|---|
| Frecuencia de clases (sin features) | 1,0663 | 0,454 |
| **A** (xG, PPDA) | 1,0513 | 0,456 |
| B1 (solo resultados) | 1,0591 | 0,433 |
| **B2** (+ tiros) | **1,0502** | 0,470 |

B2 − A = −0,0010 ± 0,0106: **no hay diferencia demostrable entre A y B2**. Tampoco A (−0,0150 ± 0,0218) ni B2 (−0,0161 ± 0,0194)
superan de forma demostrable a la frecuencia de clases en este tramo.

**Tramo 2 — datos que A no puede ver** (486 partidos, 2025-08 → 2026-11-01; B reajustado con datos hasta 2025-07):

| Modelo | Log-loss | Accuracy |
|---|---|---|
| Frecuencia de clases | 1,0526 | 0,482 |
| Cuotas medias de las casas de apuestas (solo referencia) | 0,9549 | 0,549 |
| B1 | 1,0627 | 0,461 |
| **B2** | **1,0378** | 0,453 |

B2 − B1 = −0,0250 ± 0,0128: los tiros sí aportan sobre usar solo resultados. B2 − frecuencia de clases = −0,0148 ± 0,0328: no
demostrable. B2 − cuotas = +0,0829 ± 0,0277: **las casas de apuestas son claramente mejores**.

## Qué se puede afirmar (y qué no)
- Se puede: quitar xG y PPDA y poner tiros **no empeora de forma demostrable** el modelo (1,0502 frente a 1,0513), y permite predecir
  con datos de ayer. Los tiros aportan sobre usar solo resultados.
- No se puede: decir que B (ni A) predice mejor que el azar informado por la frecuencia de clases; los intervalos incluyen 0 con
  ~1.100 y ~500 partidos. Ni acercarlo al mercado: las cuotas llevan información que el modelo no tiene (lesiones, alineaciones, mercado).
- La utilidad de B es la **actualidad** y la transparencia (se sabe qué lo alimenta y cuánto vale), no una precisión superior.
- Limitaciones: equipos recién ascendidos con pocos partidos en Primera; equipos que vuelven tras años (la «forma» sale de su última
  etapa, con descansos de cientos de días); los tiros de los partidos que solo vienen de la API son desconocidos hasta que se baje un CSV nuevo.

## Modelo en producción
`data/modelo_predictivo_laliga_b.pkl`: B2 reajustado con los 4.645 partidos jugados hasta 2026-11-01 y los hiperparámetros del
tramo 1 (`data/modelo_b_params.json`). Se regenera con `python -m scripts.entrenar_modelo_b --guardar`.

## Actualizar los datos antes de una demostración
1. Bajar a mano `SP1.csv` de 2026/27 desde football-data.co.uk (Primera División) y guardarlo como `data/2026-2027.csv`.
2. `POST /actualizar` (o reiniciar la API): vuelve a leer la API y recalcula la forma.
3. Opcional: `python -m scripts.entrenar_modelo_b --guardar` para reajustar el modelo con los partidos nuevos.

## Registro de predicciones (evaluación hacia adelante)
`data/registro_predicciones.jsonl` guarda cada pronóstico de B **antes** del partido; después se puntúa con el resultado real
(`backend/app/registro.py`). Es la evidencia más fuerte que tiene el proyecto, porque no depende de decisiones tomadas viendo
los resultados.

- **Solo se añade** (nunca se reescribe), **una vez por partido** (manda la primera predicción) y **nunca con el partido empezado**
  (`backend/tests/test_registro.py`, probado con sabotajes). El archivo se versiona en Git: la fecha del commit es la prueba externa.
- Se registra al arrancar la API, con `POST /actualizar` o con `python -m scripts.registro_predicciones registrar` (próximos 10 días).
- Puntaje: acierto, log-loss, Brier y la diferencia frente a la frecuencia de clases con su error (±2 e.e.). **Con menos de 30 partidos
  jugados la interfaz dice que todavía no se puede concluir**: una jornada son 10 partidos y el error es mayor que cualquier diferencia.
- La interfaz lo muestra en la pestaña «Acierto» (`GET /registro`); la pestaña «Posiciones» usa `GET /tabla`.
- Primer registro: 10 partidos de la jornada 12 (2026-11-06 a 2026-11-08), guardados el 2026-11-03.
