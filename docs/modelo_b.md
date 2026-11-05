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
- Solo es fiable para partidos cercanos a los datos: para fechas lejanas (más de 30 días desde el último partido conocido de un equipo) el sistema añade un aviso de «forma desactualizada»; no corrige las probabilidades.
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

## Calibración de B (solo medida; el modelo no se tocó)
Script: `python -m scripts.calibracion_b` (desde `backend/`), mismo método que `scripts/calibracion.py` (A). Mismos cortes y mismos
hiperparámetros que `entrenar_modelo_b.py` (`data/modelo_b_params.json`, `class_weight` balanceado). Medido el 2026-11-04, con datos
hasta 2026-11-01: el tramo 2 crece con cada CSV nuevo, así que sus cifras cambiarán al repetirlo. Figura: `docs/figuras/fiabilidad_b.png`.

Probabilidad media predicha frente a frecuencia real, por clase:

| Clase | Tramo 1 (1.140): predicha / real | Tramo 2 (486): predicha / real |
|---|---|---|
| Victoria visitante | 0,329 / 0,289 | 0,336 / 0,274 |
| Empate | 0,327 / 0,257 | 0,322 / 0,245 |
| Victoria local | 0,344 / **0,454** | 0,342 / **0,481** |

ECE medio: 0,0766 (tramo 1) y 0,0931 (tramo 2). Log-loss: 1,0502 y 1,0378 (coinciden con la tabla de arriba, lo que confirma que se
reprodujo el mismo modelo).

Tabla de fiabilidad (predicha/observada por bin, de menor a mayor probabilidad; 8 bins en el tramo 1, 5 en el 2 porque con ~500 partidos
8 bins dejarían ~60 por casilla):

| | Tramo 1 | Tramo 2 |
|---|---|---|
| Visitante | 0,19/0,10 · 0,25/0,20 · 0,29/0,20 · 0,32/0,27 · 0,34/0,27 · 0,35/0,39 · 0,39/0,38 · 0,50/0,50 | 0,21/0,13 · 0,29/0,26 · 0,33/0,27 · 0,36/0,29 · 0,50/0,42 |
| Empate | 0,24/0,22 · 0,29/0,24 · 0,31/0,27 · 0,33/0,23 · 0,34/0,25 · 0,35/0,27 · 0,36/0,29 · 0,39/0,27 | 0,25/0,12 · 0,31/0,27 · 0,33/0,22 · 0,35/0,28 · 0,37/0,34 |
| Local | 0,21/0,22 · 0,26/0,38 · 0,29/0,34 · 0,31/0,37 · 0,34/0,48 · 0,37/0,54 · 0,43/0,58 · 0,54/0,71 | 0,21/0,33 · 0,29/0,42 · 0,33/0,47 · 0,37/0,41 · 0,51/0,77 |

**Qué se ve (hechos):** B reparte las tres probabilidades cerca de 1/3 y **subestima sistemáticamente la victoria local** (dice ~0,34;
ocurre ~0,45–0,48) y **sobrestima el empate y la visitante**. El patrón es el mismo en los dos tramos. El orden sí es informativo: en el
local, cuanto más alta la probabilidad que da B, más alta la frecuencia real (0,22 → 0,71).
**Hipótesis (no probada aquí):** el `class_weight` balanceado trata las tres clases como igual de frecuentes y empuja las probabilidades
hacia 1/3; la clase local, que es la más frecuente, es la que más sufre. No se cambió `class_weight` (decisión ya tomada).

**Modelo sustituto + Platt (INFORMATIVO, no aplicado a B).** Como en A: un sustituto en memoria (mismos hiperparámetros), entrenado solo
con datos anteriores a la temporada de calibración (tramo 1: < 2021-08, Platt con 2021-08→2022-08; tramo 2: < 2024-08, Platt con
2024-08→2025-08), para que sus probabilidades en esa temporada sean fuera de muestra.

| | Tramo 1 | Tramo 2 |
|---|---|---|
| Log-loss del sustituto sin calibrar → con Platt | 1,0514 → 1,0234 | 1,0396 → 1,0026 |
| ECE medio sin calibrar → con Platt | 0,0790 → 0,0363 | 0,0929 → 0,0537 |
| Δ log-loss (Platt − sustituto), ±2 e.e. | −0,0280 ± 0,0123 | −0,0371 ± 0,0243 |
| Δ log-loss (sustituto + Platt − frecuencia de clases), ±2 e.e. | −0,0429 ± 0,0160 | −0,0500 ± 0,0332 |

Lectura prudente: en este experimento Platt corrige el sesgo hacia el local y baja el log-loss, y los intervalos de la última fila no
incluyen 0. Pero es un **sustituto**, no el modelo en producción; el tramo 2 es corto (486 partidos, un solo vistazo); y habría que
decidir si calibrar y cómo (ventana, dónde se ajusta) **antes** de mirar más resultados. Si se calibrara, cambiaría la versión del modelo
(`version_modelo` del registro) y los pronósticos ya registrados dejarían de ser comparables. **La decisión es del autor; este script no
la aplica.**
