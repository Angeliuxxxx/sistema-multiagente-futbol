"""Pruebas del modelo B. Ejecutar desde backend/:  python -m tests.test_modelo_b

1) Sin desfase entrenamiento-inferencia: la forma que se calcula al predecir un partido pasado debe ser IDÉNTICA a la
   del entrenamiento (ya nos pasó con `dias_desde_ultimo_partido` en el modelo A, ver docs/datos.md).
2) Sin fuga: la forma de un partido no cambia aunque borremos ese partido y todos los posteriores.
3) Los nombres de equipo de las tres fuentes se unifican (sin duplicados tipo «Ath Madrid» / «Atletico Madrid»).
"""
from contextlib import contextmanager

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


@contextmanager
def _datos_csv(sin_partidos_de: str | None = None, desde: str = "2026-09-15"):
    """Tabla del CSV (sin API) y sin calendario; opcionalmente se borran los partidos recientes de un equipo para simular
    que lleva semanas sin jugar. Restaura lo reemplazado pase lo que pase."""
    from app import calendario, prediction_b
    tabla, proximos = prediction_b.cargar_tabla, calendario.proximos
    tm = R.a_equipo_partido(R.cargar_partidos())
    if sin_partidos_de:
        tm = tm[~((tm["team"] == sin_partidos_de) & (tm["date"] >= desde))]
    prediction_b.cargar_tabla = lambda: tm
    calendario.proximos = lambda n=None: []
    try:
        yield prediction_b
    finally:
        prediction_b.cargar_tabla, calendario.proximos = tabla, proximos


def _predecir_con_datos_csv(fecha: pd.Timestamp, **kw) -> dict:
    with _datos_csv(**kw) as pb:
        return pb.predecir_partido_b("Barcelona", "Real Madrid", fecha)


def test_aviso_si_la_fecha_ya_pasó() -> None:
    ultimo = R.cargar_partidos()["date"].max()
    for fecha in (pd.Timestamp("2025-09-01"), ultimo.normalize()):  # claramente pasada y justo el último día con datos
        r = _predecir_con_datos_csv(fecha)
        assert r["aviso"] and "fuera de muestra" in r["aviso"], fecha


def test_sin_aviso_si_la_fecha_es_futura() -> None:
    ultimo = R.cargar_partidos()["date"].max()
    assert _predecir_con_datos_csv(ultimo.normalize() + pd.Timedelta(days=3))["aviso"] is None


def test_aviso_forma_desactualizada_con_descanso_enorme() -> None:
    # Caso real: el Clásico del calendario es en mayo de 2027 y el último partido conocido es de noviembre de 2026.
    r = _predecir_con_datos_csv(pd.Timestamp("2027-05-09 20:00"))
    dias = max(r["forma_local"]["dias_desde_ultimo_partido"], r["forma_visitante"]["dias_desde_ultimo_partido"])
    assert dias > 150, dias
    assert "Forma desactualizada" in r["aviso"] and f"han pasado {int(dias)} días" in r["aviso"]
    assert "Barcelona" in r["aviso"] or "Real Madrid" in r["aviso"]
    assert "fuera de muestra" not in r["aviso"], "la fecha es futura: no debe mezclar el aviso de fecha pasada"


def test_nombra_al_equipo_con_mas_dias() -> None:
    # El Real Madrid «no juega» desde el 15-sep; el Barcelona sí: el aviso nombra solo al Madrid.
    ultimo = R.cargar_partidos()["date"].max()
    r = _predecir_con_datos_csv(ultimo.normalize() + pd.Timedelta(days=1), sin_partidos_de="Real Madrid")
    assert r["forma_visitante"]["dias_desde_ultimo_partido"] > 30 >= r["forma_local"]["dias_desde_ultimo_partido"]
    assert "Real Madrid" in r["aviso"] and "Barcelona" not in r["aviso"]


def test_sin_aviso_con_descanso_normal() -> None:
    ultimo = R.cargar_partidos()["date"].max()
    r = _predecir_con_datos_csv(ultimo.normalize() + pd.Timedelta(days=1))
    assert max(r["forma_local"]["dias_desde_ultimo_partido"], r["forma_visitante"]["dias_desde_ultimo_partido"]) <= 30
    assert r["aviso"] is None


def test_fecha_pasada_y_forma_desactualizada_se_unen() -> None:
    # Fecha anterior al último dato Y un equipo sin jugar desde septiembre: los dos textos, ninguno pisa al otro.
    r = _predecir_con_datos_csv(pd.Timestamp("2026-10-25 20:00"), sin_partidos_de="Real Madrid")
    assert "fuera de muestra" in r["aviso"] and "Forma desactualizada" in r["aviso"] and "Real Madrid" in r["aviso"]


def test_aviso_forma_llega_al_chat() -> None:
    from app import orquestador
    ultimo = R.cargar_partidos()["date"].max()
    with _datos_csv(sin_partidos_de="Real Madrid"):
        texto, detalle = orquestador._responder_prediccion("Barcelona", "Real Madrid", (ultimo + pd.Timedelta(days=1)).date())
    assert "Forma desactualizada" in texto and "Real Madrid" in texto, "el aviso debe ir en el texto del chat"
    assert detalle.aviso and "Forma desactualizada" in detalle.aviso, "y en el detalle que pinta el panel"
    with _datos_csv():
        texto, detalle = orquestador._responder_prediccion("Barcelona", "Real Madrid", (ultimo + pd.Timedelta(days=1)).date())
    assert "desactualizada" not in texto and detalle.aviso is None


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
