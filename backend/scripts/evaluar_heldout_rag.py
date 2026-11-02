"""Held-out de RAG: 10 preguntas sobre artículos que NO se usaron para afinar (datos_evaluacion/heldout_rag.json).

SE EJECUTA UNA SOLA VEZ, al final, y no se usa para decidir nada ni para retocar el sistema después.
Mide lo mismo que en desarrollo: (a) frase clave en los 8 fragmentos (+ sección correcta), (b) hecho clave en la respuesta del LLM.
Ejecutar desde backend/:  python -m scripts.evaluar_heldout_rag
"""
import json
from pathlib import Path

from app.chat import responder_conocimiento
from app.retrieval import buscar
from scripts.evaluar_respuestas import _contiene

RUTA = Path(__file__).parent / "datos_evaluacion" / "heldout_rag.json"


def main() -> None:
    casos = json.loads(RUTA.read_text(encoding="utf-8"))["casos"]
    n_f = n_r = 0
    print("| Pregunta | Frase en fragmentos | Hecho en respuesta | ms |\n|---|---|---|---|")
    detalle = []
    for c in casos:
        frags = buscar(c["pregunta"])
        pos = next((i for i, f in enumerate(frags, 1) if c["seccion"] in f.seccion
                    and c["frase_clave"] in " ".join(f.texto.split())), None)
        r = responder_conocimiento(c["pregunta"])
        ok = any(_contiene(r.respuesta, h) for h in c["hechos"])
        n_f += pos is not None
        n_r += ok
        print(f"| {c['pregunta']} | {'✔ pos ' + str(pos) if pos else '✘'} | {'✔' if ok else '✘'} | {r.ms_busqueda + r.ms_llm} |")
        detalle.append(f"- {c['pregunta']}\n  {r.respuesta}")
    print(f"\nFrase clave en fragmentos: {n_f}/{len(casos)} | hecho en respuesta: {n_r}/{len(casos)}\n")
    print("\n".join(detalle))


if __name__ == "__main__":
    main()
