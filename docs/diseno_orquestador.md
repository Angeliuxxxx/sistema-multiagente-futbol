# Diseño del orquestador

El orquestador (`backend/app/orquestador.py`, endpoint `POST /preguntar`) decide a quién va cada pregunta:
`prediccion` (modelo XGBoost, llamado directamente), `conocimiento` (RAG, `responder_conocimiento`), `aclarar`
(falta el rival) o `fuera_de_alcance`.

## Por qué reglas y no un LLM en el router
- **Determinista y auditable.** La misma pregunta siempre va a la misma ruta y cada decisión devuelve el `motivo` (la regla
  que se cumplió). Con un LLM habría que defender un resultado que puede cambiar entre ejecuciones.
- **Latencia.** El router tarda microsegundos. Un LLM local en la RTX 4050 (6 GB) añadiría 1–3 s antes de empezar la
  respuesta real, con un presupuesto total de 5 s (RNF) en el que el RAG ya gasta 2–6 s.
- **Memoria y costo.** El 7B ya ocupa ~5 GB de VRAM con el RAG; un segundo uso del LLM compite por el mismo recurso. Sin servicios de pago.
- **Es medible.** Se evalúa con `scripts/evaluar_orquestador.py` (precisión por ruta y matriz de confusión) y cada fallo
  señala qué regla corregir.
- **El dominio es cerrado.** Solo hay dos capacidades reales y las distingue el vocabulario (equipos + verbos de
  pronóstico vs. términos de reglamento). Es el caso donde las reglas rinden bien.

Costo asumido: las reglas no entienden lo que no está en su vocabulario. Se acepta porque el error más probable es
caer en `fuera_de_alcance`/`aclarar`, que son respuestas seguras, y no inventar una respuesta.

## Reglas (en orden de prioridad)
1. Dos equipos + señal de pronóstico → `prediccion` (el primero nombrado es el local).
2. «Clásico» + señal de pronóstico, sin equipos → `prediccion` Barcelona–Real Madrid.
3. Un equipo + señal de pronóstico → `aclarar` (falta el rival).
4. Señal de pronóstico sin equipos y sin vocabulario de reglamento → `aclarar`.
5. Vocabulario de reglamento, liga o historia → `conocimiento` (aunque nombre equipos: «origen del Clásico entre Barcelona y Real Madrid»).
6. Si no, `fuera_de_alcance`.

Equipos: nombres reales de `/teams` + alias (Barça, Atleti, «el Madrid»…), sin tildes ni mayúsculas, y el alias más
largo gana («Atlético de Madrid» no cuenta como Real Madrid).

## Decisiones de la predicción
- Campos reales de `PredictRequest`: `local: str`, `visitante: str`, `fecha: date | None` (por defecto, hoy).
- Los datos terminan el 2025-05-25. Sin fecha del usuario se usa el **día siguiente al último dato**, no hoy: con la fecha
  de hoy `dias_desde_ultimo_partido` valdría ~500, un valor que el modelo nunca vio al entrenar. La respuesta lo dice.
- La respuesta de predicción es una plantilla (no pasa por LLM) y siempre aclara quién es local.

## Límites conocidos (probados a mano después de la evaluación, sin retocar reglas)
- «Barcelona vs Madrid» sin verbo de pronóstico → `fuera_de_alcance` (debería ser predicción).
- «¿Cuántos puntos tiene el Madrid?» → `conocimiento` por la palabra «puntos» (es una estadística que nadie cubre).
- «¿Quién ganó el clásico de 2011?» → `conocimiento` (el corpus no lo tiene; el RAG responderá que no encontró).
- No se extrae la fecha del texto: solo el campo opcional `fecha` de la petición.
