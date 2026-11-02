#!/bin/sh
# Prepara un DATA_DIR de trabajo a partir de /data (montado en SOLO LECTURA).
# Por qué: Chroma abre su SQLite en modo escritura aunque solo consultemos; con el índice del anfitrión montado
# directamente podría modificarlo o fallar. Copiamos solo el índice (~14 MB) y enlazamos lo demás (solo se lee).
set -eu
for f in modelo_predictivo_laliga.pkl team_matches.csv chroma_index_v2; do
  [ -e "$DATA_SRC/$f" ] || { echo "ERROR: falta $DATA_SRC/$f (monta ./data en /data; ver docs/despliegue.md)" >&2; exit 1; }
done
mkdir -p "$DATA_DIR"
ln -sf "$DATA_SRC/modelo_predictivo_laliga.pkl" "$DATA_DIR/modelo_predictivo_laliga.pkl"
ln -sf "$DATA_SRC/team_matches.csv" "$DATA_DIR/team_matches.csv"
rm -rf "$DATA_DIR/chroma_index_v2"
cp -r "$DATA_SRC/chroma_index_v2" "$DATA_DIR/chroma_index_v2"
exec "$@"
