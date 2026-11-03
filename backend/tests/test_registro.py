"""Pruebas del registro de predicciones. Ejecutar desde backend/:  python -m tests.test_registro

Se simulan el calendario y el modelo (no se toca el registro real ni la red) para comprobar las GARANTÍAS del registro.
"""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app import calendario, prediction_b, registro

AHORA = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731


def _falso(proximos: list[dict], terminados: list[dict] | None = None):
    """Prepara registro con un archivo temporal, un calendario falso y un modelo que siempre da 50/30/20."""
    registro.RUTA = Path(tempfile.mkdtemp()) / "registro.jsonl"
    calendario.proximos = lambda n=None: proximos
    calendario.partidos_api = lambda forzar=False: terminados or []
    prediction_b.predecir_partido_b = lambda l, v, f=None: {
        "datos_hasta": "2026-11-04", "probabilidades": {"victoria_local": 0.5, "empate": 0.3, "victoria_visitante": 0.2}}
    registro._version_modelo = lambda: "test"


def _p(local, visitante, dias, jornada=12):
    return {"fecha": iso(AHORA + timedelta(days=dias)), "local": local, "visitante": visitante, "jornada": jornada}


def test_no_duplica_y_solo_añade() -> None:
    _falso([_p("A", "B", 2), _p("C", "D", 3)])
    assert len(registro.registrar(AHORA)) == 2
    antes = registro.RUTA.read_text()
    assert registro.registrar(AHORA + timedelta(hours=1)) == [], "un partido ya registrado no se vuelve a registrar"
    assert registro.RUTA.read_text() == antes, "el archivo no debe cambiar si no hay partidos nuevos"
    _falso([_p("A", "B", 2), _p("E", "F", 4)])  # archivo nuevo: ahora sí
    registro.registrar(AHORA)
    antes = registro.RUTA.read_text()
    calendario.proximos = lambda n=None: [_p("A", "B", 2), _p("E", "F", 4), _p("G", "H", 5)]
    registro.registrar(AHORA)
    assert registro.RUTA.read_text().startswith(antes), "solo se añade al final; lo anterior queda idéntico"


def test_rechaza_partido_ya_empezado_y_muy_lejano() -> None:
    _falso([_p("A", "B", -0.01), _p("C", "D", 0), _p("E", "F", 30), _p("G", "H", 1)])
    nuevos = registro.registrar(AHORA)
    assert [n["local"] for n in nuevos] == ["G"], "ni empezados, ni a más de 10 días"


def test_puntuacion() -> None:
    fin = [{"status": "FINISHED", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}, "score": {"fullTime": {"home": 2, "away": 0}}},
           {"status": "FINISHED", "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"}, "score": {"fullTime": {"home": 0, "away": 1}}}]
    _falso([_p("A", "B", 1), _p("C", "D", 1), _p("E", "F", 1)], fin)
    registro.registrar(AHORA)
    f = {r["local"]: r for r in registro.puntuar()}
    assert f["A"]["acierto"] is True and np.isclose(f["A"]["log_loss"], -np.log(0.5))
    assert f["C"]["acierto"] is False and np.isclose(f["C"]["log_loss"], -np.log(0.2))
    assert np.isclose(f["A"]["brier"], (0.5 - 1) ** 2 + 0.3**2 + 0.2**2), "brier de una victoria local con 0.5"
    assert f["E"]["resultado"] is None and "acierto" not in f["E"], "sin resultado no hay puntaje"
    r = registro.resumen()
    assert (r["registrados"], r["jugados"], r["aciertos"], r["concluyente"]) == (3, 2, 1, False)


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
