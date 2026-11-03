"""API del sistema multiagente. Arranque: uvicorn app.main:app --reload (desde /backend)."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import calendario, prediction, prediction_b, retrieval
from .chat import calentar_llm, router as chat_router
from .orquestador import router as orquestador_router


def _calentar() -> None:
    # En ese orden y no en paralelo: si el retrieval se calienta mientras Ollama carga ~5 GB, la carga desaloja de la
    # memoria los pesos del modelo de embeddings y la primera pregunta real vuelve a pagar esos ~4 s.
    calentar_llm()
    retrieval.calentar()


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
    probabilidades: dict[str, float]
    resultado_probable: str
    forma_local: dict[str, float]
    forma_visitante: dict[str, float]
    datos_hasta: str


@app.get("/health")
def health() -> dict:
    return {"estado": "ok"}


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
    return {"datos_hasta": str(prediction_b.datos_hasta().date())}
