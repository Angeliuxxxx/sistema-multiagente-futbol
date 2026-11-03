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

# Hora que se asume cuando la fecha llega SIN hora (p. ej. "2025-06-01" desde la API).
# Por qué: training-serving skew. Al entrenar, dias_desde_ultimo_partido restaba horas de inicio reales; en inferencia la
# fecha llegaba a las 00:00 y la feature salía 1 día menos en ~57 % de los casos (valores 0-1 que el modelo nunca vio;
# el mínimo en entrenamiento es 2). Evidencia (backend/scripts/auditar_dias_descanso.py, docs/mediciones.md): la hora
# mediana de los 4.180 partidos es 17:30 y es la que mejor reproduce la feature de entrenamiento (MAE 0,28 días,
# 71,8 % de coincidencia exacta, sesgo -0,07) frente a 00:00 (MAE 0,57, 43,3 %). La moda (20:00) es peor (62,2 %).
HORA_POR_DEFECTO = pd.Timedelta(hours=17, minutes=30)
DIAS_FECHA_POR_DEFECTO = 7  # sin fecha: último dato + 7 días (una jornada típica), ver fecha_por_defecto()

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


def equipos(modelo: str = "b") -> list[str]:
    """Equipos válidos. El modelo A solo conoce los del histórico (hasta 2025); B, los de la temporada en curso."""
    if modelo == "b":
        from . import prediction_b
        return prediction_b.equipos_b()
    return sorted(cargar_team_matches()["team"].unique())


def equipos_conocidos() -> list[str]:
    """Todos los equipos que algún modelo conoce. El orquestador reconoce nombres con esta lista (y no con la de B sola):
    así «Girona vs Villarreal» sigue yendo a predicción aunque Girona no juegue en la temporada actual."""
    return sorted(set(equipos("a")) | set(equipos("b")))


def fecha_por_defecto(tm: pd.DataFrame | None = None) -> pd.Timestamp:
    """Fecha a predecir cuando el usuario no da ninguna: último dato + 7 días, a la hora típica.

    Con el día siguiente salían 0 o 1 días de descanso (el último partido es del 24-25 de mayo), valores fuera de lo
    que el modelo vio al entrenar (mínimo 2). A 7 días el descanso queda en el rango normal de una jornada.
    """
    tm = cargar_team_matches() if tm is None else tm
    return tm["date"].max().normalize() + pd.Timedelta(days=DIAS_FECHA_POR_DEFECTO) + HORA_POR_DEFECTO


def con_hora(fecha: pd.Timestamp, equipos_: tuple[str, ...], tm: pd.DataFrame) -> pd.Timestamp:
    """Completa la hora de una fecha que llega a las 00:00 para igualar lo que vio el modelo al entrenar.

    - Si algún equipo jugó realmente ese día, se usa la hora real de ese partido (así reproducimos exacto la feature
      del entrenamiento, p. ej. al volver a predecir un partido ya jugado).
    - Si no, HORA_POR_DEFECTO. Una fecha que ya trae hora se respeta tal cual.
    """
    if fecha != fecha.normalize():
        return fecha
    for equipo in equipos_:
        del_dia = tm[(tm["team"] == equipo) & (tm["date"].dt.normalize() == fecha)]
        if not del_dia.empty:
            return del_dia["date"].iloc[0]
    return fecha + HORA_POR_DEFECTO


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


def predecir_partido(local: str, visitante: str, fecha: pd.Timestamp | None = None, modelo: str = "b") -> dict:
    """Punto de entrada único. `modelo="b"` (por defecto, datos hasta ayer) o `"a"` (xG y PPDA, datos hasta mayo de 2025)."""
    if modelo == "b":
        from . import prediction_b
        return prediction_b.predecir_partido_b(local, visitante, fecha)
    return predecir_partido_a(local, visitante, fecha)


def predecir_partido_a(local: str, visitante: str, fecha: pd.Timestamp | None = None) -> dict:
    if local == visitante:
        raise ValueError("El equipo local y el visitante deben ser distintos.")
    tm, modelo = cargar_team_matches(), cargar_modelo()
    fecha = con_hora(fecha, (local, visitante), tm) if fecha is not None else fecha_por_defecto(tm)

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
        "modelo": "a",
        "fecha": str(fecha.date()),
        "probabilidades": probabilidades,
        "resultado_probable": max(probabilidades, key=probabilidades.get),
        "forma_local": {k: round(float(v), 3) for k, v in forma["home"].items()},
        "forma_visitante": {k: round(float(v), 3) for k, v in forma["away"].items()},
        "datos_hasta": str(tm["date"].max().date()),
    }
