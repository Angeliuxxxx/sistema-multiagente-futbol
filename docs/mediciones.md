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

## Desfase de `dias_desde_ultimo_partido` (02/11/2026)

Script: `backend/scripts/auditar_dias_descanso.py` (no reentrena nada; usa el modelo y los CSV tal cual).
Problema: al entrenar la feature resta horas de inicio reales; en inferencia la fecha llegaba a las 00:00 y salía 1 día menos
en ~57 % de los casos (training-serving skew).

**(a) Hora de inicio** (4.180 partidos): mediana **17:30**, moda **20:00** (solo 14,4 % de los partidos; después 17:30, 19:00,
15:15, 12:00, 13:00). `df_final_features` coincide al 100 % con `diff().dt.days` sobre `team_matches`.

**(b) Feature simulada vs. la de entrenamiento** (8.360 − 31 filas equipo-partido con partido previo):
| Hora por defecto | MAE (días) | Coincidencia exacta | Sesgo medio |
|---|---|---|---|
| **17:30 (mediana)** | **0,282** | **71,8 %** | −0,07 |
| 19:00 | 0,294 | 70,6 % | +0,09 |
| 20:00 (moda) | 0,378 | 62,2 % | +0,30 |
| 00:00 (comportamiento anterior) | 0,567 | 43,3 % | −0,57 |

Barrido por hora entera: el máximo está en 18 h (72 %); 17 h–19 h quedan en 69–72 %, así que la elección no es crítica.

**(c) Log-loss en prueba** (1.140 partidos, ≥ 2022-08-01):
| Feature | Log-loss |
|---|---|
| Original (entrenamiento) | 1,0513 |
| Simulada 17:30 | 1,0514 |
| Simulada 19:00 | 1,0516 |
| Simulada 20:00 | 1,0519 |
| Simulada 00:00 | 1,0509 |

Lectura honesta: el modelo es **poco sensible** a este desfase (diferencias ≤ 0,001, dentro del ruido). Por log-loss
la "mejor" sería 00:00, pero por 0,0004; no es evidencia. Se elige **17:30** por fidelidad de la feature (menor MAE, sesgo ≈ 0, mayor
coincidencia), que es la causa real del problema y no depende de ruido de la muestra. La importancia práctica es sobre todo evitar
valores 0–1 que el modelo no vio (mínimo en entrenamiento: 2).

## Calibración del modelo (02/11/2026)

Script: `backend/scripts/calibracion.py` (no reentrena ni toca el `.pkl`). Prueba = 1.140 partidos (≥ 2022-08-01), entrenamiento = 3.019.
Bins por cuantiles (8 bins, ~142 partidos cada uno). Figuras en `docs/figuras/` (`fiabilidad_original.png`,
`fiabilidad_calibrado.png`, `fiabilidad_sustituto.png`).

### Línea base y modelo
| | Log-loss en prueba |
|---|---|
| Línea base exacta (frecuencias de entrenamiento: visitante 0,2862 / empate 0,2597 / local 0,4541) | **1,0663** |
| Modelo XGBoost desplegado | **1,0513** |

La ventaja sobre la línea base es de 0,015 nats: el modelo aporta poco, aunque es real.

### Calibración por clase del modelo desplegado (prueba)
| Clase | ECE | Brier (1 vs resto) | Log-loss (1 vs resto) | Prob. media predicha | Frec. real |
|---|---|---|---|---|---|
| Visitante | 0,046 | 0,193 | 0,572 | 0,323 | 0,289 |
| Empate | 0,083 | 0,199 | 0,588 | 0,339 | 0,257 |
| Local | 0,116 | 0,242 | 0,677 | 0,339 | 0,454 |

Brier multiclase 0,6337; ECE medio 0,0816. **Sesgo sistemático**: el modelo sobreestima el empate (predice 0,34, ocurre 0,26)
y subestima la victoria local (predice 0,34, ocurre 0,45). Se ve en la figura: casi todo el rango local queda por encima de la
diagonal y el empate por debajo. Es consistente con `class_weight` balanceado, que reparte el peso igual entre las tres clases
aunque la local sea la más frecuente. Con ese peso se optimizó la log-loss en validación, pero las probabilidades salen
desplazadas hacia la uniformidad.

### Calibrar con la última temporada de entrenamiento (2021-08-01 … 2022-08-01, 380 partidos), tal como se pidió
| Variante (modelo desplegado) | Log-loss prueba | Brier multiclase | ECE medio |
|---|---|---|---|
| Original | 1,0513 | 0,6337 | 0,0816 |
| + Isotónica | 1,3581 | 0,6735 | 0,1195 |
| + Platt multinomial | 1,2040 | 0,6926 | 0,1153 |

**Empeora mucho** (Δ log-loss +0,31 y +0,15, ICs bootstrap lejos de 0). Causa: el modelo **ya vio** esa temporada al entrenar.
Su log-loss ahí es 0,974 frente a 1,051 en prueba, es decir, sus probabilidades son demasiado seguras, y el calibrador aprende
una corrección para un modelo sobreajustado que no vale en datos nuevos. Con el modelo desplegado no hay ningún tramo
anterior a la prueba que sea «no visto»; esta variante no se puede evaluar bien sin reentrenar.

### Comprobación sin sesgo: modelo sustituto en memoria
Para saber si calibrar ayudaría de verdad se entrenó **en memoria** (no se guarda; el pkl no se toca) un XGBoost con los mismos
hiperparámetros y el mismo `class_weight` balanceado, pero solo con los 2.639 partidos anteriores a 2021-08-01. Sus
probabilidades en 2021-22 ya son fuera de muestra (log-loss 1,0663), como lo serán en prueba.

| Variante (sustituto) | Log-loss prueba | Brier multiclase | ECE medio | Δ log-loss vs sustituto (IC95 bootstrap) |
|---|---|---|---|---|
| Sin calibrar | 1,0538 | 0,6353 | 0,0792 | — |
| + Isotónica | 1,0598 | 0,6176 | 0,0483 | +0,0059 [−0,028, +0,049] (ruido) |
| + Platt multinomial | **1,0288** | **0,6167** | **0,0482** | **−0,0250 [−0,039, −0,011]** |

Platt mejora log-loss (−0,025), Brier y ECE (0,079 → 0,048), y el IC no cruza el cero. La isotónica mejora ECE y Brier pero no la
log-loss (demasiados grados de libertad para 380 partidos). El sustituto + Platt (1,0288) queda también por debajo del modelo
desplegado (1,0513) y de la línea base (1,0663).

### Propuesta (NO aplicada)
Calibrar con Platt multinomial (regresión logística sobre log-probabilidades, 12 parámetros). Para hacerlo bien hace falta **un
modelo entrenado sin la temporada de calibración** (como el sustituto): reentrenar hasta 2021-08-01, calibrar con 2021-22 y
evaluar en prueba; el modelo final se reentrenaría con todo y reutilizaría el calibrador (con la salvedad de que cambian algo
las probabilidades). Eso toca el `.pkl`, así que queda para decisión del autor. Limitaciones: una sola partición cronológica,
380 partidos de calibración, y el sustituto no es exactamente el modelo desplegado.

## Sin RAG vs. con RAG (02/11/2026)

Script: `backend/scripts/evaluar_sin_rag.py`. Mismas 11 preguntas de desarrollo (`evaluar_frases`), mismo LLM (qwen2.5:7b, temperature 0,
num_ctx 2048, ya calentado) y mismo criterio de acierto que `evaluar_respuestas` (hecho clave en el texto). «Sin RAG» = pregunta directa
al modelo con un prompt neutro («Eres un asistente experto en fútbol. Responde en español, de forma clara y breve»), sin fragmentos.
Los ms de «con RAG» son búsqueda + LLM por `/chat`.

| Pregunta | Sin RAG | ms | Con RAG | ms |
|---|---|---|---|---|
| ¿Cuántos suplentes se pueden usar en un partido? | ✘ | 2.825 | ✘ | 4.046 |
| ¿Cuántas sustituciones puede hacer cada equipo? | ✔ | 3.722 | ✔ | 4.144 |
| ¿Cómo funciona la sustitución por conmoción cerebral? | ✘ | 3.803 | ✔ | 6.881 |
| ¿Cuántos equipos descienden de Primera División? | ✘ | 1.690 | ✘ | 2.110 |
| ¿Cuántos puntos se dan por una victoria? | ✔ | 1.412 | ✔ | 2.376 |
| ¿Cuántos equipos participan en Primera División? | ✔ | 1.236 | ✔ | 2.403 |
| ¿Cómo se desempata si dos equipos terminan con los mismos puntos? | ✘ | 3.090 | ✔ | 6.006 |
| ¿Cuántas amonestaciones llevan a una suspensión? | ✘ | 2.788 | ✔ | 4.063 |
| ¿Cuántos futbolistas extranjeros no comunitarios puede inscribir un club? | ✘ | 3.444 | ✔ | 3.478 |
| ¿Cuándo abre el periodo de inscripción de licencias de invierno? | ✘ | 3.636 | ✔ | 3.322 |
| ¿En qué horarios se juegan los partidos del sábado? | ✔ | 4.600 | ✔ | 3.375 |
| **Total** | **4/11** | 2.931 medio | **9/11** | 3.836 medio |

Lectura:
- RAG sube de 4/11 a 9/11 (+5) a un coste de ~0,9 s de media. Los aciertos sin RAG son preguntas de cultura general
  (3 puntos, 20 equipos) o coincidencias; las que dependen del reglamento 2026/27 (amonestaciones: dijo 3, real 5; extranjeros:
  dijo 4, real 3; licencias: dijo «octubre», real 2 de enero de 2027) las falla con seguridad y sin avisar de que no sabe.
- Los aciertos sin RAG son generosos: «sustituciones» acierta por el «5» genérico de la Champions, y «sábado» por «a partir de las
  12:00», aunque el modelo inventa «hasta las 22:00» (el reglamento dice 21:01). El hecho clave es una cifra corta; no mide si el
  resto de la respuesta es correcta, ni la cita, que solo existe con RAG.
- Con RAG hay dos fallos (suplentes, descienden); los dos ya estaban documentados arriba. Sin RAG, «descienden» responde «2 equipos»
  (incorrecto: son 3) y lo afirma con seguridad; con RAG responde «No encontré esa información». Es preferible, aunque cuente igual como fallo.
- Muestra pequeña (11), una sola corrida con temperature 0.

## Arreglo del fallo «descienden» (02/11/2026)

**Causa** (medida): el fragmento del Art. 8 con «posiciones 18ª, 19ª y 20ª» dice «descenderán»/«descenso» (raíces `descend`/`descens`); la
pregunta dice «descienden» (`desciend`, verbo irregular e→ie que Snowball no une). BM25 no daba puntos por ese término (el
fragmento quedaba 9.º en BM25 por palabras genéricas) y en embeddings quedaba 16.º; RRF lo dejaba fuera del cupo de 3.

Opciones medidas solo con las preguntas de desarrollo (`evaluar_frases` 11 + 2 de alcance, `evaluar_recuperacion`, `evaluar_respuestas` con 7B, in-process, 1 corrida):
| Variante | frases | recuperación | respuestas | Notas |
|---|---|---|---|---|
| Base | 10/11 | 17/17 | 9/11 | |
| A. Léxico de dominio (`descend`/`desciend`/`descens`→`descens`, ídem *ascen*) | 10/11 | 17/17 | 9/11 | BM25: puesto 9→1, pero RRF lo deja 4.º (cupo 3) |
| S. Quitar de BM25 `equip`, `primer`, `division` | 10/11 | **16/17** | 9/11 | no arregla y rompe una de recuperación |
| **A+S (elegida)** | **11/11** (alcance 2/2) | **17/17** | **10/11** | sin tocar fusión, cupo ni latencia (~4,2 s medio) |
| Referencia: A + peso ×3 del léxico en RRF | 11/11 | 17/17 | 9/11 | rompe «sustituciones»; cambia la fusión de todas las consultas |
| Referencia: cupo de Normas 3→4 | 10/11 | 17/17 | 9/11 | no arregla; +2 s por contexto más largo |

**Elección: A+S.** Ninguna sola funciona; juntas son dos cambios pequeños y locales al tokenizador (`app/retrieval.py`), simétricos
en índice y consulta, sin reindexar. Pesar el léxico ×3 cambia el comportamiento de todas las búsquedas y regresó una pregunta.
Respuestas 10/11: queda solo «suplentes» (fallo de generación por ambigüedad, ya documentado).

Salvedades: (1) las palabras S y el léxico se eligieron mirando el fallo de desarrollo; la validez fuera de muestra la dirá el
held-out. (2) S es específica de este corpus (solo Primera División); en otro dominio no valdría. (3) El léxico cubre solo
descender/ascender; otros verbos irregulares siguen sin unirse. (4) Respuestas: una corrida, n=11; 9→10 no es una diferencia estadística.

## Held-out de RAG (02/11/2026, ejecutado UNA vez, tras el arreglo A+S)

Script `backend/scripts/evaluar_heldout_rag.py`; preguntas en `backend/scripts/datos_evaluacion/heldout_rag.json` (commiteadas antes de tocar el
recuperador). Cubren artículos NO usados para afinar (lista de usados en el JSON): Normas Art. 9, 11, 12, 28; Reglas 2, 3, 10, 13, 15, 16.

| | Desarrollo (11) | Held-out (10) |
|---|---|---|
| Frase clave en los 8 fragmentos | 11/11 | **9/10** |
| Hecho clave en la respuesta | 10/11 | **9/10** |

Fallo: «¿Cuánto puede durar como máximo cada periodo de tiempo suplementario?» (Regla 10): el fragmento no llegó a los 8 y el modelo
respondió «No encontré esa información» (fallo de recuperación; abstención correcta, no alucinación). Los demás llegaron en las posiciones 1–5
(varios en la 4–5: margen estrecho dentro de 8). Latencia media de este lote ≈ 4,1 s.

Lectura prudente: n=10, intervalo muy ancho (9/10 → IC95 de Wilson ≈ 60–98 %); el held-out lo redactó la misma persona que el desarrollo, y
la métrica de «hecho clave» es generosa (la respuesta a «mínimo de jugadores» es confusa aunque contiene «siete»). La caída respecto al
desarrollo (11/11) es lo esperable al pasar a datos no vistos. No se retocó nada tras ver estas cifras.
