"""Registro de predicciones: evaluación HACIA ADELANTE del modelo B.

Idea: guardar cada pronóstico ANTES del partido y puntuarlo DESPUÉS con el resultado real. Sin esto, «predije bien» no es
verificable: `/proximos` recalcula con los datos de cada momento y nadie podría demostrar qué dijo el modelo antes.

Garantías (cada una tiene su prueba en tests/test_registro.py):
  - Solo se añaden líneas (JSONL): nunca se reescribe ni se borra una predicción ya registrada.
  - Un partido se registra UNA vez: la primera predicción es la única válida (no se puede «mejorar» después).
  - No se acepta ninguna predicción con el partido ya empezado.
  - El archivo se versiona en Git: cada commit lleva fecha, y eso es la prueba externa de que el registro existía antes del partido.
"""
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import calendario, prediction_b, resultados as R

RUTA = R.DATA_DIR / "registro_predicciones.jsonl"
HORIZONTE_DIAS = 10  # se registra todo lo que se juega en los próximos 10 días (una jornada y media)
MIN_PARA_CONCLUIR = 30  # con menos partidos, el error del log-loss es mayor que cualquier diferencia entre modelos
CLASES = ("victoria_visitante", "empate", "victoria_local")


def _leer() -> list[dict]:
    if not RUTA.exists():
        return []
    return [json.loads(linea) for linea in RUTA.read_text().splitlines() if linea.strip()]


def _version_modelo() -> str:
    """Huella del .pkl: si algún día se reentrena, el registro dice con qué versión se hizo cada pronóstico."""
    return hashlib.sha256((R.DATA_DIR / "modelo_predictivo_laliga_b.pkl").read_bytes()).hexdigest()[:12]


def _commit_codigo() -> str:
    """Commit del código con que se hizo el pronóstico. Nunca debe romper el registro: sin git, sin carpeta .git o
    con cualquier fallo devuelve «desconocido» (un pronóstico sin commit vale más que un pronóstico perdido)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).resolve().parent,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "desconocido"
    except Exception:  # noqa: BLE001 — git ausente, timeout, permisos...: da igual la causa
        return "desconocido"


def registrar(ahora: datetime | None = None, horizonte_dias: int = HORIZONTE_DIAS) -> list[dict]:
    """Registra los partidos próximos que aún no estén registrados. Devuelve SOLO los nuevos."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora + pd.Timedelta(days=horizonte_dias)
    ya = {(r["local"], r["visitante"], r["temporada"]) for r in _leer()}
    commit = _commit_codigo()  # una sola vez por llamada: es el mismo código para todos los pronósticos de la tanda
    nuevos = []
    for p in calendario.proximos():
        inicio = datetime.fromisoformat(p["fecha"].replace("Z", "+00:00"))
        clave = (p["local"], p["visitante"], calendario.TEMPORADA_ACTUAL)
        if inicio <= ahora or inicio > limite or clave in ya:
            continue  # ya empezó (no se acepta), está muy lejos o ya registrado (la primera predicción manda)
        try:
            r = prediction_b.predecir_partido_b(p["local"], p["visitante"], pd.Timestamp(inicio).tz_localize(None))
        except ValueError:
            continue  # sin historial: mejor no registrar nada que inventar un pronóstico
        nuevos.append({
            "registrado_en": ahora.isoformat(timespec="seconds"), "temporada": calendario.TEMPORADA_ACTUAL,
            "jornada": p["jornada"], "inicio_partido": p["fecha"], "local": p["local"], "visitante": p["visitante"],
            "modelo": "b", "version_modelo": _version_modelo(), "commit_codigo": commit, "datos_hasta": r["datos_hasta"],
            "probabilidades": r["probabilidades"],
        })
    if nuevos:
        with RUTA.open("a") as f:  # modo «a»: solo añade al final
            for n in nuevos:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
    return nuevos


@lru_cache
def _frecuencias() -> dict[str, float]:
    """Frecuencia de clases de TODO lo jugado: el pronóstico «sin saber nada» contra el que se compara el modelo."""
    df = R.cargar_partidos()
    objetivo = (df["home_goals"] > df["away_goals"]) * 2 + (df["home_goals"] == df["away_goals"]) * 1
    f = np.bincount(objetivo, minlength=3) / len(df)
    return dict(zip(CLASES, map(float, f)))


def _resultados_reales() -> dict[tuple[str, str], str]:
    """(local, visitante) → clase real, solo de partidos terminados de la temporada en curso."""
    out = {}
    for m in calendario.partidos_api():
        if m["status"] != "FINISHED":
            continue
        g = m["score"]["fullTime"]
        clave = (calendario._canonico(m["homeTeam"]["name"]), calendario._canonico(m["awayTeam"]["name"]))
        out[clave] = CLASES[2] if g["home"] > g["away"] else CLASES[0] if g["home"] < g["away"] else CLASES[1]
    return out


def puntuar(version_modelo: str | None = None) -> list[dict]:
    """Cada predicción registrada con su resultado y sus puntajes (si el partido ya se jugó).

    Solo cuenta la versión del modelo pedida (por defecto, la actual): mezclar pronósticos de modelos distintos en una
    sola cifra impediría decir cuál de ellos acierta. Los registros viejos sin `commit_codigo` se leen igual (`.get`)."""
    version_modelo = version_modelo or _version_modelo()
    reales, freq = _resultados_reales(), _frecuencias()
    filas = []
    for r in _leer():
        if r.get("version_modelo") != version_modelo:
            continue
        real = reales.get((r["local"], r["visitante"]))
        fila = {**r, "resultado": real}
        if real:
            p = r["probabilidades"]
            fila |= {
                "acierto": max(p, key=p.get) == real,
                "log_loss": -float(np.log(max(p[real], 1e-15))),
                "log_loss_frecuencia": -float(np.log(freq[real])),
                # Brier multiclase: suma de (probabilidad − 1 si ocurrió, 0 si no)² sobre las tres clases.
                "brier": float(sum((p[c] - (c == real)) ** 2 for c in CLASES)),
            }
        filas.append(fila)
    return filas


def resumen(filas: list[dict] | None = None, version_modelo: str | None = None) -> dict:
    filas = puntuar(version_modelo) if filas is None else filas
    jugados = [f for f in filas if f["resultado"]]
    # `versiones` cuenta TODOS los pronósticos del archivo por versión (no solo la puntuada), para que se vea de un
    # vistazo si hay registros de más de un modelo y por qué las cifras de abajo no incluyen a todos.
    base = {"registrados": len(filas), "jugados": len(jugados), "minimo_para_concluir": MIN_PARA_CONCLUIR,
            "concluyente": len(jugados) >= MIN_PARA_CONCLUIR,
            "versiones": dict(Counter(r.get("version_modelo", "desconocida") for r in _leer()))}
    if not jugados:
        return base
    ll = np.array([f["log_loss"] for f in jugados])
    lf = np.array([f["log_loss_frecuencia"] for f in jugados])
    d = ll - lf
    return base | {
        "aciertos": sum(f["acierto"] for f in jugados),
        "acierto_pct": round(100 * sum(f["acierto"] for f in jugados) / len(jugados), 1),
        "log_loss": round(float(ll.mean()), 4), "log_loss_frecuencia": round(float(lf.mean()), 4),
        "brier": round(float(np.mean([f["brier"] for f in jugados])), 4),
        # Diferencia modelo − frecuencia con su error: si ±2 errores incluyen 0, no se puede afirmar que el modelo gane.
        "diferencia": round(float(d.mean()), 4),
        "error_2e": round(float(2 * d.std(ddof=1) / np.sqrt(len(d))), 4) if len(d) > 1 else None,
    }
