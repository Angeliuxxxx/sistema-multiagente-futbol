"""Calibración del modelo predictivo sobre el conjunto de prueba (>= 2022-08-01). NO reentrena ni toca el .pkl.

Ejecutar desde backend/:  python -m scripts.calibracion

Qué mide:
  1. Por clase (visitante / empate / local): curva de fiabilidad (bins por cuantiles), ECE, Brier y log-loss one-vs-rest.
  2. Log-loss global del modelo y de la LÍNEA BASE exacta (frecuencias de clase del conjunto de entrenamiento).
  3. Dos calibradores (isotónico por clase y Platt multinomial) ajustados SOLO con la última temporada de entrenamiento
     (2021-08-01 <= fecha < 2022-08-01), nunca con la prueba, y evaluados en la prueba.

Por qué bins por cuantiles: con 1.140 partidos y un empate que casi nunca supera p=0,35, bins de ancho fijo dejan
casillas vacías o con 5 partidos; por cuantiles cada bin tiene ~el mismo número de partidos y su frecuencia observada es
igual de fiable.

Advertencia metodológica (se imprime también): el modelo se entrenó con TODO lo anterior a 2022-08-01, incluida la
temporada usada para calibrar, así que sus probabilidades ahí están sobreajustadas (in-sample) y más seguras de lo que
serán en datos nuevos. Calibrar con ellas puede quedarse corto; se mide cuánto comparando log-loss en ese tramo vs. prueba.
"""
import warnings
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # sin ventana: el script debe poder correr en WSL/servidor
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.metrics import log_loss  # noqa: E402
from sklearn.utils.class_weight import compute_sample_weight  # noqa: E402

from app.prediction import DATA_DIR  # noqa: E402

warnings.filterwarnings("ignore")
CORTE_TEST = "2022-08-01"      # mismo split cronológico del notebook 02
INICIO_CALIB = "2021-08-01"    # última temporada de entrenamiento: tramo anterior a la prueba
TARGET = {"Victoria visitante": 0, "Empate": 1, "Victoria local": 2}
NOMBRES = ["Victoria visitante", "Empate", "Victoria local"]
N_BINS = 8                     # ~142 partidos por bin en la prueba
FIGURAS = Path(__file__).resolve().parents[2] / "docs" / "figuras"
EPS = 1e-6


def bins_cuantiles(p: np.ndarray, y: np.ndarray, n: int = N_BINS) -> pd.DataFrame:
    """Curva de fiabilidad: por bin, probabilidad media predicha vs. frecuencia observada de la clase."""
    orden = np.argsort(p, kind="stable")
    trozos = np.array_split(orden, n)
    return pd.DataFrame({"p_media": [p[t].mean() for t in trozos], "frec": [y[t].mean() for t in trozos],
                         "n": [len(t) for t in trozos]})


def ece(p: np.ndarray, y: np.ndarray) -> float:
    """Error de calibración esperado: media ponderada de |frecuencia - probabilidad| por bin."""
    b = bins_cuantiles(p, y)
    return float((b["n"] * (b["frec"] - b["p_media"]).abs()).sum() / b["n"].sum())


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def logloss_binaria(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def metricas(P: np.ndarray, y: np.ndarray) -> dict:
    """P: (n, 3) con columnas en el orden visitante, empate, local; y: 0/1/2."""
    por_clase = {}
    for k, nombre in enumerate(NOMBRES):
        yk = (y == k).astype(float)
        por_clase[nombre] = dict(ece=ece(P[:, k], yk), brier=brier(P[:, k], yk), logloss=logloss_binaria(P[:, k], yk))
    return dict(clase=por_clase, logloss=log_loss(y, P, labels=[0, 1, 2]),
                brier_multi=float(np.mean(np.sum((P - np.eye(3)[y]) ** 2, axis=1))),
                ece_medio=float(np.mean([v["ece"] for v in por_clase.values()])))


def ajustar_isotonica(P: np.ndarray, y: np.ndarray):
    """Una isotónica por clase (one-vs-rest) y renormalización: las tres salidas deben seguir sumando 1."""
    iso = [IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip").fit(P[:, k], (y == k).astype(float))
           for k in range(3)]

    def aplicar(Q: np.ndarray) -> np.ndarray:
        R = np.column_stack([iso[k].predict(Q[:, k]) for k in range(3)])
        return R / R.sum(axis=1, keepdims=True)
    return aplicar


def ajustar_platt(P: np.ndarray, y: np.ndarray):
    """Platt multinomial: regresión logística sobre log(p). Solo 3x3+3 parámetros, así que apenas sobreajusta
    con ~380 partidos (la isotónica tiene muchos más grados de libertad)."""
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(np.log(np.clip(P, EPS, 1)), y)  # C alto = sin regularizar
    return lambda Q: lr.predict_proba(np.log(np.clip(Q, EPS, 1)))


def figura_fiabilidad(P_dict: dict[str, np.ndarray], y: np.ndarray, ruta: Path, titulo: str) -> None:
    colores = {"Original": "#1f77b4", "Isotónica": "#d95f02", "Platt": "#1b9e77"}
    fig, ejes = plt.subplots(1, 3, figsize=(13, 4.4))
    for k, ax in enumerate(ejes):
        ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="Calibración perfecta")
        for nombre, P in P_dict.items():
            b = bins_cuantiles(P[:, k], (y == k).astype(float))
            ax.plot(b["p_media"], b["frec"], "o-", color=colores[nombre], label=nombre, ms=4)
        ax.set_title(NOMBRES[k])
        ax.set_xlabel("Probabilidad predicha (media del bin)")
        ax.set_ylabel("Frecuencia observada")
        ax.set_xlim(0, 0.8)
        ax.set_ylim(0, 0.8)
        ax.grid(alpha=0.3)
    ejes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle(titulo)
    fig.tight_layout()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=130)
    plt.close(fig)


def imprimir(titulo: str, m: dict) -> None:
    print(f"\n{titulo}: log-loss {m['logloss']:.4f} | Brier multiclase {m['brier_multi']:.4f} | ECE medio {m['ece_medio']:.4f}")
    for nombre, v in m["clase"].items():
        print(f"    {nombre:<20} ECE {v['ece']:.4f}  Brier {v['brier']:.4f}  log-loss(1 vs resto) {v['logloss']:.4f}")


def main() -> None:
    modelo = joblib.load(DATA_DIR / "modelo_predictivo_laliga.pkl")
    cols = list(modelo.feature_names_in_)
    assert list(modelo.classes_) == [0, 1, 2], "el orden de clases debe ser visitante, empate, local"
    df = pd.read_csv(DATA_DIR / "df_final_features.csv", parse_dates=["date"])
    df["target"] = df["resultado"].map(TARGET)
    formas = [c for c in cols if "dias" not in c]
    df = df.dropna(subset=formas)   # igual que auditar_dias_descanso: sin los primeros partidos sin forma
    train = df[df["date"] < CORTE_TEST]
    calib = train[train["date"] >= INICIO_CALIB]
    test = df[df["date"] >= CORTE_TEST]
    y_tr, y_cal, y_te = (d["target"].to_numpy() for d in (train, calib, test))
    P_cal = modelo.predict_proba(calib[cols])
    P_te = modelo.predict_proba(test[cols])
    print(f"Entrenamiento {len(train)} | tramo de calibración {len(calib)} ({INICIO_CALIB} a {CORTE_TEST}) | prueba {len(test)}")
    print("Frecuencias reales en prueba:", {n: round(float((y_te == k).mean()), 3) for k, n in enumerate(NOMBRES)})
    print("Probabilidad media predicha en prueba:", {n: round(float(P_te[:, k].mean()), 3) for k, n in enumerate(NOMBRES)})

    # Línea base exacta: predecir SIEMPRE las frecuencias de clase del entrenamiento.
    frec = np.bincount(y_tr, minlength=3) / len(y_tr)
    base = np.tile(frec, (len(y_te), 1))
    print(f"\nLínea base (frecuencias de entrenamiento {dict(zip(NOMBRES, frec.round(4)))}): "
          f"log-loss en prueba = {log_loss(y_te, base, labels=[0, 1, 2]):.4f}")

    m_orig = metricas(P_te, y_te)
    imprimir("Modelo original en prueba", m_orig)
    print(f"\nSesgo in-sample: log-loss del modelo en el tramo de calibración (visto al entrenar) "
          f"{log_loss(y_cal, P_cal, labels=[0, 1, 2]):.4f} vs. prueba {m_orig['logloss']:.4f}")

    calibradores = {"Isotónica": ajustar_isotonica(P_cal, y_cal), "Platt": ajustar_platt(P_cal, y_cal)}
    salidas = {"Original": P_te}
    for nombre, f in calibradores.items():
        salidas[nombre] = f(P_te)
        imprimir(f"{nombre} (ajustada solo con {INICIO_CALIB}..{CORTE_TEST}) en prueba", metricas(salidas[nombre], y_te))

    # Bootstrap pareado: ¿la diferencia de log-loss es mayor que el ruido de 1.140 partidos?
    rng = np.random.default_rng(0)
    def ll_filas(P):  # log-loss por partido
        return -np.log(np.clip(P[np.arange(len(y_te)), y_te], EPS, 1))
    for nombre in calibradores:
        d = ll_filas(salidas[nombre]) - ll_filas(P_te)
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
        lo, hi = np.percentile(boots, [2.5, 97.5])
        print(f"\nΔ log-loss ({nombre} − original) = {d.mean():+.4f}  IC95 bootstrap [{lo:+.4f}, {hi:+.4f}]")

    # --- Comprobación SIN sesgo in-sample, con un modelo SUSTITUTO (vive solo en memoria; no se guarda ni sustituye al pkl) ---
    # Mismos hiperparámetros y mismo class_weight balanceado, pero entrenado solo con datos anteriores al tramo de
    # calibración. Así sus probabilidades en 2021-22 son fuera de muestra, como lo serán en prueba. Responde a: ¿el
    # PROCEDIMIENTO de calibrar con la última temporada ayuda, cuando esa temporada es de verdad "no vista"?
    previo = train[train["date"] < INICIO_CALIB]
    sust = clone(modelo).fit(previo[cols], previo["target"], sample_weight=compute_sample_weight("balanced", previo["target"]))
    S_cal, S_te = sust.predict_proba(calib[cols]), sust.predict_proba(test[cols])
    print(f"\n== Modelo sustituto (entrenado con {len(previo)} partidos < {INICIO_CALIB}) ==")
    print(f"log-loss sustituto en tramo de calibración {log_loss(y_cal, S_cal, labels=[0, 1, 2]):.4f} (ya fuera de muestra) "
          f"| en prueba {log_loss(y_te, S_te, labels=[0, 1, 2]):.4f}")
    imprimir("Sustituto sin calibrar en prueba", metricas(S_te, y_te))
    sal_sust = {"Original": S_te}
    for nombre, ajustar in (("Isotónica", ajustar_isotonica), ("Platt", ajustar_platt)):
        sal_sust[nombre] = ajustar(S_cal, y_cal)(S_te)
        imprimir(f"Sustituto + {nombre} en prueba", metricas(sal_sust[nombre], y_te))
        d = -np.log(np.clip(sal_sust[nombre][np.arange(len(y_te)), y_te], EPS, 1)) + np.log(np.clip(S_te[np.arange(len(y_te)), y_te], EPS, 1))
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(2000)]
        print(f"    Δ log-loss ({nombre} − sustituto) = {d.mean():+.4f}  IC95 [{np.percentile(boots, 2.5):+.4f}, {np.percentile(boots, 97.5):+.4f}]")

    figura_fiabilidad(sal_sust, y_te, FIGURAS / "fiabilidad_sustituto.png",
                      "Modelo sustituto (fuera de muestra al calibrar): original vs. calibrado")
    figura_fiabilidad({"Original": P_te}, y_te, FIGURAS / "fiabilidad_original.png",
                      f"Curva de fiabilidad del modelo en prueba ({len(y_te)} partidos, {N_BINS} bins por cuantiles)")
    figura_fiabilidad(salidas, y_te, FIGURAS / "fiabilidad_calibrado.png",
                      "Fiabilidad en prueba: original vs. calibrado con la última temporada de entrenamiento")
    print(f"\nFiguras guardadas en {FIGURAS}")
    for nombre, P in salidas.items():
        print(f"\nBins ({nombre}):")
        for k, c in enumerate(NOMBRES):
            b = bins_cuantiles(P[:, k], (y_te == k).astype(float))
            print(f"    {c:<20}", " ".join(f"{a:.2f}/{f:.2f}" for a, f in zip(b["p_media"], b["frec"])))


if __name__ == "__main__":
    main()
