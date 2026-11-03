"""Calendario y resultados recientes desde la API oficial de football-data.org (plan gratuito, con token en .env).

Por qué una caché en disco: el plan gratis permite 10 peticiones por minuto y la API no trae tiros, así que solo la
usamos para dos cosas: (1) los próximos partidos y (2) los resultados posteriores al último CSV descargado.
Si no hay token o no hay red, el sistema sigue funcionando con los CSV y la última caché (degrada, no se cae).
"""
import json
import os
import time
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

from . import resultados as R

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # el token vive solo en .env (nunca en el repo)
URL = "https://api.football-data.org/v4/competitions/PD/matches"
CACHE = R.DATA_DIR / "calendario_cache.json"
VIGENCIA_S = 6 * 3600  # 6 h: las jornadas se juegan en fines de semana y a media semana, no cada minuto
TEMPORADA_ACTUAL = int(os.getenv("TEMPORADA_ACTUAL", "2026"))  # año en que EMPIEZA la temporada (2026 = 2026/27)


def _descargar() -> list[dict]:
    clave = os.getenv("FOOTBALL_DATA_KEY")
    if not clave:
        raise RuntimeError("Falta FOOTBALL_DATA_KEY en .env")
    r = httpx.get(URL, params={"season": TEMPORADA_ACTUAL}, headers={"X-Auth-Token": clave}, timeout=20)
    r.raise_for_status()
    return r.json()["matches"]


def partidos_api(forzar: bool = False) -> list[dict]:
    """Todos los partidos de la temporada (jugados y por jugar). Usa la caché si es reciente o si la API falla."""
    if CACHE.exists() and not forzar and time.time() - CACHE.stat().st_mtime < VIGENCIA_S:
        return json.loads(CACHE.read_text())
    try:
        datos = _descargar()
        CACHE.write_text(json.dumps(datos))
        return datos
    except (httpx.HTTPError, RuntimeError):
        return json.loads(CACHE.read_text()) if CACHE.exists() else []


def _canonico(nombre: str) -> str:
    return R.NOMBRES_API.get(nombre, nombre)


def terminados() -> pd.DataFrame:
    """Partidos jugados según la API, con las mismas columnas que `resultados.COLUMNAS` (tiros desconocidos = NaN)."""
    filas = [{
        "date": pd.Timestamp(m["utcDate"]).tz_localize(None),
        "home_team": _canonico(m["homeTeam"]["name"]), "away_team": _canonico(m["awayTeam"]["name"]),
        "home_goals": m["score"]["fullTime"]["home"], "away_goals": m["score"]["fullTime"]["away"],
        "home_shots": float("nan"), "away_shots": float("nan"), "home_sot": float("nan"), "away_sot": float("nan"),
    } for m in partidos_api() if m["status"] == "FINISHED"]
    return pd.DataFrame(filas, columns=R.COLUMNAS)


def proximos(n: int | None = None) -> list[dict]:
    """Próximos partidos por jugar, en orden. Cada uno: fecha ISO (UTC), local, visitante, jornada."""
    futuros = [m for m in partidos_api() if m["status"] in ("SCHEDULED", "TIMED")]
    futuros.sort(key=lambda m: m["utcDate"])
    out = [{"fecha": m["utcDate"], "local": _canonico(m["homeTeam"]["name"]),
            "visitante": _canonico(m["awayTeam"]["name"]), "jornada": m.get("matchday")} for m in futuros]
    return out[:n] if n else out
