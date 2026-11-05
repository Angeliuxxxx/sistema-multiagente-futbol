"""Pruebas del modelo B. Ejecutar desde backend/:  python -m tests.test_modelo_b

1) Sin desfase entrenamiento-inferencia: la forma que se calcula al predecir un partido pasado debe ser IDÉNTICA a la
   del entrenamiento (ya nos pasó con `dias_desde_ultimo_partido` en el modelo A, ver docs/datos.md).
2) Sin fuga: la forma de un partido no cambia aunque borremos ese partido y todos los posteriores.
3) Los nombres de equipo de las tres fuentes se unifican (sin duplicados tipo «Ath Madrid» / «Atletico Madrid»).
"""
import numpy as np
import pandas as pd

from app import resultados as R

COLS = list(R.FORMA) + ["dias_desde_ultimo_partido"]


def _tm() -> pd.DataFrame:
    return R.features_entrenamiento(R.a_equipo_partido(R.cargar_partidos()))


def test_inferencia_igual_a_entrenamiento() -> None:
    tm = _tm()
    errores = []
    # Cada 11.ª fila con historial previo: determinista, repartida por toda la historia y rápida.
    for _, f in tm.dropna(subset=["forma_goles_favor"]).iloc[::11].iterrows():
        got = R.forma_equipo(tm, f["team"], f["date"])
        for c in COLS:
            esperado = f[c]
            if not (np.isclose(got[c], esperado, equal_nan=True)):
                errores.append((f["team"], str(f["date"]), c, got[c], esperado))
    assert not errores, f"{len(errores)} diferencias, p. ej. {errores[:3]}"


def test_sin_fuga_de_datos() -> None:
    tm = _tm()
    equipo = "Barcelona"
    fila = tm[tm["team"] == equipo].iloc[-1]
    truncada = R.a_equipo_partido(R.cargar_partidos().query("date < @fila.date"))
    got = R.forma_equipo(truncada, equipo, fila["date"])
    for c in COLS:
        assert np.isclose(got[c], fila[c], equal_nan=True), c


def test_nombres_unificados() -> None:
    equipos = set(R.cargar_partidos()["home_team"])
    for malo in R.NOMBRES_CSV:
        assert malo not in equipos, f"«{malo}» sin traducir al nombre canónico"
    assert {"Atletico Madrid", "Real Betis", "Racing Santander", "Real Oviedo"} <= equipos


def _con_calendario_falso(csv: pd.DataFrame, api: pd.DataFrame) -> pd.DataFrame:
    """Ejecuta `_completar_con_api` con un calendario falso (sin red) y lo deja como estaba, pase lo que pase."""
    from app import calendario
    original = calendario.terminados
    calendario.terminados = lambda: api
    try:
        return R._completar_con_api(csv)
    finally:
        calendario.terminados = original


def _partido(fecha: str, local: str, visitante: str) -> dict:
    return {"date": pd.Timestamp(fecha), "home_team": local, "away_team": visitante, "home_goals": 1, "away_goals": 0,
            "home_shots": np.nan, "away_shots": np.nan, "home_sot": np.nan, "away_sot": np.nan}


def test_api_anade_revancha_de_otra_temporada() -> None:
    # A–B se jugó en marzo de 2026 (temporada 25/26) y vuelve en noviembre de 2026 (26/27): el partido nuevo NO es un duplicado.
    # Con la clave (local, visitante, año natural) ambos caen en 2026 y se perdía el de noviembre.
    csv = pd.DataFrame([_partido("2026-03-01 20:00", "A", "B"), _partido("2026-11-01 20:00", "C", "D")], columns=R.COLUMNAS)
    api = pd.DataFrame([_partido("2026-11-08 20:00", "A", "B")], columns=R.COLUMNAS)
    out = _con_calendario_falso(csv, api)
    assert len(out) == 3 and (out["date"] == pd.Timestamp("2026-11-08 20:00")).any(), "la revancha de otra temporada debe entrar"


def test_api_no_duplica_partido_de_la_misma_temporada() -> None:
    # El mismo partido ya está en el CSV (aunque la API lo escriba con otra hora): no debe contar doble.
    csv = pd.DataFrame([_partido("2026-11-01 20:00", "A", "B")], columns=R.COLUMNAS)
    api = pd.DataFrame([_partido("2026-11-01 20:00", "A", "B"), _partido("2026-11-02 20:00", "E", "F")], columns=R.COLUMNAS)
    out = _con_calendario_falso(csv, api)
    assert len(out) == 2 and not out.duplicated(["home_team", "away_team", "date"]).any()


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
