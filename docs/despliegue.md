# Despliegue con Docker

## Arranque

```bash
docker compose up --build        # primera vez: ~10 min y varios GB; después, segundos
```

- Interfaz: http://localhost:8080 · API y OpenAPI: http://localhost:8000/docs
- Requisitos: Docker (Compose v2), **Ollama corriendo en el anfitrión** con el modelo de `.env` (`OLLAMA_MODEL`), y la carpeta `data/`
  con los archivos obligatorios (modelos A y B, `team_matches.csv`, el CSV histórico y `chroma_index_v2/`; lista completa en el README,
  «Modo Docker»). Los `.pkl` del modelo A y B están en Git; los CSV y el índice no (se regeneran o se descargan, ver `docs/datos.md`).
- Parar: `docker compose down`. No borra nada de `data/`.

## Arquitectura

| Servicio | Imagen | Qué hace |
|---|---|---|
| `backend` | python:3.14-slim + torch CPU | FastAPI, XGBoost, Chroma, embeddings. `./data` montado en `/data` **solo lectura**. |
| `frontend` | nginx:alpine (build con Node) | Sirve el build de Vite y reenvía `/api/*` al backend. |
| Ollama | **fuera de Docker** | El LLM usa la GPU del anfitrión y sus modelos ya descargados. |

Decisiones y porqué:
- **Datos por volumen, no en la imagen:** no están en Git, pesan y deben poder actualizarse sin reconstruir.
- **Copia, no enlace, de lo que se escribe** (`docker-entrypoint.sh`): el índice de Chroma (~14 MB, abre su SQLite en escritura), `calendario_cache.json` y `registro_predicciones.jsonl`. Lo demás se enlaza. Así `./data` queda intacto.
- **Sin registro de pronósticos por defecto** (`REGISTRAR_AL_ARRANCAR=0`): la copia del registro se pierde al apagar; el registro versionado se hace desde el anfitrión.
- **torch solo CPU:** la rueda por defecto trae CUDA (GBs); el contenedor no usa GPU (los embeddings tardan ~70 ms en CPU).
- **Modelo de embeddings horneado en la imagen** (`HF_HUB_OFFLINE=1`): el arranque no necesita internet ni usa tu caché de Hugging Face.
- **Versiones fijadas** en `backend/constraints-docker.txt` (las del venv): un pickle de XGBoost/sklearn o un Chroma se rompen con versiones distintas.
- **nginx como proxy (`/api`)** en vez de abrir CORS: el navegador ve un solo origen. El backend solo permite `localhost:5173` (Vite en desarrollo).

## Ollama desde el contenedor

Se verificó (1/11/2026) en este equipo: Docker Desktop (WSL2), Ollama escuchando en `127.0.0.1:11434`, y un contenedor lo alcanza
con `http://host.docker.internal:11434` **sin cambiar nada**. El compose usa esa URL por defecto (`OLLAMA_BASE_URL` la sobreescribe).

Si en otra máquina falla (Docker Engine nativo en Linux): Ollama debe escuchar en una interfaz alcanzable desde el puente de Docker.
Con systemd: `sudo systemctl edit ollama` y añadir `Environment="OLLAMA_HOST=0.0.0.0"`, luego `sudo systemctl restart ollama`.
Ojo: `0.0.0.0` expone Ollama a tu red; usa el firewall o enlaza solo a la IP del puente `docker0` (172.17.0.1). `extra_hosts: host-gateway`
ya está en el compose para que el nombre se resuelva.

## Mediciones (6/11/2026, WSL2, 7,5 GB RAM, Docker 29.9.2, Ollama con GPU en el anfitrión, modelo B por defecto)

| Medida | Valor |
|---|---|
| `docker compose up --build` con capas en caché | 51 s hasta `healthy` el frontend (incluye crear contenedores) |
| Reinicio del backend hasta `healthy` | 36 s (≈ 17 s de «startup complete» y el resto, entrypoint y primer healthcheck que pasa) |
| Imagen backend | 4,33 GB |
| RAM backend en reposo | 1,13 GiB (frontend 13,7 MiB) |
| `/preguntar` conocimiento, primera llamada (Ollama carga qwen2.5:7b en frío) | 50 s |
| `/preguntar` conocimiento, modelo ya caliente | 3,3 s (una muestra) |
| `/preguntar` predicción | 0,1 s (una muestra) |

Sin construcción desde cero en esta prueba: la primera construcción (9 min 43 s el 1/11/2026) y la imagen del frontend (74 MB) son de entonces y no se repitieron.
Healthcheck: el actual (`start_period` 20 s, 12 reintentos de 10 s) basta, porque el backend tarda ~30 s en estar sano; no se tocó.
Lectura honesta: la primera pregunta de conocimiento tras encender Ollama supera de largo los 5 s del RNF (carga del modelo en la GPU); caliente, 3,3 s. Son muestras sueltas, no una medición de latencia: para eso usar `backend/scripts/evaluar_respuestas.py`.

## Qué se probó el 6/11/2026
`up --build` hasta `healthy`; `/health`; `/predict` con modelo B y A; `/registro` (10 pronósticos de la jornada 12, copia); `/preguntar` por las dos rutas;
`/proximos` con clave (refrescó la caché dentro del contenedor), sin clave con caché y sin clave sin caché (`[]`, HTTP 200); `/api/health`, `/api/registro` y la página por nginx;
y un `docker run` sin el `.pkl` del modelo B, que falla nombrando el archivo.

## Qué no se probó
- La interfaz en un navegador real (solo `curl` a través de nginx: la página responde 200, pero no se hizo clic en nada).
- Docker Engine nativo en Linux y la ruta `OLLAMA_HOST=0.0.0.0` (solo Docker Desktop/WSL2).
- Otra arquitectura (ARM/Mac): imagen construida solo para amd64.
- Construcción desde cero tras este cambio y `git clone` limpio en modo Docker (la imagen se reutilizó de caché y `data/` es la del repo local).
- Arranque con `data/` incompleta en los archivos opcionales (se probó sin caché de calendario, no sin los CSV recientes).
- Carga concurrente y latencia sostenida.
