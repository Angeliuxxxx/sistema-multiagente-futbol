"""Registro de predicciones por línea de comandos (desde backend/):

  python -m scripts.registro_predicciones registrar   # guarda los pronósticos de los próximos 10 días
  python -m scripts.registro_predicciones resumen     # puntúa los partidos ya jugados
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import prediction_b, registro  # noqa: E402

if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "resumen"
    if orden == "registrar":
        prediction_b.refrescar()  # primero los datos de ayer: el pronóstico debe usar lo más reciente
        nuevos = registro.registrar()
        for n in nuevos:
            p = n["probabilidades"]
            print(f"{n['inicio_partido'][:10]} J{n['jornada']} {n['local']} - {n['visitante']}: "
                  f"L {p['victoria_local']:.0%} E {p['empate']:.0%} V {p['victoria_visitante']:.0%}")
        print(f"{len(nuevos)} pronósticos nuevos registrados en {registro.RUTA}")
    else:
        print(json.dumps(registro.resumen(), indent=2, ensure_ascii=False))
