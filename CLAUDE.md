# Sistema Multiagente de Analítica de Fútbol (LaLiga) — Tesis

Sistema de 3 agentes: **orquestador**, **conocimiento (RAG)** y **predictivo (XGBoost)**.
Backend FastAPI, frontend React (chat + dashboard), ChromaDB, LangChain. Una sola liga (LaLiga).

## Estructura del repo
- `/data` — CSVs, `modelo_predictivo_laliga.pkl`, índice de Chroma (no se sube lo pesado)
- `/notebooks` — `01_eda_partidos`, `02_modelo_baseline`, `03_rag_corpus`, `04_agente_conocimiento`
- `/backend` — FastAPI + agentes (por crear)
- `/frontend` — React (por crear)
- `/docs` — notas explicativas, diagrama de arquitectura

## Estado
- Fase 1 (EDA + features) y Fase 2 (modelo) cerradas.
- Fase 3 (RAG): reconstruyendo el corpus v2 y eligiendo el LLM. Luego: orquestador, API, UI, despliegue.

## Decisiones ya tomadas (no reabrir sin evidencia)
- Modelo: XGBoost tuneado con `class_weight` balanceado (log-loss 1.0513 vs RF 1.0531 vs LR 1.0623).
- Split cronológico (train < 2022-08-01); validación con `TimeSeriesSplit`. Nunca split aleatorio.
- Sin fuga de datos: solo features calculadas con `shift(1)`. Prohibido usar columnas post-partido
  (xG, tiros, goles del propio partido) como features.
- 12 features: `home_`/`away_` × (`forma_goles_favor`, `forma_goles_contra`, `forma_xg`, `forma_puntos`,
  `forma_ppda`, `dias_desde_ultimo_partido`).
- Funciones invocables existentes: `ultima_forma(equipo, fecha, team_matches)` y `predecir_partido`.
- RAG: ChromaDB con métrica coseno; embeddings `paraphrase-multilingual-MiniLM-L12-v2`
  (límite ~128 tokens: chunks de ≤500 caracteres). Metadata por chunk: `documento`, `seccion`, `pagina`, `division`.
- Corpus: Normas de Competición Primera/Segunda 2026/27, Reglas de Juego IFAB 2026/27 y 2 PDFs de Wikipedia.
- LLM: Ollama `qwen2.5:7b` en desarrollo, siempre detrás de la interfaz de LangChain para poder cambiarlo
  con una línea. Decisión de LLM para el despliegue: pendiente.

## Convenciones
- Python 3.10+, type hints, comentarios en español que expliquen el **porqué**, no solo el qué.
- Secretos solo en `.env` (en `.gitignore`), cargados con python-dotenv. **No exportar `ANTHROPIC_API_KEY`
  en el shell**: Claude Code la usaría en lugar de la suscripción y cobraría por API.
- Chroma: usar carpeta nueva si hay errores de base de datos; no reutilizar carpetas corruptas.
- Notebooks: una sola versión de cada celda, `Restart & Run All` antes de dar algo por bueno.
- Todo endpoint de FastAPI con modelos Pydantic y documentación OpenAPI.
- Cada respuesta del sistema debe indicar su fuente: conocimiento (con documento y página) o predicción.

## Cómo trabajar con el autor
- Es estudiante de 9.º semestre y debe poder defender cada línea: explica el porqué y avanza en pasos pequeños.
- Verifica con evidencia (shapes, conteos, ejemplos reales), no por suposición.
- No proponer servicios de pago sin avisar antes; el proyecto debe poder correr gratis en desarrollo.

## Requisitos no funcionales
Respuesta < 5 s, interfaz responsive, API keys fuera del repo, README claro, reproducible con `git clone`.
