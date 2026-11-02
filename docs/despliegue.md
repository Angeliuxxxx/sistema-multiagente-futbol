# Despliegue con Docker

## Arranque

```bash
docker compose up --build        # primera vez: ~10 min y varios GB; después, segundos
```

- Interfaz: http://localhost:8080 · API y OpenAPI: http://localhost:8000/docs
- Requisitos: Docker (Compose v2), **Ollama corriendo en el anfitrión** con el modelo de `.env` (`OLLAMA_MODEL`), y la carpeta `data/`
  con `modelo_predictivo_laliga.pkl`, `team_matches.csv` y `chroma_index_v2/` (no están en Git: se regeneran con los notebooks).
- Parar: `docker compose down`. No borra nada de `data/`.

## Arquitectura

| Servicio | Imagen | Qué hace |
|---|---|---|
| `backend` | python:3.14-slim + torch CPU | FastAPI, XGBoost, Chroma, embeddings. `./data` montado en `/data` **solo lectura**. |
| `frontend` | nginx:alpine (build con Node) | Sirve el build de Vite y reenvía `/api/*` al backend. |
| Ollama | **fuera de Docker** | El LLM usa la GPU del anfitrión y sus modelos ya descargados. |

Decisiones y porqué:
- **Datos por volumen, no en la imagen:** no están en Git, pesan y deben poder actualizarse sin reconstruir.
- **Copia del índice de Chroma al arrancar** (`docker-entrypoint.sh`, ~14 MB): Chroma abre su SQLite en escritura; así el índice del anfitrión nunca se toca.
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

## Mediciones (1/11/2026, WSL2, 12 CPU, 7,5 GB RAM, Ollama con GPU en el anfitrión)

| Medida | Valor |
|---|---|
| Primera construcción (sin caché) | 9 min 43 s (torch ≈ 5,6 min, imagen final 2,5 min) |
| Imagen backend | 4,33 GB (torch CPU + dependencias ≈ 2,4 GB; modelo de embeddings 0,48 GB) |
| Imagen frontend | 74 MB |
| Arranque hasta `healthy` | 22 s |
| RAM backend en reposo | 1,65 GB |
| `/predict` | 14 ms |
| `/chat` (modelo ya caliente) | 2,4 s y 6,5 s en dos preguntas |

Lectura honesta: la segunda pregunta superó los 5 s del RNF; el tiempo lo domina la generación del LLM (qwen2.5:7b con 6 GB de VRAM),
no Docker. Son dos muestras, no una medición de latencia: para eso usar `backend/scripts/evaluar_respuestas.py`.

## Qué no se probó
- Docker Engine nativo en Linux (solo Docker Desktop/WSL2) ni la ruta `OLLAMA_HOST=0.0.0.0`.
- Otra arquitectura (ARM/Mac): imagen construida solo para amd64.
- Reconstrucción con caché parcial y `git clone` limpio (la `data/` se tomó del repo local).
- Uso desde el navegador (se probó la página y la API por `curl` a través de nginx, no la interfaz con clics).
- Carga concurrente y latencia sostenida.
