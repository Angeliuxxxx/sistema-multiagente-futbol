"""Calibración del modelo B: SOLO MIDE. No reentrena ni toca data/modelo_predictivo_laliga_b.pkl ni lo aplica en la API.

Ejecutar desde backend/:  python -m scripts.calibracion_b

Sigue el método de scripts/calibracion.py (el de A) y reutiliza sus funciones (bins por cuantiles, ECE, Platt) para que
A y B se midan con la misma vara. Se evalúan los dos tramos de scripts/entrenar_modelo_b.py, con los mismos cortes y los
mismos hiperparámetros (data/modelo_b_params.json, los elegidos en el tramo 1 sin ver 2025/26):

  Tramo 1: entrenar < 2022-08-01, probar 2022-08 → 2025-05 (los mismos partidos que evalúa A).
  Tramo 2: entrenar < 2025-08-01, probar 2025-08 → último dato (A no puede evaluarse aquí).

Para cada tramo se imprime, por clase, la probabilidad media predicha frente a la frecuencia real, la tabla de fiabilidad y
ECE/Brier. Además, y solo como INFORMACIÓN, un modelo sustituto + Platt (como se hizo para A): se entrena con datos
anteriores a la temporada de calibración para que sus probabilidades ahí sean fuera de muestra. Esto no se aplica a B:
decidir si calibrar es del autor.
"""
import json
import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana: debe correr en WSL/servidor
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import log_loss  # noqa: E402
from sklearn.utils.class_weight import compute_sample_weight  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import resultados as R  # noqa: E402
from scripts.calibracion import NOMBRES, ajustar_platt, bins_cuantiles, brier  # noqa: E402
from scripts.entrenar_modelo_b import B2, COLS, CORTE_A, CORTE_VIVO, LADOS  # noqa: E402

warnings.filterwarnings("ignore")
FIGURAS = Path(__file__).resolve().parents[2] / "docs" / "figuras"
COLUMNAS = COLS["B2 (+tiros, 12 feat.)"]  # el modelo en producción es B2
FIN_TEST_1 = pd.Timestamp("2025-06-01")  # mismo fin que el tramo 1 de entrenar_modelo_b.py


def ece_n(p: np.ndarray, y: np.ndarray, n: int) -> float:
    b = bins_cuantiles(p, y, n)
    return float((b["n"] * (b["frec"] - b["p_media"]).abs()).sum() / b["n"].sum())


def entrenar(datos: pd.DataFrame, params: dict) -> XGBClassifier:
    """Mismos hiperparámetros y mismo class_weight balanceado que el modelo de producción."""
    m = XGBClassifier(**params)
    m.fit(datos[COLUMNAS], datos["target"], sample_weight=compute_sample_weight("balanced", datos["target"]))
    return m


def informe(titulo: str, P: np.ndarray, y: np.ndarray, n_bins: int) -> dict:
    print(f"\n--- {titulo} ({len(y)} partidos, {n_bins} bins por cuantiles) ---")
    print(f"log-loss {log_loss(y, P, labels=[0, 1, 2]):.4f} | Brier multiclase {np.mean(np.sum((P - np.eye(3)[y]) ** 2, axis=1)):.4f}")
    eces = []
    for k, nombre in enumerate(NOMBRES):
        yk = (y == k).astype(float)
        e = ece_n(P[:, k], yk, n_bins)
        eces.append(e)
        print(f"  {nombre:<19} predicha media {P[:, k].mean():.3f} | frecuencia real {yk.mean():.3f} | ECE {e:.4f} | Brier(1 vs resto) {brier(P[:, k], yk):.4f}")
    print(f"  ECE medio {np.mean(eces):.4f}")
    print("  Tabla de fiabilidad (predicha / observada por bin, de menor a mayor probabilidad):")
    for k, nombre in enumerate(NOMBRES):
        b = bins_cuantiles(P[:, k], (y == k).astype(float), n_bins)
        print(f"    {nombre:<19}", " ".join(f"{a:.2f}/{f:.2f}" for a, f in zip(b["p_media"], b["frec"])))
    return {"ece_medio": float(np.mean(eces))}


def sustituto_platt(df: pd.DataFrame, params: dict, ini_calib: pd.Timestamp, fin_calib: pd.Timestamp,
                    test: pd.DataFrame, etiqueta: str, n_bins: int, prior: np.ndarray) -> np.ndarray:
    """Informativo: sustituto entrenado con < ini_calib, Platt ajustado en [ini_calib, fin_calib), evaluado en `test`."""
    previo = df[df["date"] < ini_calib]
    calib = df[(df["date"] >= ini_calib) & (df["date"] < fin_calib)]
    sust = entrenar(previo, params)
    S_cal, S_te = sust.predict_proba(calib[COLUMNAS]), sust.predict_proba(test[COLUMNAS])
    Q = ajustar_platt(S_cal, calib["target"].to_numpy())(S_te)
    y = test["target"].to_numpy()
    print(f"\n== {etiqueta}: sustituto entrenado con {len(previo)} partidos < {ini_calib.date()}, Platt con {len(calib)} partidos "
          f"de {ini_calib.date()} a {fin_calib.date()} ==")
    informe("Sustituto sin calibrar", S_te, y, n_bins)
    informe("Sustituto + Platt (INFORMATIVO, no se aplica)", Q, y, n_bins)
    nll = lambda P: -np.log(np.clip(P[np.arange(len(y)), y], 1e-15, 1))  # noqa: E731
    d = nll(Q) - nll(S_te)
    print(f"  Δ log-loss (Platt − sustituto) = {d.mean():+.4f} ± {2 * d.std(ddof=1) / np.sqrt(len(d)):.4f} (±2 e.e.; negativo = Platt mejora)")
    # Contra la referencia que importa: predecir siempre la frecuencia de clases del entrenamiento del tramo.
    d0 = nll(Q) - (-np.log(prior[y]))
    print(f"  Δ log-loss (sustituto + Platt − frecuencia de clases) = {d0.mean():+.4f} ± {2 * d0.std(ddof=1) / np.sqrt(len(d0)):.4f} (±2 e.e.)")
    return Q


def figura(tramos: list[tuple[str, np.ndarray, np.ndarray, int]], ruta: Path) -> None:
    fig, ejes = plt.subplots(len(tramos), 3, figsize=(13, 4.4 * len(tramos)), squeeze=False)
    for fila, (titulo, P, y, n_bins) in enumerate(tramos):
        for k in range(3):
            ax = ejes[fila][k]
            b = bins_cuantiles(P[:, k], (y == k).astype(float), n_bins)
            ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="Calibración perfecta")
            ax.plot(b["p_media"], b["frec"], "o-", color="#1f77b4", ms=4, label="Modelo B")
            ax.set_title(f"{titulo}\n{NOMBRES[k]}", fontsize=10)
            ax.set_xlabel("Probabilidad predicha (media del bin)")
            ax.set_ylabel("Frecuencia observada")
            ax.set_xlim(0, 0.8)
            ax.set_ylim(0, 0.8)
            ax.grid(alpha=0.3)
    ejes[0][0].legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=130)
    plt.close(fig)


def main() -> None:
    params = json.loads((R.DATA_DIR / "modelo_b_params.json").read_text())
    df = R.tabla_partidos_con_features()
    df = df.dropna(subset=[c for c in df.columns if "forma" in c])  # cold start, igual que entrenar_modelo_b.py
    assert all(c in df.columns for c in COLUMNAS) and len(B2) * len(LADOS) == len(COLUMNAS)

    # Tramo 1: los mismos partidos que A (se cruza con las claves de su conjunto de prueba, como en entrenar_modelo_b.py).
    a = pd.read_csv(R.DATA_DIR / "df_final_features.csv", parse_dates=["date"])
    claves = a[a["date"] >= CORTE_A][["date", "home_team", "away_team"]]
    tr1 = df[df["date"] < CORTE_A]
    te1 = df[(df["date"] >= CORTE_A) & (df["date"] < FIN_TEST_1)].merge(claves)
    P1 = entrenar(tr1, params).predict_proba(te1[COLUMNAS])
    y1 = te1["target"].to_numpy()

    tr2, te2 = df[df["date"] < CORTE_VIVO], df[df["date"] >= CORTE_VIVO]
    P2 = entrenar(tr2, params).predict_proba(te2[COLUMNAS])
    y2 = te2["target"].to_numpy()

    print(f"Hiperparámetros de data/modelo_b_params.json: { {k: v for k, v in params.items() if v is not None} }")
    print(f"Tramo 1: entrenamiento {len(tr1)}, prueba {len(te1)} | Tramo 2: entrenamiento {len(tr2)}, prueba {len(te2)} "
          f"(hasta {te2['date'].max().date()})")
    informe("TRAMO 1 · B2 (2022-08 → 2025-05)", P1, y1, 8)
    informe("TRAMO 2 · B2 (2025-08 → último dato)", P2, y2, 5)  # 5 bins: con ~500 partidos, 8 dejarían ~60 por bin (muy ruidoso)

    frec = lambda d: np.bincount(d["target"], minlength=3) / len(d)  # noqa: E731
    sustituto_platt(df, params, pd.Timestamp("2021-08-01"), CORTE_A, te1, "Tramo 1", 8, frec(tr1))
    sustituto_platt(df, params, pd.Timestamp("2024-08-01"), CORTE_VIVO, te2, "Tramo 2", 5, frec(tr2))

    figura([(f"Tramo 1 ({len(y1)} partidos)", P1, y1, 8), (f"Tramo 2 ({len(y2)} partidos)", P2, y2, 5)], FIGURAS / "fiabilidad_b.png")
    print(f"\nFigura guardada en {FIGURAS / 'fiabilidad_b.png'}")


if __name__ == "__main__":
    main()
