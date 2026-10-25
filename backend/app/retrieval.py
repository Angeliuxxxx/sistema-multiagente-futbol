"""Recuperación híbrida (embeddings + BM25 + RRF) con cupos por fuente.

Es la versión de producción de lo que se midió en notebooks/05_corpus_v2.ipynb (Hit@8 = 16/17 con 17 preguntas).
El backend NO vuelve a leer los PDFs: lee el índice que dejó el notebook 05 en data/chroma_index_v2.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chromadb
import snowballstemmer
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# Misma convención que prediction.py: por defecto <repo>/data, con DATA_DIR para sobreescribirlo.
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
RUTA_INDICE = DATA_DIR / "chroma_index_v2"
COLECCION = "corpus_laliga_v2"
# Debe ser EXACTAMENTE el modelo con el que se indexó: si cambia, los vectores de consulta y los del índice no se parecen.
MODELO_EMBEDDINGS = "paraphrase-multilingual-MiniLM-L12-v2"

# (documentos de la fuente, cuántos fragmentos aporta). Cada fuente aporta sus mejores N para que una fuente grande o
# ruidosa (Reglas de Juego, 678 chunks) no ocupe todo el contexto que verá el LLM.
CUPOS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("normas_competicion",), 3),
    (("reglas_juego",), 3),
    (("primera_division", "clasico"), 2),
)

_stemmer = snowballstemmer.stemmer("spanish")
# Palabras vacías sin acentos (ya se los quitamos al tokenizar): no distinguen un artículo de otro y diluyen BM25.
_STOP = set("de la el en y a los las del un una por con para que se es al lo como su cual cuales cuantos cuantas "
            "cuanto cuando donde qui quien".split())


@dataclass(frozen=True)
class Fragmento:
    """Un trozo del corpus con lo necesario para citarlo (documento y página) en la respuesta."""
    texto: str
    documento: str
    seccion: str
    pagina: int


@dataclass
class Indice:
    col: chromadb.Collection
    modelo: SentenceTransformer
    chunks: list[dict]  # la posición i corresponde al id "c{i}" de Chroma
    bm25: dict[tuple[str, ...], tuple[list[int], BM25Okapi]]  # un índice BM25 por fuente, creado la primera vez


def tokenizar(t: str) -> list[str]:
    # Sin acentos y en minúsculas, para que "sustitución" y "sustituciones" compartan raíz tras el stemmer.
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return [_stemmer.stemWord(w) for w in re.findall(r"[a-z0-9]+", t) if w not in _STOP]


@lru_cache(maxsize=1)
def cargar_indice() -> Indice:
    """Carga Chroma + el modelo una sola vez (tarda segundos; no debe pasar en cada petición, RNF < 5 s)."""
    if not RUTA_INDICE.exists():
        raise FileNotFoundError(f"No existe {RUTA_INDICE}. Genera el índice ejecutando notebooks/05_corpus_v2.ipynb.")
    col = chromadb.PersistentClient(path=str(RUTA_INDICE)).get_collection(COLECCION)
    datos = col.get(include=["documents", "metadatas"])
    orden = sorted(range(len(datos["ids"])), key=lambda j: int(datos["ids"][j][1:]))
    # BM25 devuelve posiciones y Chroma devuelve ids "c{i}": solo se pueden cruzar si los ids van de c0 a c{n-1}.
    assert [int(datos["ids"][j][1:]) for j in orden] == list(range(len(orden))), "ids de Chroma no contiguos"
    chunks = [dict(texto=datos["documents"][j], **datos["metadatas"][j]) for j in orden]
    ind = Indice(col=col, modelo=SentenceTransformer(MODELO_EMBEDDINGS), chunks=chunks, bm25={})
    for documentos, _ in CUPOS:   # los 3 índices BM25 se construyen ahora, no en la primera pregunta (costaba ~3 s)
        _bm25_de(ind, documentos)
    return ind


def _bm25_de(ind: Indice, documentos: tuple[str, ...]) -> tuple[list[int], BM25Okapi]:
    # IDF por fuente: "qué tan rara es una palabra" se mide dentro de la fuente que se está consultando.
    if documentos not in ind.bm25:
        idx = [i for i, c in enumerate(ind.chunks) if c["documento"] in documentos]
        ind.bm25[documentos] = (idx, BM25Okapi([tokenizar(ind.chunks[i]["texto"]) for i in idx]))
    return ind.bm25[documentos]


def _hibrido(ind: Indice, pregunta: str, emb: list[float], k: int, documentos: tuple[str, ...],
             candidatos: int = 20, k_rrf: int = 60) -> list[int]:
    """Devuelve las posiciones de los k mejores chunks de una fuente, fusionando embeddings y BM25 con RRF."""
    r = ind.col.query(query_embeddings=[emb], n_results=candidatos, where={"documento": {"$in": list(documentos)}})
    denso = [int(i[1:]) for i in r["ids"][0]]                      # "c123" -> 123

    idx, bm = _bm25_de(ind, documentos)
    sc = bm.get_scores(tokenizar(pregunta))
    lexico = [idx[j] for j in sorted((j for j in range(len(idx)) if sc[j] > 0), key=lambda j: -sc[j])][:candidatos]

    # RRF: cada ranking aporta 1/(k_rrf + posición). Suma posiciones, no puntajes (están en escalas distintas).
    fusion: dict[int, float] = {}
    for ranking in (denso, lexico):
        for pos, i in enumerate(ranking, start=1):
            fusion[i] = fusion.get(i, 0.0) + 1.0 / (k_rrf + pos)
    return sorted(fusion, key=fusion.get, reverse=True)[:k]


def buscar(pregunta: str) -> list[Fragmento]:
    """Los fragmentos del corpus que mejor responden la pregunta: 3 de Normas, 3 de Reglas y 2 de Wikipedia."""
    ind = cargar_indice()
    # Se vectoriza la pregunta UNA vez y se reutiliza en las tres fuentes (hacerlo tres veces triplicaría la latencia).
    emb = ind.modelo.encode([pregunta])[0].tolist()
    salida: list[Fragmento] = []
    for documentos, cupo in CUPOS:
        for i in _hibrido(ind, pregunta, emb, cupo, documentos):
            c = ind.chunks[i]
            salida.append(Fragmento(texto=c["texto"], documento=c["documento"], seccion=c["seccion"],
                                    pagina=int(c["pagina"])))
    return salida
