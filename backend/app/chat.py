"""Agente de conocimiento: responde preguntas de reglamento con RAG y cita sus fuentes (documento + página).

Flujo: pregunta -> retrieval.buscar (8 fragmentos) -> prompt -> LLM -> respuesta + fuentes.
"""
from __future__ import annotations

import logging
import os
import re
import time
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .retrieval import Fragmento, buscar

router = APIRouter(tags=["conocimiento"])
log = logging.getLogger("uvicorn.error")   # mismo logger que uvicorn para que el aviso salga en su consola

# Nombre legible de cada documento: es lo que verá el usuario como fuente (RF07).
NOMBRES_DOCUMENTO = {
    "normas_competicion": "Normas de Competición 2026/27",
    "reglas_juego": "Reglas de Juego IFAB 2026/27",
    "primera_division": "Wikipedia – Primera División",
    "clasico": "Wikipedia – El Clásico",
}
SIN_RESPUESTA = "No encontré esa información en los documentos disponibles."

# El prompt es la defensa contra las alucinaciones: el modelo solo puede usar los fragmentos y debe admitir cuando no sabe.
SISTEMA = f"""Eres el asistente de conocimiento de un sistema de analítica de LaLiga.
Respondes SOLO con la información de los FRAGMENTOS que se te entregan.
Reglas:
- Responde en español, de forma clara y breve (máximo 5 frases).
- Cita los fragmentos que uses con su número entre corchetes, por ejemplo [1] o [2][3].
- Si los fragmentos no contienen la respuesta, responde exactamente: "{SIN_RESPUESTA}" y no inventes nada.
- No uses conocimiento propio ni cifras que no aparezcan en los fragmentos."""


class ChatRequest(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=500, examples=["¿Cuántos suplentes se pueden usar en un partido?"])


class FuenteCitada(BaseModel):
    documento: str = Field(..., description="Nombre legible del documento")
    seccion: str = Field(..., description="Artículo, regla o sección (vacío en Wikipedia)")
    pagina: int | None = Field(None, description="Página del PDF; None si el documento no tiene páginas (Wikipedia)")
    texto: str = Field(..., description="Fragmento exacto que se le dio al modelo")


class ChatResponse(BaseModel):
    respuesta: str
    fuentes: list[FuenteCitada]
    fuente: Literal["agente_conocimiento"] = "agente_conocimiento"  # RF07: toda respuesta indica qué agente la produjo
    ms_busqueda: int
    ms_llm: int


@lru_cache(maxsize=1)
def crear_llm() -> BaseChatModel:
    """ÚNICO lugar donde se elige el proveedor del LLM. Cambiarlo es cambiar este bloque; el resto usa BaseChatModel."""
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0,   # reglamento: queremos la misma respuesta ante la misma pregunta
        # La GPU tiene 6 GB y el 7B no cabe entero: parte de las capas corre en CPU, que es lo que vuelve lento al LLM.
        # El KV-cache crece con num_ctx, así que un contexto menor libera VRAM y deja más capas en GPU.
        # Medición del 27/10/2026 (`ollama ps` + response_metadata):
        #   num_ctx 4096 -> 5,2 GB, 18 % CPU, 17,4-19,5 tok/s
        #   num_ctx 2048 -> 5,0 GB, 16 % CPU, 19,6-21,4 tok/s
        # El prompt más largo de las 11 preguntas de evaluar_frases fue de 1.532 tokens (1.636 contando la respuesta),
        # así que 2048 alcanza con margen. Si el prompt pasara de 2048, Ollama lo TRUNCA en silencio (perderíamos el
        # inicio, es decir, las instrucciones): hay que volver a medir si se sube k o el tamaño de chunk.
        num_ctx=2048,
        # Por defecto Ollama descarga el modelo a los 5 min sin uso y la siguiente petición paga la carga completa.
        keep_alive="30m",
    )


def calentar_llm() -> None:
    """Carga el modelo en memoria con la misma configuración que usará /chat (mismo num_ctx y mismo SISTEMA).

    Por qué: la primera llamada real paga la carga de ~5 GB a GPU/CPU; mejor pagarla al arrancar. Usamos el SISTEMA real
    para que Ollama deje su prefijo ya procesado. Nunca lanza: si Ollama no está, /chat dará 503 como siempre.
    """
    try:
        t0 = time.perf_counter()
        crear_llm().invoke([SystemMessage(content=SISTEMA), HumanMessage(content="FRAGMENTOS:\n\nPREGUNTA: hola")])
        log.info("LLM calentado en %.1f s", time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001 - el calentamiento es opcional, no debe tumbar el servidor
        log.warning("No se pudo calentar el LLM (¿Ollama apagado?): %s", e)


def _contexto(fragmentos: list[Fragmento]) -> str:
    bloques = []
    for n, f in enumerate(fragmentos, start=1):
        pag = f", pág. {f.pagina}" if f.pagina else ""
        bloques.append(f"[{n}] ({NOMBRES_DOCUMENTO.get(f.documento, f.documento)}{', ' + f.seccion if f.seccion else ''}{pag})\n{f.texto}")
    return "\n\n".join(bloques)


def _fuentes_usadas(respuesta: str, fragmentos: list[Fragmento]) -> list[Fragmento]:
    """Solo los fragmentos que el modelo citó con [n]. Si no citó ninguno (y sí respondió), devolvemos todos los consultados."""
    if SIN_RESPUESTA in respuesta:
        return []
    citados = [int(n) for n in re.findall(r"\[(\d+)\]", respuesta)]
    vistos = list(dict.fromkeys(n for n in citados if 1 <= n <= len(fragmentos)))   # únicos, en orden, solo válidos
    return [fragmentos[n - 1] for n in vistos] or fragmentos


@router.post("/chat", response_model=ChatResponse, summary="Pregunta sobre reglamento (agente de conocimiento)")
def chat(req: ChatRequest) -> ChatResponse:
    # `def` y no `async def`: buscar() y el LLM bloquean; FastAPI corre las funciones normales en un hilo aparte.
    t0 = time.perf_counter()
    try:
        fragmentos = buscar(req.pregunta)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    t1 = time.perf_counter()

    mensajes = [SystemMessage(content=SISTEMA),
                HumanMessage(content=f"FRAGMENTOS:\n{_contexto(fragmentos)}\n\nPREGUNTA: {req.pregunta}")]
    try:
        respuesta = str(crear_llm().invoke(mensajes).content).strip()
    except Exception as e:  # noqa: BLE001 - cualquier fallo de conexión/modelo se reporta igual al cliente
        raise HTTPException(status_code=503, detail="No se pudo consultar el LLM. ¿Ollama está corriendo y el modelo descargado?") from e
    t2 = time.perf_counter()

    fuentes = [FuenteCitada(documento=NOMBRES_DOCUMENTO.get(f.documento, f.documento), seccion=f.seccion,
                            pagina=f.pagina or None, texto=f.texto) for f in _fuentes_usadas(respuesta, fragmentos)]
    return ChatResponse(respuesta=respuesta, fuentes=fuentes,
                        ms_busqueda=round((t1 - t0) * 1000), ms_llm=round((t2 - t1) * 1000))
