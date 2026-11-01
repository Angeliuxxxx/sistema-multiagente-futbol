# Mediciones

Hardware: portátil con NVIDIA GeForce RTX 4050 Laptop (6 GB de VRAM), WSL2, Ollama local. Sin servicios de pago.
Las cifras vienen de dos fuentes: las medidas anteriores que ya estaban anotadas en el código (fecha indicada) y las
medidas del **01/11/2026**, tomadas al implementar el alcance de Primera División.

## Latencia del LLM

### `num_ctx` (qwen2.5:7b) — medido el 27/10/2026, anotado en `backend/app/chat.py`
| num_ctx | VRAM | CPU | tok/s |
|---|---|---|---|
| 4096 | 5,2 GB | 18 % | 17,4–19,5 |
| 2048 | 5,0 GB | 16 % | 19,6–21,4 |

El prompt más largo de las 11 preguntas de `evaluar_frases` fue de 1.532 tokens, así que 2048 alcanza. Si el prompt lo
superara, Ollama lo trunca en silencio: hay que volver a medir si se sube `k` o el tamaño de chunk.

### Carga en frío
| Qué | Frío | Caliente | Fecha |
|---|---|---|---|
| Retrieval (primera pregunta vs segunda) | 4,4 s | 0,14 s | anotado en `retrieval.py` |
| Calentamiento del LLM 7B al arrancar | 18,2 s | — | 01/11/2026 |
| Calentamiento del LLM 3B al arrancar | 12,4 s | — | 01/11/2026 |
| Calentamiento del retrieval al arrancar | 0,6–0,7 s | — | 01/11/2026 |

### 7B vs 3B por `/chat` (11 preguntas de `evaluar_frases`, num_ctx=2048) — 01/11/2026
| Modelo | ms_llm medio | Hecho clave en la respuesta |
|---|---|---|
| qwen2.5:7b | 2.853 ms (2.ª corrida; 1.ª: 3.759 ms) | 9/11 |
| qwen2.5:3b | 1.347 ms | 7/11 |

El 3B es ~2× más rápido pero falla más y a veces responde solo con las citas (`[1] [2] [3]`) sin texto. Ambos
cumplen la meta de < 5 s en la mayoría de preguntas; el 7B roza o pasa los 5 s en conmoción cerebral y desempate (4,9–6,0 s).

## Evaluaciones de recuperación y respuesta (01/11/2026)

| Script | Antes del alcance | Con el alcance |
|---|---|---|
| `evaluar_recuperacion` (sección correcta en 8 fragmentos) | 16/17 | **17/17** |
| `evaluar_frases` (frase clave en 8 fragmentos, 11 casos) | 10/11 | 10/11 |
| `evaluar_frases`, casos de alcance (Segunda recupera Art. 17; Primera no trae Art. 17) | — | 2/2 |
| `evaluar_respuestas` con 7B (hecho clave en la respuesta) | — | 9/11 |
| `evaluar_respuestas` con 3B | — | 7/11 |

- Antes del alcance, "¿Cómo se desempata…?" devolvía el Art. 17 (Segunda) dos veces entre los 8 fragmentos.
- Fallos que persisten (7B):
  - «¿Cuántos equipos descienden de Primera División?»: el fragmento del Art. 8 no llega (✘ también en `evaluar_frases`)
    y el modelo responde correctamente «No encontré esa información». Es un fallo de recuperación, no del LLM.
  - «¿Cuántos suplentes…?»: sí llega «doce futbolistas» (pos. 2), pero el modelo contesta «cinco» (los cinco
    sustitutos del Art. 25 y de la Regla 3). Es un fallo de generación; la pregunta es ambigua (suplentes inscritos vs. sustituciones).

## Orquestador (02/11/2026)

Router por reglas (`app/orquestador.py`), sin LLM. Casos en `backend/scripts/datos_orquestador/`; los 36 casos se
redactaron y commitearon **antes** de escribir el router.

| Conjunto | Aciertos | Por ruta (predicción / conocimiento / aclarar / fuera) |
|---|---|---|
| dev (24) | 24/24 | 6/6 · 6/6 · 6/6 · 6/6 |
| heldout (12), ejecutado una vez | 12/12 | 3/3 · 3/3 · 3/3 · 3/3 |

Matriz de confusión diagonal en ambos. Lectura prudente: los conjuntos son pequeños y los redactó la misma persona que
las reglas, así que 100 % no es una garantía de generalización. Pruebas manuales posteriores (sin retocar reglas) mostraron
fallos en entradas fuera de estos conjuntos; ver «Límites conocidos» en `docs/diseno_orquestador.md`.

Latencia por `/preguntar` (qwen2.5:7b, RTX 4050 6 GB, ya calentado): predicción 299 ms, aclarar/fuera 1–3 ms,
conocimiento 4.018 ms (una medición).

### Orquestador, ajuste v1.1 (02/11/2026)
dev ampliado con 3 casos hallados a mano: 25/27 con las reglas v1 → **27/27** tras R1b y R4b. heldout (v1, congelado, no se usó
para decidir nada): **12/12**.
