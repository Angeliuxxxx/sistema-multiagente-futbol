"""Auditoría del desfase entrenamiento-inferencia de `dias_desde_ultimo_partido`.

Ejecutar desde backend/:  python -m scripts.auditar_dias_descanso

Qué mide (todo con los datos reales, sin reentrenar nada):
  (a) hora de inicio mediana y moda de todos los partidos;
  (b) para cada hora por defecto candidata, el error medio absoluto (MAE) y el % de coincidencia exacta entre la
      feature simulada (fecha sin hora + hora candidata) y la usada al entrenar (diferencia entre marcas de tiempo);
  (c) la sensibilidad del modelo: log-loss del conjunto de prueba (>= 2022-08-01, mismo corte que el notebook 02)
      con la feature original frente a la simulada.

Por qué existe: al entrenar, `dias_desde_ultimo_partido` resta horas de inicio reales; en inferencia la fecha llegaba
a medianoche y la feature salía 1 día menos en ~57 % de los casos (training-serving skew). Ver docs/datos.md.
"""
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss

from app.prediction import DATA_DIR

warnings.filterwarnings("ignore")
CORTE_TEST = "2022-08-01"  # el mismo split cronológico del notebook 02
TARGET = {"Victoria visitante": 0, "Empate": 1, "Victoria local": 2}


def hora_del_dia(fechas: pd.Series) -> pd.Series:
    """Hora de inicio como Timedelta desde la medianoche."""
    return fechas - fechas.dt.normalize()


def gap_simulado(fechas: pd.Series, previas: pd.Series, hora: pd.Timedelta) -> pd.Series:
    """Lo que calcularía la inferencia: fecha a medianoche + hora fija, menos el último partido, en días enteros."""
    return (fechas.dt.normalize() + hora - previas).dt.days


def main() -> None:
    tm = pd.read_csv(DATA_DIR / "team_matches.csv", parse_dates=["date"]).sort_values(["team", "date"])
    tm["previa"] = tm.groupby("team")["date"].shift(1)
    tm["gap_entreno"] = tm["date"].sub(tm["previa"]).dt.days  # fórmula del notebook 01, celda 11

    # (a) Hora de inicio: una fila por partido (is_home == 1) para no contar cada partido dos veces.
    partidos = tm[tm["is_home"] == 1]
    horas = hora_del_dia(partidos["date"])
    mediana, moda = horas.median(), horas.mode().iloc[0]
    fmt = lambda t: f"{int(t.total_seconds() // 3600):02d}:{int(t.total_seconds() % 3600 // 60):02d}"  # noqa: E731
    print(f"(a) Partidos: {len(partidos)} | hora mediana {fmt(mediana)} | moda {fmt(moda)} "
          f"({(horas == moda).mean():.1%} de los partidos)")
    print("    distribución de horas:", {fmt(k): int(v) for k, v in horas.value_counts().head(6).items()})

    # Coherencia: la columna de df_final_features debe ser la fórmula de entrenamiento.
    df = pd.read_csv(DATA_DIR / "df_final_features.csv", parse_dates=["date"])
    for rol, flag in (("home", 1), ("away", 0)):
        ref = tm[tm["is_home"] == flag][["date", "team", "gap_entreno"]].rename(
            columns={"team": f"{rol}_team", "gap_entreno": "ref"})
        m = df.merge(ref, on=["date", f"{rol}_team"], how="left")
        ok = np.isclose(m[f"{rol}_dias_desde_ultimo_partido"].fillna(-1), m["ref"].fillna(-1)).mean()
        print(f"    df_final_features.{rol}_dias == diff().dt.days en {ok:.2%} de las filas")

    # (b) Candidatos. 19:00 y 00:00 pedidos expresamente (00:00 es el comportamiento anterior).
    candidatos = {f"mediana {fmt(mediana)}": mediana, f"moda {fmt(moda)}": moda,
                  "19:00": pd.Timedelta(hours=19), "00:00 (antes)": pd.Timedelta(0)}
    v = tm.dropna(subset=["previa"])
    print("\n(b) Feature simulada vs entrenamiento (todas las filas equipo-partido con partido previo):")
    print(f"    {'hora':<18}{'MAE (días)':>12}{'coincide':>11}{'sesgo medio':>13}")
    for nombre, h in candidatos.items():
        g = gap_simulado(v["date"], v["previa"], h)
        print(f"    {nombre:<18}{(g - v['gap_entreno']).abs().mean():>12.4f}{(g == v['gap_entreno']).mean():>11.1%}"
              f"{(g - v['gap_entreno']).mean():>13.3f}")
    print("    barrido horario (para ver si hay una hora claramente mejor):")
    barrido = {h: (gap_simulado(v["date"], v["previa"], pd.Timedelta(hours=h)) == v["gap_entreno"]).mean() for h in range(0, 24)}
    print("    " + " ".join(f"{h:02d}h={p:.0%}" for h, p in barrido.items()))

    # (c) Sensibilidad del modelo en el conjunto de prueba.
    modelo = joblib.load(DATA_DIR / "modelo_predictivo_laliga.pkl")
    cols = list(modelo.feature_names_in_)
    df["target"] = df["resultado"].map(TARGET)
    formas = [c for c in cols if "dias" not in c]
    test = df.dropna(subset=formas)
    test = test[test["date"] >= CORTE_TEST].copy()
    y = test["target"].to_numpy()

    def ll(frame: pd.DataFrame) -> float:
        return log_loss(y, modelo.predict_proba(frame[cols]), labels=list(modelo.classes_))

    print(f"\n(c) Log-loss en prueba ({len(test)} partidos, >= {CORTE_TEST}):")
    print(f"    feature original (entrenamiento)  {ll(test):.4f}")
    previas = {}
    for rol, flag in (("home", 1), ("away", 0)):
        ref = tm[tm["is_home"] == flag][["date", "team", "previa"]].rename(
            columns={"team": f"{rol}_team", "previa": f"{rol}_previa"})
        test = test.merge(ref, on=["date", f"{rol}_team"], how="left")
        previas[rol] = f"{rol}_previa"
    resultados = {}
    for nombre, h in candidatos.items():
        sim = test.copy()
        for rol in ("home", "away"):
            sim[f"{rol}_dias_desde_ultimo_partido"] = gap_simulado(sim["date"], sim[previas[rol]], h)
        resultados[nombre] = ll(sim)
        print(f"    simulada con {nombre:<16} {resultados[nombre]:.4f}")
    mejor = min(resultados, key=resultados.get)
    print(f"    mejor candidata por log-loss: {mejor}")


if __name__ == "__main__":
    main()
