"""Pruebas del registro de predicciones. Ejecutar desde backend/:  python -m tests.test_registro

Se simulan el calendario y el modelo (no se toca el registro real ni la red) para comprobar las GARANTÍAS del registro.
"""
import json
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app import calendario, prediction_b, registro

AHORA = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731


@contextmanager
def _falso(proximos: list[dict], terminados: list[dict] | None = None):
    """Archivo temporal, calendario falso y un modelo que siempre da 50/30/20. Al salir (aunque la prueba falle) se
    restauran las funciones reemplazadas: si no, contaminarían a cualquier otro módulo que corra en el mismo proceso."""
    guardado = (registro.RUTA, calendario.proximos, calendario.partidos_api, prediction_b.predecir_partido_b,
                registro._version_modelo, registro._commit_codigo)
    try:
        registro.RUTA = Path(tempfile.mkdtemp()) / "registro.jsonl"
        calendario.proximos = lambda n=None: proximos
        calendario.partidos_api = lambda forzar=False: terminados or []
        prediction_b.predecir_partido_b = lambda l, v, f=None: {
            "datos_hasta": "2026-11-04", "probabilidades": {"victoria_local": 0.5, "empate": 0.3, "victoria_visitante": 0.2}}
        registro._version_modelo = lambda: "test"
        registro._commit_codigo = lambda: "abc1234"
        yield
    finally:
        (registro.RUTA, calendario.proximos, calendario.partidos_api, prediction_b.predecir_partido_b,
         registro._version_modelo, registro._commit_codigo) = guardado


def _p(local, visitante, dias, jornada=12):
    return {"fecha": iso(AHORA + timedelta(days=dias)), "local": local, "visitante": visitante, "jornada": jornada}


def test_no_duplica_y_solo_añade() -> None:
    with _falso([_p("A", "B", 2), _p("C", "D", 3)]):
        assert len(registro.registrar(AHORA)) == 2
        antes = registro.RUTA.read_text()
        assert registro.registrar(AHORA + timedelta(hours=1)) == [], "un partido ya registrado no se vuelve a registrar"
        assert registro.RUTA.read_text() == antes, "el archivo no debe cambiar si no hay partidos nuevos"
    with _falso([_p("A", "B", 2), _p("E", "F", 4)]):  # archivo nuevo: ahora sí
        registro.registrar(AHORA)
        antes = registro.RUTA.read_text()
        calendario.proximos = lambda n=None: [_p("A", "B", 2), _p("E", "F", 4), _p("G", "H", 5)]
        registro.registrar(AHORA)
        assert registro.RUTA.read_text().startswith(antes), "solo se añade al final; lo anterior queda idéntico"


def test_rechaza_partido_ya_empezado_y_muy_lejano() -> None:
    with _falso([_p("A", "B", -0.01), _p("C", "D", 0), _p("E", "F", 30), _p("G", "H", 1)]):
        nuevos = registro.registrar(AHORA)
        assert [n["local"] for n in nuevos] == ["G"], "ni empezados, ni a más de 10 días"


def test_puntuacion() -> None:
    fin = [{"status": "FINISHED", "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}, "score": {"fullTime": {"home": 2, "away": 0}}},
           {"status": "FINISHED", "homeTeam": {"name": "C"}, "awayTeam": {"name": "D"}, "score": {"fullTime": {"home": 0, "away": 1}}}]
    with _falso([_p("A", "B", 1), _p("C", "D", 1), _p("E", "F", 1)], fin):
        registro.registrar(AHORA)
        f = {r["local"]: r for r in registro.puntuar()}
        assert f["A"]["acierto"] is True and np.isclose(f["A"]["log_loss"], -np.log(0.5))
        assert f["C"]["acierto"] is False and np.isclose(f["C"]["log_loss"], -np.log(0.2))
        assert np.isclose(f["A"]["brier"], (0.5 - 1) ** 2 + 0.3**2 + 0.2**2), "brier de una victoria local con 0.5"
        assert f["E"]["resultado"] is None and "acierto" not in f["E"], "sin resultado no hay puntaje"
        r = registro.resumen()
        assert (r["registrados"], r["jugados"], r["aciertos"], r["concluyente"]) == (3, 2, 1, False)


def test_registro_nuevo_lleva_commit_y_el_viejo_se_lee_sin_el() -> None:
    fin = [{"status": "FINISHED", "homeTeam": {"name": "V"}, "awayTeam": {"name": "W"}, "score": {"fullTime": {"home": 1, "away": 0}}}]
    with _falso([_p("A", "B", 2)], fin):
        viejo = {"registrado_en": "2026-11-01T00:00:00+00:00", "temporada": 2026, "jornada": 11, "inicio_partido": "2026-11-02T20:00:00Z",
                 "local": "V", "visitante": "W", "modelo": "b", "version_modelo": "test", "datos_hasta": "2026-11-01",
                 "probabilidades": {"victoria_local": 0.4, "empate": 0.3, "victoria_visitante": 0.3}}  # sin commit_codigo
        registro.RUTA.write_text(json.dumps(viejo) + "\n")
        nuevos = registro.registrar(AHORA)
        assert nuevos[0]["commit_codigo"] == "abc1234"
        filas = registro.puntuar()  # no debe fallar por la clave ausente
        assert [r.get("commit_codigo") for r in filas] == [None, "abc1234"]
        assert registro.RUTA.read_text().startswith(json.dumps(viejo) + "\n"), "el registro viejo queda intacto"


def test_commit_desconocido_si_git_falla() -> None:
    # Se usa la función real (el _falso la reemplaza), así que se prueba por separado, y se restauran las dos cosas tocadas.
    original = registro.subprocess.run
    try:
        def sin_git(*a, **k):
            raise FileNotFoundError("git")
        registro.subprocess.run = sin_git
        assert registro._commit_codigo() == "desconocido", "sin git no debe romper"
        registro.subprocess.run = lambda *a, **k: registro.subprocess.CompletedProcess(a, 128, "", "fatal: not a git repository")
        assert registro._commit_codigo() == "desconocido", "fuera de un repositorio tampoco"
    finally:
        registro.subprocess.run = original
    assert registro._commit_codigo() != "", "con git real devuelve algo (un commit o «desconocido»)"


def test_puntuar_y_resumen_por_version() -> None:
    def reg(local: str, version: str) -> dict:
        return {"registrado_en": "x", "temporada": 2026, "jornada": 1, "inicio_partido": "2026-11-02T20:00:00Z", "local": local,
                "visitante": "Z", "modelo": "b", "version_modelo": version, "datos_hasta": "x",
                "probabilidades": {"victoria_local": 0.5, "empate": 0.3, "victoria_visitante": 0.2}}
    with _falso([]):
        registro.RUTA.write_text("".join(json.dumps(reg(l, v)) + "\n" for l, v in (("A", "vieja"), ("B", "test"), ("C", "test"))))
        assert [r["local"] for r in registro.puntuar()] == ["B", "C"], "por defecto, solo la versión actual"
        assert [r["local"] for r in registro.puntuar("vieja")] == ["A"]
        r = registro.resumen()
        assert r["registrados"] == 2 and r["versiones"] == {"vieja": 1, "test": 2}, r
        assert registro.resumen(version_modelo="vieja")["registrados"] == 1


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
