"""Tabla de posiciones de la temporada en curso, calculada con los mismos datos que usa el modelo B (CSV + API)."""
import pandas as pd

from . import calendario, resultados as R


def tabla() -> list[dict]:
    """Posiciones por puntos, diferencia de goles y goles a favor.

    Simplificación declarada: el reglamento desempata primero por el enfrentamiento directo (Art. 10 de las Normas);
    aquí se usa la diferencia de goles general, que coincide salvo empates a puntos entre equipos.
    """
    df = R.cargar_partidos(con_api=True)
    df = df[df["date"] >= pd.Timestamp(f"{calendario.TEMPORADA_ACTUAL}-07-01")]
    tm = R.a_equipo_partido(df)
    filas = []
    for equipo, g in tm.groupby("team"):
        g = g.sort_values("date")
        gf, gc = int(g["goals_for"].sum()), int(g["goals_against"].sum())
        filas.append({
            "equipo": equipo, "pj": len(g), "g": int((g["puntos"] == 3).sum()), "e": int((g["puntos"] == 1).sum()),
            "p": int((g["puntos"] == 0).sum()), "gf": gf, "gc": gc, "dg": gf - gc, "pts": int(g["puntos"].sum()),
            # Últimos 5 resultados, del más antiguo al más reciente: V ganó, E empató, D perdió.
            "forma": "".join({3: "V", 1: "E", 0: "D"}[int(x)] for x in g["puntos"].tail(5)),
        })
    filas.sort(key=lambda f: (-f["pts"], -f["dg"], -f["gf"], f["equipo"]))
    return [{"posicion": i + 1, **f} for i, f in enumerate(filas)]
