"""Entrena y evalúa el modelo B (sin xG ni PPDA) con el MISMO protocolo que el modelo A (notebook 02).

Uso (desde backend/):  python -m scripts.entrenar_modelo_b [--guardar]

Protocolo (idéntico a A salvo las features):
  - split cronológico, train < 2022-08-01; búsqueda aleatoria de 30 combinaciones con TimeSeriesSplit(5);
  - class_weight balanceado (compute_sample_weight); métrica log-loss.
Además mide dos referencias que A no tenía: la frecuencia de clases y las cuotas medias de las casas de apuestas.
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import resultados as R  # noqa: E402

CORTE_A = pd.Timestamp("2022-08-01")  # el mismo corte que el notebook 02
CORTE_VIVO = pd.Timestamp("2025-08-01")  # inicio de 2025/26: tramo que A no puede evaluar (no hay xG/PPDA)

LADOS = ("home", "away")
# B1: solo resultados. B2: B1 + tiros y tiros a puerta (sustituyen a xG y PPDA de A, que ya no existen).
B1 = ["forma_goles_favor", "forma_goles_contra", "forma_puntos", "dias_desde_ultimo_partido"]
B2 = ["forma_goles_favor", "forma_goles_contra", "forma_tiros_puerta", "forma_puntos", "forma_tiros",
      "dias_desde_ultimo_partido"]
COLS = {"B1 (solo resultados, 8 feat.)": [f"{l}_{c}" for c in B1 for l in LADOS],
        "B2 (+tiros, 12 feat.)": [f"{l}_{c}" for c in B2 for l in LADOS]}

PARAMS = {"max_depth": [3, 4, 5, 6], "learning_rate": [0.01, 0.03, 0.05, 0.1], "n_estimators": [200, 300, 500],
          "subsample": [0.6, 0.8, 1.0], "colsample_bytree": [0.6, 0.8, 1.0], "min_child_weight": [1, 3, 5]}


def buscar(X, y) -> XGBClassifier:
    base = XGBClassifier(objective="multi:softprob", eval_metric="mlogloss", random_state=42)
    s = RandomizedSearchCV(base, PARAMS, n_iter=30, scoring="neg_log_loss", cv=TimeSeriesSplit(n_splits=5),
                           random_state=42, n_jobs=6)
    s.fit(X, y, sample_weight=compute_sample_weight("balanced", y))
    return s.best_estimator_


def cuotas_casas() -> pd.DataFrame:
    """Probabilidades implícitas de las cuotas medias (se normalizan para quitar el margen de la casa).
    SOLO como referencia de comparación: nunca entran como feature (no están disponibles para el histórico entero)."""
    filas = []
    for n in R.CSV_RECIENTES:
        df = pd.read_csv(R.DATA_DIR / n, encoding="utf-8-sig").dropna(subset=["FTHG", "AvgH"])
        inv = 1 / df[["AvgA", "AvgD", "AvgH"]].to_numpy()  # orden de clases del modelo: visitante, empate, local
        p = inv / inv.sum(axis=1, keepdims=True)
        filas.append(pd.DataFrame({
            "date": pd.to_datetime(df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M"),
            "home_team": df["HomeTeam"].replace(R.NOMBRES_CSV), "away_team": df["AwayTeam"].replace(R.NOMBRES_CSV),
            "p0": p[:, 0], "p1": p[:, 1], "p2": p[:, 2]}))
    return pd.concat(filas)


def nll(y, p) -> np.ndarray:
    """Pérdida (log-loss) de cada partido por separado: sirve para comparar dos modelos partido a partido."""
    return -np.log(np.clip(p[np.arange(len(y)), np.asarray(y)], 1e-15, 1))


def diferencia(nombre: str, perdida_x: np.ndarray, perdida_y: np.ndarray) -> str:
    """Media ± error estándar de (x - y). Si el intervalo de ±2 errores incluye 0, no hay diferencia demostrable."""
    d = perdida_x - perdida_y
    return f"{nombre}: {d.mean():+.4f} ± {2 * d.std(ddof=1) / np.sqrt(len(d)):.4f} (±2 e.e.)"


def fila(nombre: str, y, p) -> dict:
    return {"modelo": nombre, "n": len(y), "log_loss": round(log_loss(y, p, labels=[0, 1, 2]), 4),
            "accuracy": round(accuracy_score(y, p.argmax(axis=1)), 4)}


def main(guardar: bool) -> None:
    df = R.tabla_partidos_con_features()
    todas_forma = [c for c in df.columns if "forma" in c]
    df = df.dropna(subset=todas_forma)  # cold start, igual que A
    tr = df[df["date"] < CORTE_A]
    te = df[(df["date"] >= CORTE_A) & (df["date"] < pd.Timestamp("2025-06-01"))]
    print(f"Train {len(tr)} (<{CORTE_A.date()}) · Test comparable con A {len(te)} · Tramo vivo (>= {CORTE_VIVO.date()}) "
          f"{(df['date'] >= CORTE_VIVO).sum()}")

    # ---- Tramo 1: mismo test que A -------------------------------------------------------------------------------
    a = pd.read_csv(R.DATA_DIR / "df_final_features.csv", parse_dates=["date"])
    a["target"] = a["resultado"].map({"Victoria visitante": 0, "Empate": 1, "Victoria local": 2})
    modelo_a = joblib.load(R.DATA_DIR / "modelo_predictivo_laliga.pkl")
    a_cols = list(modelo_a.feature_names_in_)
    a = a.dropna(subset=[c for c in a_cols if "dias" not in c])
    a_te = a[a["date"] >= CORTE_A]
    claves = te[["date", "home_team", "away_team"]].merge(a_te[["date", "home_team", "away_team"]])
    te = te.merge(claves)  # exactamente los mismos partidos que A, para que la comparación sea justa
    a_te = a_te.merge(claves)
    y1 = te["target"].to_numpy()
    prior = np.bincount(tr["target"], minlength=3) / len(tr)
    resumen1 = [fila("Frecuencia de clases (sin features)", y1, np.tile(prior, (len(y1), 1))),
                fila("A: XGBoost 12 feat. con xG y PPDA", a_te["target"], modelo_a.predict_proba(a_te[a_cols]))]
    mejores, perd1 = {}, {"A": nll(a_te["target"], modelo_a.predict_proba(a_te[a_cols])),
                          "prior": nll(y1, np.tile(prior, (len(y1), 1)))}
    for nombre, cols in COLS.items():
        m = buscar(tr[cols], tr["target"])
        mejores[nombre] = m.get_params()
        p = m.predict_proba(te[cols])
        perd1[nombre] = nll(y1, p)
        resumen1.append(fila(nombre, y1, p))
    print("\n== Tramo 1: mismo test que A (2022-08 → 2025-05) ==")
    print(pd.DataFrame(resumen1).to_string(index=False))
    b1, b2 = list(COLS)
    print("Diferencias de log-loss partido a partido (negativo = el primero es mejor):")
    for x, y in ((b2, "A"), (b1, "A"), (b2, b1), ("A", "prior"), (b2, "prior")):
        print("  " + diferencia(f"{x} − {y}", perd1[x], perd1[y]))

    # ---- Tramo 2: datos que A no puede ver ------------------------------------------------------------------------
    tr2, te2 = df[df["date"] < CORTE_VIVO], df[df["date"] >= CORTE_VIVO]
    y2 = te2["target"].to_numpy()
    prior2 = np.bincount(tr2["target"], minlength=3) / len(tr2)
    cuotas = te2.merge(cuotas_casas(), on=["date", "home_team", "away_team"])
    perd2, perd2c = {}, {}  # perd2c: B evaluado solo en los partidos que tienen cuota, para compararlo con ellas
    resumen2 = [fila("Frecuencia de clases", y2, np.tile(prior2, (len(y2), 1))),
                fila("Cuotas medias de casas de apuestas", cuotas["target"], cuotas[["p0", "p1", "p2"]].to_numpy())]
    for nombre, cols in COLS.items():
        # Mismos hiperparámetros que se eligieron en el tramo 1 (sin ver nada de 2025/26), reajustados con datos hasta 2025-07.
        m = XGBClassifier(**mejores[nombre])
        m.fit(tr2[cols], tr2["target"], sample_weight=compute_sample_weight("balanced", tr2["target"]))
        p = m.predict_proba(te2[cols])
        perd2[nombre] = nll(y2, p)
        perd2c[nombre] = nll(cuotas["target"], m.predict_proba(cuotas[cols]))
        resumen2.append(fila(nombre, y2, p))
    print(f"\n== Tramo 2: 2025/26 + 2026/27 hasta {te2['date'].max().date()} (A no puede evaluarse aquí) ==")
    print(pd.DataFrame(resumen2).to_string(index=False))

    perd2["prior"] = nll(y2, np.tile(prior2, (len(y2), 1)))
    perd2["cuotas"] = nll(cuotas["target"], cuotas[["p0", "p1", "p2"]].to_numpy())
    print("Diferencias de log-loss partido a partido en el tramo 2:")
    print("  " + diferencia(f"{b2} − frecuencia de clases", perd2[b2], perd2["prior"]))
    print("  " + diferencia(f"{b2} − {b1}", perd2[b2], perd2[b1]))
    print("  " + diferencia(f"{b2} − cuotas", perd2c[b2], perd2["cuotas"]))

    if guardar:
        # Reajuste final con TODO lo jugado hasta ayer y los hiperparámetros ya elegidos: así B conoce la forma reciente.
        nombre, cols = list(COLS.items())[1]
        final = XGBClassifier(**mejores[nombre])
        final.fit(df[cols], df["target"], sample_weight=compute_sample_weight("balanced", df["target"]))
        destino = R.DATA_DIR / "modelo_predictivo_laliga_b.pkl"
        joblib.dump(final, destino)
        print(f"\nGuardado {destino.name} ({nombre}), entrenado con {len(df)} partidos hasta {df['date'].max().date()}")
        (R.DATA_DIR / "modelo_b_params.json").write_text(json.dumps(mejores[nombre], indent=2, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardar", action="store_true", help="entrena el modelo final y lo guarda en data/")
    main(ap.parse_args().guardar)
