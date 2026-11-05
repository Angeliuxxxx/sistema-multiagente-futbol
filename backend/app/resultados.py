"""Tabla de partidos «viva» para el modelo B: histórico (Understat) + CSV recientes (football-data.co.uk).

Por qué existe: el modelo A usa xG y PPDA, que no existen después de mayo de 2025. El modelo B usa solo columnas que
SÍ existen en las tres fuentes (goles, tiros, tiros a puerta), así que se puede actualizar hasta ayer.

Este módulo lo usan el entrenamiento Y la predicción: un solo cálculo de features evita el desfase
entrenamiento-inferencia que ya nos mordió con `dias_desde_ultimo_partido` (ver docs/datos.md).
"""
import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
HISTORICO = "la_liga_2014_2025_all_matches_final.csv"
CSV_RECIENTES = ("2025-2026.csv", "2026-2027.csv")
VENTANA = 5  # los mismos 5 partidos que el modelo A

# Nombre canónico = el del histórico (el que ya conoce el modelo A y el frontend). Lo que no está aquí ya coincide.
# Las dos fuentes nuevas escriben distinto los equipos, y sin esto «Ath Madrid» sería un equipo sin historial.
NOMBRES_CSV = {
    "Ath Bilbao": "Athletic Club", "Ath Madrid": "Atletico Madrid", "Betis": "Real Betis", "Celta": "Celta Vigo",
    "Espanol": "Espanyol", "Sociedad": "Real Sociedad", "Vallecano": "Rayo Vallecano",
    "La Coruna": "Deportivo La Coruna", "Santander": "Racing Santander", "Oviedo": "Real Oviedo",
}
# Nombres que devuelve la API de football-data.org (calendario) → canónico.
NOMBRES_API = {
    "Athletic Club": "Athletic Club", "Club Atlético de Madrid": "Atletico Madrid", "CA Osasuna": "Osasuna",
    "RCD Espanyol de Barcelona": "Espanyol", "FC Barcelona": "Barcelona", "Getafe CF": "Getafe", "Málaga CF": "Malaga",
    "Real Madrid CF": "Real Madrid", "Rayo Vallecano de Madrid": "Rayo Vallecano", "Levante UD": "Levante",
    "Real Betis Balompié": "Real Betis", "Real Sociedad de Fútbol": "Real Sociedad", "Villarreal CF": "Villarreal",
    "Valencia CF": "Valencia", "Deportivo Alavés": "Alaves", "Elche CF": "Elche", "RC Celta de Vigo": "Celta Vigo",
    "Sevilla FC": "Sevilla", "RC Deportivo La Coruña": "Deportivo La Coruna",
    "Real Racing Club de Santander": "Racing Santander",
    "Girona FC": "Girona", "RCD Mallorca": "Mallorca", "Real Oviedo": "Real Oviedo",
}

COLUMNAS = ["date", "home_team", "away_team", "home_goals", "away_goals", "home_shots", "away_shots",
            "home_sot", "away_sot"]


def _historico() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / HISTORICO, parse_dates=["date"])
    return df[COLUMNAS]


def _reciente(nombre: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / nombre, encoding="utf-8-sig")
    df = df.dropna(subset=["FTHG", "FTAG"])  # solo partidos ya jugados
    fecha = pd.to_datetime(df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M")
    out = pd.DataFrame({
        "date": fecha,
        "home_team": df["HomeTeam"].replace(NOMBRES_CSV), "away_team": df["AwayTeam"].replace(NOMBRES_CSV),
        "home_goals": df["FTHG"], "away_goals": df["FTAG"],
        "home_shots": df["HS"], "away_shots": df["AS"], "home_sot": df["HST"], "away_sot": df["AST"],
    })
    return out


def _temporada(fecha: pd.Timestamp) -> int:
    """Año en que EMPIEZA la temporada de esa fecha: de julio en adelante es la que arranca ese año, antes es la anterior."""
    return fecha.year if fecha.month >= 7 else fecha.year - 1


def _completar_con_api(df: pd.DataFrame) -> pd.DataFrame:
    """Añade los partidos jugados DESPUÉS del último CSV (la API los publica antes de que haya CSV nuevo).

    Llegan sin tiros (la API no los trae): las medias de forma ignoran esos huecos. Se descarta lo que ya está en el CSV
    (misma pareja local-visitante en la MISMA temporada) para que nada cuente doble. La clave usa la temporada y no el año
    natural: una pareja que jugó en marzo de 2026 (25/26) y vuelve en noviembre de 2026 (26/27) no es un duplicado.
    """
    from . import calendario  # import tardío: calendario importa este módulo
    nuevos = calendario.terminados()
    if nuevos.empty:
        return df
    nuevos = nuevos[nuevos["date"].dt.normalize() >= df["date"].max().normalize()]
    ya = set(zip(df["home_team"], df["away_team"], df["date"].map(_temporada)))
    nuevos = nuevos[[(h, a, _temporada(d)) not in ya for h, a, d in zip(nuevos["home_team"], nuevos["away_team"], nuevos["date"])]]
    return pd.concat([df, nuevos], ignore_index=True).sort_values("date").reset_index(drop=True)


def cargar_partidos(con_api: bool = False) -> pd.DataFrame:
    """Un partido por fila, ordenado por fecha, de 2014 hasta el último partido jugado.

    `con_api=False` (entrenamiento): solo histórico + CSV, que traen tiros completos y son reproducibles.
    `con_api=True` (predicción): además los resultados que la API tiene y los CSV aún no.
    """
    partes = [_historico()] + [_reciente(n) for n in CSV_RECIENTES if (DATA_DIR / n).exists()]
    df = pd.concat(partes, ignore_index=True).sort_values("date").reset_index(drop=True)
    if con_api:
        df = _completar_con_api(df)
    # Dos fuentes no deben solaparse: si lo hicieran, un partido contaría doble en la forma de un equipo.
    assert not df.duplicated(["date", "home_team", "away_team"]).any(), "partidos duplicados entre fuentes"
    return df


def a_equipo_partido(df: pd.DataFrame) -> pd.DataFrame:
    """De «un partido por fila» a «una fila por equipo y partido» (como team_matches.csv del modelo A)."""
    def lado(loc: str, rival: str, es_local: int) -> pd.DataFrame:
        return pd.DataFrame({
            "date": df["date"], "team": df[f"{loc}_team"], "is_home": es_local,
            "goals_for": df[f"{loc}_goals"], "goals_against": df[f"{rival}_goals"],
            "shots_for": df[f"{loc}_shots"], "sot_for": df[f"{loc}_sot"],
        })
    tm = pd.concat([lado("home", "away", 1), lado("away", "home", 0)]).sort_values(["team", "date"])
    gf, gc = tm["goals_for"], tm["goals_against"]
    tm["puntos"] = (gf > gc) * 3 + (gf == gc) * 1
    tm["dia"] = tm["date"].dt.normalize()  # el descanso se mide en días de calendario, igual al entrenar y al predecir
    return tm.reset_index(drop=True)


FORMA = {"forma_goles_favor": "goals_for", "forma_goles_contra": "goals_against", "forma_puntos": "puntos",
         "forma_tiros": "shots_for", "forma_tiros_puerta": "sot_for"}


def features_entrenamiento(tm: pd.DataFrame) -> pd.DataFrame:
    """Forma de cada equipo ANTES de cada partido: shift(1) y luego media de 5 (sin fuga, como en el notebook 01)."""
    g = tm.groupby("team")
    for nombre, col in FORMA.items():
        tm[nombre] = g[col].transform(lambda x: x.shift(1).rolling(VENTANA, min_periods=1).mean())
    tm["dias_desde_ultimo_partido"] = g["dia"].diff().dt.days
    return tm


def forma_equipo(tm: pd.DataFrame, equipo: str, fecha: pd.Timestamp) -> dict | None:
    """Misma forma que `features_entrenamiento`, pero para un partido futuro: usa solo partidos anteriores a `fecha`."""
    hist = tm[(tm["team"] == equipo) & (tm["date"] < fecha)]
    if hist.empty:
        return None
    ult = hist.tail(VENTANA)
    out = {nombre: float(ult[col].mean()) for nombre, col in FORMA.items()}
    out["dias_desde_ultimo_partido"] = (fecha.normalize() - hist["dia"].iloc[-1]).days
    return out


def tabla_partidos_con_features(con_api: bool = False) -> pd.DataFrame:
    """Un partido por fila con home_*/away_* + resultado, listo para entrenar el modelo B."""
    df = cargar_partidos(con_api)
    tm = features_entrenamiento(a_equipo_partido(df))
    cols = list(FORMA) + ["dias_desde_ultimo_partido"]
    local = tm[tm["is_home"] == 1][["date", "team"] + cols].rename(columns={"team": "home_team", **{c: f"home_{c}" for c in cols}})
    visita = tm[tm["is_home"] == 0][["date", "team"] + cols].rename(columns={"team": "away_team", **{c: f"away_{c}" for c in cols}})
    out = df.merge(local, on=["date", "home_team"]).merge(visita, on=["date", "away_team"])
    # Mismo mapeo de clases que el modelo A: 0 visitante, 1 empate, 2 local.
    out["target"] = (out["home_goals"] > out["away_goals"]) * 2 + (out["home_goals"] == out["away_goals"]) * 1
    return out
