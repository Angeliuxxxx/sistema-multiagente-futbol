#!/bin/sh
# Prepara un DATA_DIR de trabajo a partir de /data (montado en SOLO LECTURA).
# Por qué: Chroma abre su SQLite en modo escritura aunque solo consultemos; con el índice del anfitrión montado
# directamente podría modificarlo o fallar. Lo que la API solo LEE se enlaza; lo que puede ESCRIBIR se copia.
set -eu

# 1) Obligatorios: sin ellos el lifespan de la API falla al arrancar (modelo A, modelo B y su tabla histórica, RAG).
#    Comprobarlos aquí da un mensaje que nombra el archivo, en vez de un FileNotFoundError dentro de uvicorn.
for f in modelo_predictivo_laliga.pkl team_matches.csv \
         modelo_predictivo_laliga_b.pkl la_liga_2014_2025_all_matches_final.csv \
         chroma_index_v2; do
  [ -e "$DATA_SRC/$f" ] || { echo "ERROR: falta $DATA_SRC/$f (monta ./data en /data; ver docs/despliegue.md)" >&2; exit 1; }
done
mkdir -p "$DATA_DIR"

# 2) Solo lectura -> enlace simbólico (no ocupa espacio y el original no se toca).
for f in modelo_predictivo_laliga.pkl team_matches.csv \
         modelo_predictivo_laliga_b.pkl la_liga_2014_2025_all_matches_final.csv; do
  ln -sf "$DATA_SRC/$f" "$DATA_DIR/$f"
done

# 3) Opcionales de solo lectura: CSV recientes del modelo B. Si faltan, resultados.py los omite y usa el histórico.
for f in 2025-2026.csv 2026-2027.csv; do
  [ -e "$DATA_SRC/$f" ] && ln -sf "$DATA_SRC/$f" "$DATA_DIR/$f"
done

# 4) Opcionales que la API puede ESCRIBIR (caché del calendario, registro de pronósticos): se COPIAN, porque /data es
#    de solo lectura. Así /registro muestra lo ya guardado sin escribir nada en la carpeta del anfitrión; lo nuevo se
#    pierde al apagar el contenedor. `cp -p` conserva la fecha: si no, una caché vieja parecería recién descargada.
for f in calendario_cache.json registro_predicciones.jsonl; do
  [ -e "$DATA_SRC/$f" ] && cp -p "$DATA_SRC/$f" "$DATA_DIR/$f"
done

# 5) Índice de Chroma: copia (se abre en modo escritura).
rm -rf "$DATA_DIR/chroma_index_v2"
cp -r "$DATA_SRC/chroma_index_v2" "$DATA_DIR/chroma_index_v2"
exec "$@"
