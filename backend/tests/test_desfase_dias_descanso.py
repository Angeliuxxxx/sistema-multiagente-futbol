"""Prueba anti-regresión del desfase entrenamiento-inferencia de `dias_desde_ultimo_partido`.

Ejecutar desde backend/:  python -m tests.test_desfase_dias_descanso   (o `pytest` si está instalado)

Si alguien vuelve a calcular la feature con la fecha a medianoche, estas pruebas fallan.
"""
import pandas as pd

from app import prediction


def _gap_entrenamiento(tm: pd.DataFrame) -> pd.Series:
    # Fórmula literal del notebook 01 (celda 11): diferencia entre marcas de tiempo, en días enteros.
    return tm.sort_values(["team", "date"]).groupby("team")["date"].diff().dt.days


def test_partido_real_reproduce_la_feature_de_entrenamiento() -> None:
    """Pedir una fecha (sin hora) en la que el equipo jugó de verdad debe dar EXACTAMENTE la feature del entrenamiento."""
    tm = prediction.cargar_team_matches().sort_values(["team", "date"]).reset_index(drop=True)
    tm["esperado"] = _gap_entrenamiento(tm)
    # Muestra determinista y repartida (cada 7.ª fila) para que la prueba tarde segundos y no minutos.
    errores = []
    for _, fila in tm.dropna(subset=["esperado"]).iloc[::7].iterrows():
        fecha = fila["date"].normalize()  # lo que llega de la API: solo el día
        f = prediction.ultima_forma(fila["team"], prediction.con_hora(fecha, (fila["team"],), tm), tm)
        if f["dias_desde_ultimo_partido"] != fila["esperado"]:
            errores.append((fila["team"], str(fila["date"]), f["dias_desde_ultimo_partido"], fila["esperado"]))
    assert not errores, f"Desfase entrenamiento-inferencia en {len(errores)} casos, p. ej. {errores[:3]}"


def test_sin_hora_ni_partido_se_usa_la_hora_por_defecto() -> None:
    tm = prediction.cargar_team_matches()
    fecha = pd.Timestamp("2025-07-15")  # sin partidos: los datos terminan en mayo de 2025
    assert prediction.con_hora(fecha, ("Barcelona", "Real Madrid"), tm) == fecha + prediction.HORA_POR_DEFECTO


def test_fecha_con_hora_se_respeta() -> None:
    tm = prediction.cargar_team_matches()
    fecha = pd.Timestamp("2025-07-15 21:00")
    assert prediction.con_hora(fecha, ("Barcelona",), tm) == fecha


def test_fecha_por_defecto_no_da_descansos_fuera_de_lo_visto() -> None:
    """El mínimo en entrenamiento es 2 días: la fecha por defecto no debe producir 0 ni 1 en ningún equipo."""
    tm = prediction.cargar_team_matches()
    fecha = prediction.fecha_por_defecto(tm)
    minimo_entrenamiento = _gap_entrenamiento(tm).min()
    for equipo in prediction.equipos():
        f = prediction.ultima_forma(equipo, fecha, tm)
        assert f["dias_desde_ultimo_partido"] >= minimo_entrenamiento, equipo


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("ok", nombre)
