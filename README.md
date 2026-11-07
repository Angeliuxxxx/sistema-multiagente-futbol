# Sistema multiagente de analítica de fútbol (LaLiga)

Proyecto de tesis. Un chat y un panel web que responden dos tipos de pregunta sobre **LaLiga Primera División**:

- **Pronósticos de un partido** (victoria local, empate, victoria visitante) con un modelo XGBoost entrenado con la forma reciente de cada equipo.
- **Dudas de reglamento, competición e historia**, respondidas con un RAG sobre documentos oficiales y citando documento y página.

Cada respuesta indica su fuente: conocimiento (con documento y página) o predicción.

## Los tres agentes

| Agente | Qué hace | Cómo |
|---|---|---|
| **Orquestador** | Decide a quién va cada pregunta (`prediccion`, `conocimiento`, `aclarar` o `fuera_de_alcance`) | Reglas deterministas, sin LLM. Devuelve el `motivo` de su decisión |
| **Conocimiento (RAG)** | Responde sobre reglamento, competición e historia | ChromaDB (coseno) + BM25 fusionados con RRF, y un LLM local (Ollama `qwen2.5:7b`) detrás de LangChain |
| **Predictivo** | Probabilidades de un partido entre dos equipos | XGBoost con 12 features de forma (últimos 5 partidos), en dos versiones: **modelo A** (xG y PPDA; datos hasta mayo de 2025) y **modelo B** (tiros en lugar de xG/PPDA; datos hasta ayer, el de por defecto). Ver «Modelo B, datos y registro» |

```mermaid
flowchart TD
    U["Chat y panel (React)"] --> API["FastAPI"]
    API --> O{"Orquestador<br/>reglas, sin LLM"}
    O -->|pronóstico| P["Agente predictivo<br/>XGBoost"]
    O -->|reglamento o historia| K["Agente de conocimiento<br/>RAG + LLM"]
    O -->|falta el rival o fuera de alcance| M["Mensaje fijo"]
    P --> R["Respuesta con su fuente"]
    K --> R
    M --> R
    K -.-> OL["Ollama en el anfitrión"]
```

Diagramas de componentes, de flujo y de secuencia, y las decisiones con su porqué: [`docs/arquitectura.md`](docs/arquitectura.md).

## Requisitos

| Para | Necesitas |
|---|---|
| Ambos modos | [Ollama](https://ollama.com) corriendo en tu máquina con el modelo descargado: `ollama pull qwen2.5:7b`. Se probó en una GPU de 6 GB; en CPU será más lento |
| Docker | Docker con Compose v2 |
| Desarrollo | Python 3.10 o superior (el entorno de desarrollo y la imagen usan 3.14; la instalación limpia se probó con 3.14), Node.js y npm. **Unos 6,5 GB de disco para el entorno virtual**: `sentence-transformers` trae PyTorch con CUDA desde PyPI. Si tu `/tmp` es pequeño o está en RAM (WSL2, algunos Linux), `pip` falla con «No space left on device»: instala con `TMPDIR=$HOME/tmp pip install -r backend/requirements.txt`. Sin GPU puedes instalar antes `torch` CPU como hace el Dockerfile |
| Datos | La carpeta `data/` con `la_liga_2014_2025_all_matches_final.csv`, `team_matches.csv`, `chroma_index_v2/` y, para el modelo B actualizado, `2025-2026.csv` y `2026-2027.csv` (los `.pkl` ya vienen en Git). Con eso la API arrancó en un clon limpio (04/11/2026). Ver la sección siguiente: **no vienen completos en el repositorio** |

Sin servicios de pago: todo corre en local.

## Qué NO está en el repositorio

Un `git clone` **no basta para arrancar**: faltan los datos derivados. Esto es lo que hay y lo que no (según `git ls-files` y `.gitignore`):

| Archivo en `data/` | ¿En Git? | Cómo se obtiene |
|---|---|---|
| `modelo_predictivo_laliga.pkl` | Sí | Ya viene. Se puede regenerar con el notebook 02 |
| `la_liga_2014_2025_all_matches_final.csv` (datos crudos) | **No** (`data/*.csv` está ignorado) | **Hay que aportarlo.** Ver «Créditos» sobre su procedencia |
| Los 5 PDF del corpus: `Primera_y_Segunda_Division.pdf` (Normas de Competición 2026/27, publicadas por la RFEF), `reglamento laliga 2025-2026.pdf`, `Reglas de Juego 2026_27_paginas individuales.pdf` y los 2 de Wikipedia (`Primera División de España…`, `El Clásico…`) | **No** (`data/*.pdf` está ignorado: son de terceros y el repo es público) | **Hay que aportarlos**, cada uno desde su fuente. Ver `docs/datos.md` |
| `df_final_features.csv` y `team_matches.csv` | **No** | Los genera el notebook 01 |
| `2025-2026.csv` y `2026-2027.csv` (resultados y tiros recientes, modelo B) | **No** (`data/*.csv`) | **Hay que descargarlos a mano** de football-data.co.uk (ver «Modelo B, datos y registro») |
| `calendario_cache.json` | **No** | Lo crea la API sola al consultar football-data.org (necesita `FOOTBALL_DATA_KEY`) |
| `modelo_predictivo_laliga_b.pkl`, `modelo_b_params.json` y `registro_predicciones.jsonl` | Sí | Ya vienen. El registro es el historial de pronósticos: no lo edites a mano |
| `chroma_index/` (índice v1) y `chroma_index_v2/` | **No** (`data/chroma_index*/`) | Los generan los notebooks 03 y 05 |

El CSV crudo y los PDF **no se suben al repositorio**: el CSV tiene licencia incierta (ver «Créditos») y los PDF son documentos de terceros. Cada persona debe aportar su copia.

### Cómo regenerarlo, paso a paso

1. Crea el entorno e instala las dependencias. Los notebooks necesitan algunas librerías que no están en `backend/requirements.txt`:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt
   pip install jupyter matplotlib shap pdfplumber pymupdf langchain-text-splitters
   ```
2. Coloca en `data/` los 6 archivos que debes aportar: `la_liga_2014_2025_all_matches_final.csv` y los 5 PDF del corpus (fuentes en `docs/datos.md`).
3. Ejecuta los notebooks **en este orden**, cada uno con *Restart & Run All*, desde la carpeta `notebooks/` (usan rutas `../data/`):

   | Orden | Notebook | Lee | Escribe |
   |---|---|---|---|
   | 1 | `01_eda_partidos` | CSV crudo | `df_final_features.csv`, `team_matches.csv` |
   | 2 | `02_modelo_baseline` | `df_final_features.csv` | `modelo_predictivo_laliga.pkl` (sobrescribe el versionado) |
   | 3 | `03_rag_corpus` | 4 PDF que debes aportar (`reglamento laliga 2025-2026`, Reglas de Juego, los 2 de Wikipedia) | `chroma_index/` |
   | 4 | `05_corpus_v2` | `Primera_y_Segunda_Division.pdf` y Reglas de Juego (PDF que debes aportar) y `chroma_index/` | `chroma_index_v2/` |

   El 03 va antes del 05 porque el 05 rescata de `chroma_index/` los fragmentos ya limpios de Wikipedia. El `04_agente_conocimiento` es exploratorio y no hace falta.
4. Si Chroma da errores de base de datos, usa una carpeta nueva y no reutilices una corrupta.

**No verificado:** la regeneración completa (notebooks 01 → 02 → 03 → 05) no se ha comprobado de extremo a extremo. Tampoco se ha probado desde un entorno virtual
limpio (la lista de `pip install` de arriba es la esperada, no una comprobada), ni *Restart & Run All* dentro de Jupyter, ni con PDF y CSV aportados por otra persona.

## Modelo B, datos y registro

El modelo A usa xG y PPDA, que no existen después de mayo de 2025 y no se tocan. El **modelo B** usa solo goles, tiros y tiros a puerta, y así
puede actualizarse hasta ayer. Resultados y números honestos (B ≈ A, ninguno vence de forma demostrable a la frecuencia de clases): [`docs/modelo_b.md`](docs/modelo_b.md).

**De dónde sale cada dato**

| Dato | Fuente | Cómo entra |
|---|---|---|
| Partidos 2014 a mayo de 2025 | El CSV histórico (procedencia en «Créditos») | Archivo aportado en `data/` |
| Partidos de 2025/26 y 2026/27 (goles, tiros) | [football-data.co.uk](https://www.football-data.co.uk) (Primera División, `SP1.csv`) | **Descarga manual**: guarda 2025/26 como `data/2025-2026.csv` y 2026/27 como `data/2026-2027.csv`. No hay descarga automática (ver «Créditos») |
| Calendario, próximos partidos y resultados posteriores al último CSV | API de [football-data.org](https://www.football-data.org) (plan gratuito) | Token en `.env` como `FOOTBALL_DATA_KEY` (ver `.env.example`). Esos partidos llegan sin tiros |

**Caché y sin red.** (Probado en un clon limpio, sin token ni caché: `/proximos` responde `[]` con HTTP 200 y `/predict` usa los CSV.) La API guarda su respuesta en `data/calendario_cache.json` (vigente 6 h). Sin token o sin conexión se usa la última caché, así que
`/proximos` **solo funciona sin red si esa caché ya existe** (una vez que se ejecutó con token y red); sin caché devuelve una lista vacía. `/predict`, `/tabla` y
`/registro` siguen funcionando con los CSV.

**Actualizar.** `POST /actualizar` vuelve a leer la API y recalcula la forma con los partidos de ayer (y registra pronósticos nuevos). No reentrena el modelo.

**Registro de predicciones (`data/registro_predicciones.jsonl`).** Cada pronóstico se guarda **antes** del partido (próximos 10 días), una sola vez por partido, y solo se añaden líneas.
Cada línea trae `version_modelo` (huella del `.pkl`) y `commit_codigo` (commit del código; «desconocido» sin git). Cómo leerlo:
- `GET /registro` o la pestaña **Acierto**: aciertos, log-loss del modelo y de «sin saber nada» (la frecuencia de clases), y su diferencia ± 2 errores estándar.
  **Con menos de 30 partidos jugados no se puede concluir nada.** Solo cuenta la versión actual del modelo; `versiones` dice cuántos pronósticos hay de cada una.
- `python -m scripts.registro_predicciones resumen` (desde `backend/`) imprime lo mismo en la terminal.
- Para probar sin ensuciar el archivo versionado, arranca con `REGISTRAR_AL_ARRANCAR=0` y una copia de `data/` (`DATA_DIR=/ruta/copia`).

## Inicio rápido

### Modo Docker

```bash
ollama pull qwen2.5:7b          # una vez; Ollama debe estar corriendo en el anfitrión
docker compose up --build       # primera vez: unos 10 min y varios GB; después, segundos
```

- Interfaz: <http://localhost:8080>
- API y documentación OpenAPI: <http://localhost:8000/docs>
- Parar: `docker compose down` (no borra nada de `data/`).

Ollama **no** va en el contenedor: se usa el del anfitrión (GPU y modelos ya descargados). El contenedor lo alcanza en
`host.docker.internal:11434`; para otro modelo: `OLLAMA_MODEL=qwen2.5:3b docker compose up` (también existe `OLLAMA_BASE_URL`).

**Qué necesita `data/`** (el contenedor falla al arrancar, nombrando el archivo, si falta alguno de los obligatorios):

| Archivo | Obligatorio | Para qué |
|---|---|---|
| `modelo_predictivo_laliga.pkl`, `team_matches.csv` | Sí | Modelo A |
| `modelo_predictivo_laliga_b.pkl`, `la_liga_2014_2025_all_matches_final.csv` | Sí | Modelo B (por defecto) y su histórico |
| `chroma_index_v2/` | Sí | Índice del RAG |
| `2025-2026.csv`, `2026-2027.csv` | No | Resultados recientes del modelo B (si faltan, solo se usa el histórico) |
| `calendario_cache.json`, `registro_predicciones.jsonl` | No | Se **copian** al contenedor: `/registro` muestra lo ya guardado |

- `./data` se monta en **solo lectura** (`:ro`): el contenedor nunca escribe en tu carpeta. Lo que la API escribe (caché del calendario, registro) vive en una copia que se pierde al apagarlo.
- **El contenedor no registra pronósticos por defecto** (`REGISTRAR_AL_ARRANCAR=0` en el compose). El registro versionado se hace desde el anfitrión: `cd backend && python -m scripts.registro_predicciones registrar`.
- `FOOTBALL_DATA_KEY` se lee del `.env` del anfitrión (compose lo pasa al contenedor; no entra en la imagen). Sin ella `/proximos` usa la copia de `calendario_cache.json`, y si tampoco existe devuelve una lista vacía.
Más detalle, medidas y qué no se probó: [`docs/despliegue.md`](docs/despliegue.md).

### Modo desarrollo

```bash
cp .env.example .env            # opcional: DATA_DIR y OLLAMA_MODEL. El .env no se sube a Git

# Terminal 1: backend (desde la raíz del repo, con el entorno virtual activado)
cd backend
uvicorn app.main:app --port 8000

# Terminal 2: frontend
cd frontend
npm install
npm run dev                     # http://127.0.0.1:5173
```

Comprobación rápida de la API:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/preguntar -H 'content-type: application/json' \
  -d '{"pregunta": "¿Cuántos puntos se dan por una victoria?"}'
```

El backend carga el modelo, el CSV y el índice al arrancar y falla enseguida si falta alguno. Además, **al arrancar guarda en `data/registro_predicciones.jsonl` los pronósticos de los próximos 10 días**: si estás probando y no quieres ensuciar ese archivo versionado, arranca con `REGISTRAR_AL_ARRANCAR=0 uvicorn app.main:app` (o ponlo en `.env`). Con `0`, `POST /actualizar` y `python -m scripts.registro_predicciones registrar` siguen registrando. Otros comandos del frontend: `npm run build` y `npm run lint` (ver [`frontend/README.md`](frontend/README.md)).

### Pruebas

```bash
pip install -r backend/requirements-dev.txt
cd backend
python -m pytest tests -v
```

Usa `python -m pytest` y no `pytest` a secas: así `backend/` queda en el `sys.path` y `from app import ...` funciona. Hoy hay 18 pruebas (verificadas el 04/11/2026):
el desfase de `dias_desde_ultimo_partido` (ver `docs/datos.md`), el modelo B (sin fuga, nombres, duplicados de la API entre temporadas y aviso de fecha pasada),
el registro de predicciones y `REGISTRAR_AL_ARRANCAR`. Sin pytest también corren: `python -m tests.test_modelo_b`, `python -m tests.test_registro` y `python -m tests.test_arranque`.
Todas usan archivos temporales y calendario falso: no tocan la red ni el registro real. No hay pruebas automáticas
del orquestador ni del RAG; esos se miden con los scripts de `backend/scripts/`.

## Resultados

Cifras tomadas de [`docs/mediciones.md`](docs/mediciones.md), con la fecha de cada medición. Hardware: portátil con RTX 4050 de 6 GB, WSL2.

| Qué | Resultado | Fecha |
|---|---|---|
| Modelo: log-loss en prueba (1.140 partidos desde 2022-08-01) | **1,0513** frente a 1,0663 de la línea base | 02/11/2026 |
| Modelo: calibración (ECE medio / Brier multiclase) | 0,0816 / 0,6337 | 02/11/2026 |
| Recuperación: sección correcta entre los 8 fragmentos | 17/17 (preguntas de desarrollo) | 01/11/2026 |
| RAG: hecho clave en la respuesta, sin RAG frente a con RAG | 4/11 frente a **9/11** (mismo LLM, mismas 11 preguntas) | 02/11/2026 |
| RAG tras el ajuste del léxico (desarrollo, 11 preguntas) | frase clave 11/11, respuesta 10/11 | 02/11/2026 |
| RAG **held-out** (10 preguntas, ejecutado una vez) | frase clave **9/10**, respuesta **9/10** | 02/11/2026 |
| Orquestador, desarrollo (27 casos, reglas ajustadas viendo fallos) | 27/27 | 02/11/2026 |
| Orquestador **held-out** (12 casos, congelado, ejecutado una vez) | **12/12** | 02/11/2026 |
| LLM: 7B frente a 3B (11 preguntas, `/chat`) | 9/11 y 2.853 ms frente a 7/11 y 1.347 ms | 01/11/2026 |
| Latencia de `/preguntar` | predicción 299 ms; conocimiento 4.018 ms (una medición) | 02/11/2026 |

Cómo leerlas: los conjuntos son pequeños (10 a 27 casos) y los redactó la misma persona que ajustó el sistema. Con 9/10 el intervalo de Wilson al 95 %
es de unos 60 a 98 %. Un 100 % del orquestador no garantiza que generalice.

## Limitaciones

- **Datos hasta el 2025-05-25.** No se actualizan (el origen probable prohíbe el rastreo; ver `docs/datos.md`). Los pronósticos usan la forma de los
  últimos 5 partidos a esa fecha y no reflejan fichajes, lesiones ni resultados posteriores. Sin fecha, la predicción usa el último dato + 7 días (2025-06-01).
  Equipos que no jugaron en Primera en 2024/25 (Cádiz, Almería, Granada) arrastran la forma de temporadas anteriores.
- **El modelo aporta poco y está descalibrado.** Mejora la línea base en 0,015 de log-loss. Sobreestima el empate (predice 0,34, ocurre 0,26) y subestima la
  victoria local (predice 0,34, ocurre 0,45). Se propuso calibrar con Platt, pero no se aplicó porque exige reentrenar y tocar el `.pkl`. Tómense las
  probabilidades como orientativas.
- **Latencia del LLM de 7B.** El objetivo es responder en menos de 5 s. De media se cumple, pero el 7B roza o supera los 5 s en algunas preguntas
  (conmoción cerebral y desempate: 4,9 a 6,0 s). La primera pregunta tras arrancar paga la carga en frío: el calentamiento del 7B tardó 18,2 s y la
  primera búsqueda 4,4 s frente a 0,14 s en caliente. El 3B es unas 2 veces más rápido pero acierta menos y a veces contesta solo con citas.
- **Fallos conocidos del RAG.** «¿Cuántos suplentes…?» responde «cinco» (pregunta ambigua; fallo de generación). En el held-out, la duración máxima de la prórroga
  no llegó a los fragmentos y el sistema contestó «No encontré esa información» (abstención correcta, no alucinación). La métrica de «hecho clave» es generosa.
- **El orquestador solo entiende su vocabulario.** Lo que no reconoce cae en `aclarar` o `fuera_de_alcance`. Por ejemplo, «¿Cuántos goles marcó el Barça al Madrid?» se declina.
  No extrae la fecha del texto, solo del campo opcional `fecha`. Ver `docs/diseno_orquestador.md`.
- **Alcance de la liga y del corpus.** Solo Primera División; los artículos de Segunda se excluyen salvo que la pregunta diga «segunda». El corpus es de la
  temporada 2026/27, y no contiene datos como quién ganó un clásico concreto.
- **Despliegue.** Solo probado con Docker Desktop sobre WSL2 y amd64. La interfaz se probó contra el backend real pero no en un navegador real. El LLM de despliegue final sigue pendiente.
- **Dependencia de los PDF.** Reproducir el índice exige aportar el CSV y los 5 PDF del corpus, que no están en Git.

## Estructura del repositorio

```text
.
├── backend/
│   ├── app/                  FastAPI y agentes: main, orquestador, chat (RAG + LLM), retrieval, prediction
│   ├── scripts/              evaluaciones (recuperación, respuestas, orquestador, calibración, held-out)
│   │   ├── datos_evaluacion/   preguntas del held-out de RAG
│   │   └── datos_orquestador/  casos dev y heldout del router
│   ├── tests/                pruebas con pytest
│   ├── requirements.txt      dependencias de ejecución
│   ├── requirements-dev.txt  añade pytest
│   └── Dockerfile
├── frontend/                 React + Vite: chat y panel de predicción (nginx en Docker)
├── notebooks/                01 EDA y features, 02 modelo, 03 y 05 corpus RAG, 04 exploración
├── data/                     datos (ver «Qué NO está en el repositorio»)
├── docs/                     arquitectura, datos, mediciones, despliegue, orquestador, frontend y figuras
├── docker-compose.yml
├── .env.example
└── CLAUDE.md                 decisiones del proyecto y convenciones
```

## Documentación

[`arquitectura`](docs/arquitectura.md) · [`mediciones`](docs/mediciones.md) · [`datos`](docs/datos.md) · [`despliegue`](docs/despliegue.md) · [`orquestador`](docs/diseno_orquestador.md) · [`frontend`](docs/frontend.md)

## Créditos y licencias de datos

- **Partidos (`la_liga_2014_2025_all_matches_final.csv`).** Procedencia **inferida, no confirmada**: por su esquema (`match_id`, `xg`, `ppda`, `xpts`, `deep`) parece un
  export de [Understat](https://understat.com). El archivo no trae metadatos de origen, así que **su licencia es incierta** y por eso no se redistribuye. Debe verificarse la
  procedencia exacta antes de citarla. Respetamos el `robots.txt` de Understat: no se hace ningún rastreo.
- **Reglas de Juego 2026/27.** Texto del IFAB (International Football Association Board), en español, descargable en <https://theifab.com/documents>. Se usa la variante
  **«páginas individuales»** (`Reglas de Juego 2026_27_paginas individuales.pdf`): la variante «páginas dobles» tiene otra numeración y las citas de página del sistema dejarían de coincidir.
  Los derechos pertenecen al IFAB.
- **Normas de Competición Primera y Segunda División 2026/27.** «Normas Reguladoras y Bases de Competición de los Campeonatos Nacionales de Liga de Primera y Segunda División,
  temporada 2026-2027», publicadas por la RFEF (LaLiga organiza la competición en coordinación con ella): <https://rfef.es/sites/default/files/2026-06/1._CNL_Primera_y_Segunda_Division.pdf>.
  Se guarda como `data/Primera_y_Segunda_Division.pdf`. Los derechos pertenecen a sus titulares.
- **Reglamento 2025/26** (`reglamento laliga 2025-2026.pdf`, 41 páginas, portada «REGLAMENTO · TEMPORADA 2025/26»). El archivo no indica quién lo emite; su origen está por confirmar. Los derechos pertenecen a sus titulares.
- **Wikipedia** («Primera División de España» y «El Clásico»), exportados a PDF el 10/08/2026 (revisiones 174757811 y 174777709 de es.wikipedia.org). Texto bajo licencia
  [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.es), con atribución a sus autores; los PDF no traen el pie de licencia, así que la versión no consta en el archivo (Wikimedia usa hoy la 4.0).
- **football-data.co.uk** (CSV recientes de Primera División, modelo B). Lo único que sabemos de sus condiciones: su `robots.txt` veta a los rastreadores de IA, por eso los CSV se
  descargan **a mano** y ningún código del proyecto los baja. No revisamos aquí sus términos completos: consúltalos antes de redistribuir los archivos (por eso no están en Git).
- **football-data.org** (calendario y resultados recientes por API). Lo único que sabemos: se usa el plan gratuito con token personal (`FOOTBALL_DATA_KEY`, nunca en el repo) y
  hasta 10 peticiones por minuto, y por eso hay caché. No revisamos aquí sus términos completos.
- **Modelo de embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers). **LLM:** `qwen2.5` servido localmente por Ollama.

Este proyecto es académico. No tiene afiliación con LaLiga, el IFAB, Understat, football-data.co.uk ni football-data.org.
