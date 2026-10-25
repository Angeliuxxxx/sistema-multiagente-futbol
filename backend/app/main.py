"""API del sistema multiagente. Arranque: uvicorn app.main:app --reload (desde /backend)."""
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import prediction, retrieval
from .chat import router as chat_router
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Al arrancar: si falta el .pkl o el CSV, mejor fallar aquí que en la primera petición.
    prediction.cargar_modelo()
    prediction.cargar_team_matches()
    retrieval.cargar_indice()
    yield


app = FastAPI(title="Analítica LaLiga — Sistema Multiagente", version="0.1.0", lifespan=lifespan)

# CORS: el navegador bloquea que React (otro puerto) llame a esta API salvo que la autoricemos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # puerto por defecto de Vite
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # puerto por defecto de Vite
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)

class PredictRequest(BaseModel):
    local: str = Field(examples=["Barcelona"])
    visitante: str = Field(examples=["Real Madrid"])
    fecha: date | None = Field(default=None, description="Por defecto, hoy.")


class PredictResponse(BaseModel):
    fuente: Literal["agente_predictivo"] = "agente_predictivo"  # RF07: transparencia de fuente
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
def teams() -> list[str]:
    return prediction.equipos()


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> dict:
    validos = prediction.equipos()
    for nombre in (req.local, req.visitante):
        if nombre not in validos:
            raise HTTPException(404, f"Equipo '{nombre}' no encontrado. Consulta GET /teams.")
    try:
        r = prediction.predecir_partido(req.local, req.visitante, pd.Timestamp(req.fecha) if req.fecha else None)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"local": req.local, "visitante": req.visitante, **r}
