"""Agente predictivo: envuelve el modelo XGBoost entrenado en 02_modelo_baseline.ipynb.

Contrato: recibe dos equipos y una fecha, reconstruye la forma reciente de cada uno
SOLO con partidos anteriores a esa fecha (sin fuga de datos) y devuelve probabilidades.
"""
import os
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

# Raíz del repo = dos niveles arriba de backend/app/. Se puede cambiar con DATA_DIR (útil en Docker).
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
VENTANA = 5  # mismos 5 partidos que usamos con rolling(5) al entrenar

# Mismo mapeo que `target_map` del notebook 02: el modelo devuelve probabilidades en este orden.
ETIQUETAS = {0: "victoria_visitante", 1: "empate", 2: "victoria_local"}


@lru_cache
def cargar_modelo():
    # lru_cache: se lee del disco una sola vez, no en cada petición.
    return joblib.load(DATA_DIR / "modelo_predictivo_laliga.pkl")


@lru_cache
def cargar_team_matches() -> pd.DataFrame:
    # parse_dates: sin esto 'date' sería texto y no podríamos comparar fechas ni restarlas.
    return pd.read_csv(DATA_DIR / "team_matches.csv", parse_dates=["date"])


def equipos() -> list[str]:
    return sorted(cargar_team_matches()["team"].unique())


def ultima_forma(equipo: str, fecha: pd.Timestamp, team_matches: pd.DataFrame) -> dict | None:
    """Forma de un equipo con sus últimos 5 partidos ANTERIORES a `fecha`."""
    historial = team_matches[
        (team_matches["team"] == equipo) & (team_matches["date"] < fecha)
    ].sort_values("date")
    if historial.empty:
        return None
    ult = historial.tail(VENTANA)
    return {
        "forma_goles_favor": ult["goals_for"].mean(),
        "forma_goles_contra": ult["goals_against"].mean(),
        "forma_xg": ult["xg_for"].mean(),
        "forma_puntos": ult["puntos"].mean(),
        "forma_ppda": ult["ppda_for"].mean(),
        "dias_desde_ultimo_partido": (fecha - historial["date"].iloc[-1]).days,
    }


def predecir_partido(local: str, visitante: str, fecha: pd.Timestamp | None = None) -> dict:
    if local == visitante:
        raise ValueError("El equipo local y el visitante deben ser distintos.")
    fecha = fecha if fecha is not None else pd.Timestamp.today().normalize()
    tm, modelo = cargar_team_matches(), cargar_modelo()

    forma = {}
    for rol, equipo in (("home", local), ("away", visitante)):
        f = ultima_forma(equipo, fecha, tm)
        if f is None:
            raise ValueError(f"No hay historial de '{equipo}' antes de {fecha.date()}.")
        forma[rol] = f

    # Un diccionario con las 12 columnas que espera el modelo: home_forma_xg, away_forma_xg, ...
    fila = {f"home_{k}": v for k, v in forma["home"].items()}
    fila |= {f"away_{k}": v for k, v in forma["away"].items()}
    # El orden de columnas importa: lo tomamos del propio modelo en vez de repetirlo a mano.
    columnas = list(modelo.feature_names_in_)
    probs = modelo.predict_proba(pd.DataFrame([fila])[columnas])[0]

    probabilidades = {ETIQUETAS[int(c)]: round(float(p), 4) for c, p in zip(modelo.classes_, probs)}
    return {
        "fecha": str(fecha.date()),
        "probabilidades": probabilidades,
        "resultado_probable": max(probabilidades, key=probabilidades.get),
        "forma_local": {k: round(float(v), 3) for k, v in forma["home"].items()},
        "forma_visitante": {k: round(float(v), 3) for k, v in forma["away"].items()},
        "datos_hasta": str(tm["date"].max().date()),
    }
