"""Precisión por ruta y matriz de confusión del router del orquestador (solo reglas, sin servidor ni LLM).

Ejecutar desde backend/:  python -m scripts.evaluar_orquestador [dev|heldout]
Se itera SOLO con dev. heldout se corre una vez al final: si se retocan reglas viendo sus fallos, deja de ser heldout.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from app.orquestador import enrutar

RUTAS = ["prediccion", "conocimiento", "aclarar", "fuera_de_alcance"]
DATOS = Path(__file__).parent / "datos_orquestador"


def main(conjunto: str) -> None:
    casos = json.loads((DATOS / f"{conjunto}.json").read_text(encoding="utf-8"))
    conf: Counter = Counter()
    fallos = []
    for c in casos:
        d = enrutar(c["pregunta"])
        conf[(c["ruta_esperada"], d.ruta)] += 1
        if d.ruta != c["ruta_esperada"]:
            fallos.append((c, d))

    print(f"== {conjunto}: {len(casos) - len(fallos)}/{len(casos)} ==\n")
    print("Precisión por ruta (aciertos / casos esperados):")
    for r in RUTAS:
        total = sum(conf[(r, p)] for p in RUTAS)
        print(f"  {r:<18} {conf[(r, r)]}/{total}")
    print("\nMatriz de confusión (filas = esperada, columnas = predicha):")
    print(f"  {'':<18}" + "".join(f"{p[:10]:>12}" for p in RUTAS))
    for r in RUTAS:
        print(f"  {r:<18}" + "".join(f"{conf[(r, p)]:>12}" for p in RUTAS))
    for c, d in fallos:
        print(f"\n✘ {c['pregunta']}\n  esperada={c['ruta_esperada']}  obtenida={d.ruta}  equipos={d.equipos}\n  motivo: {d.motivo}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
