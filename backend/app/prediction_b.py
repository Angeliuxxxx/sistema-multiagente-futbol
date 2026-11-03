"""Agente predictivo, modelo B: XGBoost sin xG ni PPDA, actualizable hasta ayer.

Mismo contrato que `prediction.predecir_partido` (modelo A) para que el resto del sistema no distinga cuál lo produjo,
salvo por las features de forma, que aquí son tiros y tiros a puerta en lugar de xG y PPDA.
Entrenamiento y evaluación: backend/scripts/entrenar_modelo_b.py (resultados en docs/modelo_b.md).
"""
from functools import lru_cache

import joblib
import pandas as pd

from . import calendario, resultados as R

ETIQUETAS = {0: "victoria_visitante", 1: "empate", 2: "victoria_local"}


@lru_cache
def cargar_modelo_b():
    return joblib.load(R.DATA_DIR / "modelo_predictivo_laliga_b.pkl")


@lru_cache
def cargar_tabla() -> pd.DataFrame:
    """Una fila por equipo y partido, con los resultados de la API incluidos. Se vuelve a leer con `refrescar()`."""
    return R.a_equipo_partido(R.cargar_partidos(con_api=True))


def refrescar() -> None:
    """Descarta la tabla en memoria y la caché de la API: la siguiente petición verá los partidos de ayer."""
    calendario.partidos_api(forzar=True)
    cargar_tabla.cache_clear()


def equipos_b() -> list[str]:
    """Los 20 equipos de la temporada en curso (según el calendario de la API), no los 33 que han pasado por el histórico.
    Sin API ni caché, se usan los que jugaron en el último CSV."""
    partidos = calendario.partidos_api()
    if partidos:
        return sorted({calendario._canonico(m[lado]["name"]) for m in partidos for lado in ("homeTeam", "awayTeam")})
    tm = cargar_tabla()
    return sorted(tm[tm["date"] >= pd.Timestamp(f"{calendario.TEMPORADA_ACTUAL}-07-01")]["team"].unique())


def datos_hasta() -> pd.Timestamp:
    return cargar_tabla()["date"].max()


def fecha_por_defecto(local: str, visitante: str) -> pd.Timestamp:
    """Si el partido está en el calendario, su fecha real. Si no, el día siguiente al último dato (hoy/mañana)."""
    for p in calendario.proximos():
        if p["local"] == local and p["visitante"] == visitante:
            return pd.Timestamp(p["fecha"]).tz_localize(None)
    return datos_hasta().normalize() + pd.Timedelta(days=1)


def predecir_partido_b(local: str, visitante: str, fecha: pd.Timestamp | None = None) -> dict:
    if local == visitante:
        raise ValueError("El equipo local y el visitante deben ser distintos.")
    tm, modelo = cargar_tabla(), cargar_modelo_b()
    origen = "usuario" if fecha is not None else ("calendario" if any(
        p["local"] == local and p["visitante"] == visitante for p in calendario.proximos()) else "por_defecto")
    fecha = fecha if fecha is not None else fecha_por_defecto(local, visitante)

    forma = {}
    for rol, equipo in (("home", local), ("away", visitante)):
        f = R.forma_equipo(tm, equipo, fecha)
        if f is None:
            raise ValueError(f"No hay historial de '{equipo}' antes de {fecha.date()}.")
        forma[rol] = f
    fila = {f"home_{k}": v for k, v in forma["home"].items()} | {f"away_{k}": v for k, v in forma["away"].items()}
    columnas = list(modelo.feature_names_in_)
    probs = modelo.predict_proba(pd.DataFrame([fila])[columnas])[0]
    probabilidades = {ETIQUETAS[int(c)]: round(float(p), 4) for c, p in zip(modelo.classes_, probs)}
    redondear = lambda d: {k: round(float(v), 3) for k, v in d.items()}  # noqa: E731
    return {
        "modelo": "b",
        "fecha": str(fecha.date()),
        "fecha_origen": origen,
        "probabilidades": probabilidades,
        "resultado_probable": max(probabilidades, key=probabilidades.get),
        "forma_local": redondear(forma["home"]),
        "forma_visitante": redondear(forma["away"]),
        "datos_hasta": str(datos_hasta().date()),
    }
