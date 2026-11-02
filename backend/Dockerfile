# Misma versión de Python que el venv de desarrollo (3.14): los pickles y Chroma se probaron con ella.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# 1) torch SOLO CPU: la rueda por defecto trae CUDA (~2-3 GB extra) y en el contenedor no hay GPU para el
#    modelo de embeddings (MiniLM, 118 M parámetros, ~70 ms por consulta en CPU). La GPU la usa Ollama, fuera del contenedor.
COPY constraints-docker.txt requirements.txt ./
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt -c constraints-docker.txt

# 2) El modelo de embeddings se descarga al CONSTRUIR la imagen: el arranque no depende de internet
#    ni toca la caché de modelos del anfitrión. Capa propia: solo se repite si cambia el modelo.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1

# 3) Código al final: es lo que más cambia y no invalida las capas pesadas de arriba.
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN useradd --create-home appuser && chmod +x /usr/local/bin/docker-entrypoint.sh
USER appuser

# /data (montado solo lectura desde ./data) y DATA_DIR de trabajo: ver docker-entrypoint.sh
ENV DATA_SRC=/data DATA_DIR=/tmp/data
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
