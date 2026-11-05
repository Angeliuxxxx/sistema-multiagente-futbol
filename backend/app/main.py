"""API del sistema multiagente. Arranque: uvicorn app.main:app --reload (desde /backend)."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import calendario, clasificacion, prediction, prediction_b, registro, retrieval
from .chat import calentar_llm, router as chat_router
from .orquestador import router as orquestador_router


def _calentar() -> None:
    # En ese orden y no en paralelo: si el retrieval se calienta mientras Ollama carga ~5 GB, la carga desaloja de la
    # memoria los pesos del modelo de embeddings y la primera pregunta real vuelve a pagar esos ~4 s.
    calentar_llm()
    retrieval.calentar()


def _registrar_sin_romper() -> None:
    try:
        registro.registrar()
    except Exception:  # noqa: BLE001 — sin red o sin token el registro puede fallar y la API debe seguir sirviendo
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Al arrancar: si falta el .pkl o el CSV, mejor fallar aquí que en la primera petición.
    prediction.cargar_modelo()
    prediction.cargar_team_matches()
    prediction_b.cargar_modelo_b()
    prediction_b.cargar_tabla()
    retrieval.cargar_indice()
    # Los calentamientos tardan segundos: van en un hilo aparte para que /health y /predict respondan desde el primer instante.
    # Guardamos la tarea en una variable: asyncio solo guarda referencias débiles y podría recolectarla a medias.
    calentamiento = asyncio.create_task(asyncio.to_thread(_calentar))
    # Registra los pronósticos de los próximos partidos al arrancar (idempotente): si nadie lo hace a mano, no se pierde ninguno.
    asyncio.create_task(asyncio.to_thread(_registrar_sin_romper))
    yield
    calentamiento.cancel()


app = FastAPI(title="Analítica LaLiga — Sistema Multiagente", version="0.1.0", lifespan=lifespan)

# CORS: el navegador bloquea que React (otro puerto) llame a esta API salvo que la autoricemos.
app.add_middleware(
    CORSMiddleware,
    # Puerto por defecto de Vite. Se listan localhost Y 127.0.0.1: para CORS son orígenes distintos aunque sean la misma máquina.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(orquestador_router)

class PredictRequest(BaseModel):
    local: str = Field(examples=["Barcelona"])
    visitante: str = Field(examples=["Real Madrid"])
    fecha: date | None = Field(default=None, description="Modelo B: por defecto, la fecha del partido en el calendario o, si no está, el día siguiente al último dato. Modelo A: 7 días después del último dato (mayo de 2025); sin hora se asume 17:30, o la real si ese día hubo partido.")
    modelo: Literal["a", "b"] = Field(default="b", description="`b` (por defecto): sin xG/PPDA, con datos hasta ayer. `a`: con xG y PPDA, datos hasta mayo de 2025.")


class PredictResponse(BaseModel):
    fuente: Literal["agente_predictivo"] = "agente_predictivo"  # RF07: transparencia de fuente
    modelo: Literal["a", "b"]
    local: str
    visitante: str
    fecha: str
    fecha_origen: Literal["usuario", "calendario", "por_defecto"] | None = Field(None, description="De dónde salió la fecha (solo modelo B)")
    probabilidades: dict[str, float]
    resultado_probable: str
    forma_local: dict[str, float]
    forma_visitante: dict[str, float]
    datos_hasta: str
    aviso: str | None = Field(None, description="Solo modelo B: presente si `fecha` es anterior o igual a `datos_hasta`. El modelo final ya vio ese partido al entrenar, así que el resultado no es una predicción fuera de muestra.")


@app.get("/health")
def health() -> dict:
    # La interfaz pinta «datos hasta…» con este valor: así no queda una fecha escrita a mano que se desactualiza.
    return {"estado": "ok", "datos_hasta": str(prediction_b.datos_hasta().date())}


@app.get("/teams")
def teams(modelo: Literal["a", "b"] = "b") -> list[str]:
    return prediction.equipos(modelo)


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> dict:
    validos = prediction.equipos(req.modelo)
    for nombre in (req.local, req.visitante):
        if nombre not in validos:
            raise HTTPException(404, f"Equipo '{nombre}' no encontrado. Consulta GET /teams.")
    try:
        r = prediction.predecir_partido(req.local, req.visitante, pd.Timestamp(req.fecha) if req.fecha else None, req.modelo)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"local": req.local, "visitante": req.visitante, **r}


class PartidoProximo(BaseModel):
    fecha: str = Field(description="Inicio del partido (UTC, ISO 8601)")
    jornada: int | None
    local: str
    visitante: str
    probabilidades: dict[str, float]
    resultado_probable: str


@app.get("/proximos", response_model=list[PartidoProximo], summary="Próximos partidos con su pronóstico (modelo B)")
def proximos(n: int = Query(10, ge=1, le=20)) -> list[dict]:
    out = []
    for p in calendario.proximos(n):
        try:
            r = prediction_b.predecir_partido_b(p["local"], p["visitante"], pd.Timestamp(p["fecha"]).tz_localize(None))
        except ValueError:
            continue  # equipo sin historial: mejor omitir el partido que inventar un pronóstico
        out.append({**p, "probabilidades": r["probabilidades"], "resultado_probable": r["resultado_probable"]})
    return out


@app.post("/actualizar", summary="Vuelve a leer la API y recalcula la forma con los partidos de ayer")
def actualizar() -> dict:
    prediction_b.refrescar()
    _registrar_sin_romper()
    return {"datos_hasta": str(prediction_b.datos_hasta().date())}


class FilaTabla(BaseModel):
    posicion: int
    equipo: str
    pj: int
    g: int
    e: int
    p: int
    gf: int
    gc: int
    dg: int
    pts: int
    forma: str = Field(description="Últimos 5 resultados, del más antiguo al más reciente: V, E, D")


@app.get("/tabla", response_model=list[FilaTabla], summary="Tabla de posiciones de la temporada en curso")
def tabla() -> list[dict]:
    return clasificacion.tabla()


class PartidoRegistrado(BaseModel):
    registrado_en: str = Field(description="Cuándo se guardó el pronóstico (UTC); siempre anterior al inicio del partido")
    inicio_partido: str
    jornada: int | None
    local: str
    visitante: str
    probabilidades: dict[str, float]
    resultado: str | None = Field(None, description="Clase real si el partido ya se jugó")
    acierto: bool | None = None
    log_loss: float | None = None


class ResumenRegistro(BaseModel):
    registrados: int
    jugados: int
    minimo_para_concluir: int
    concluyente: bool = Field(description="False mientras haya menos partidos jugados que `minimo_para_concluir`")
    aciertos: int | None = None
    acierto_pct: float | None = None
    log_loss: float | None = None
    log_loss_frecuencia: float | None = Field(None, description="Log-loss de pronosticar solo con la frecuencia de clases")
    brier: float | None = None
    diferencia: float | None = Field(None, description="log_loss − log_loss_frecuencia; negativo = el modelo es mejor")
    error_2e: float | None = Field(None, description="Dos errores estándar de `diferencia`; si incluye 0, no hay diferencia demostrable")


class RespuestaRegistro(BaseModel):
    resumen: ResumenRegistro
    partidos: list[PartidoRegistrado]


@app.get("/registro", response_model=RespuestaRegistro, summary="Pronósticos registrados antes de cada partido y su acierto")
def ver_registro() -> dict:
    filas = registro.puntuar()
    return {"resumen": registro.resumen(filas), "partidos": sorted(filas, key=lambda f: f["inicio_partido"], reverse=True)}
