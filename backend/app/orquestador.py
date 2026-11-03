"""Orquestador: enruta una pregunta en lenguaje natural al agente predictivo o al de conocimiento.

El router es SOLO reglas (sin LLM): es determinista, tarda microsegundos, se evalúa con una matriz de confusión y
cuando falla se sabe qué regla corregir. Ver docs/diseno_orquestador.md.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import prediction
from .chat import FuenteCitada, responder_conocimiento

router = APIRouter(tags=["orquestador"])

Ruta = Literal["prediccion", "conocimiento", "aclarar", "fuera_de_alcance"]


def _plano(t: str) -> str:
    """Minúsculas y sin tildes: 'Atlético' y 'atletico' deben ser lo mismo. Los signos se vuelven espacios."""
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "   # espacios en los bordes: ' gana ' no casa con 'ganando'


# --- Equipos -----------------------------------------------------------------------------------------------------
# Los nombres reales (/teams) vienen de prediction.equipos_conocidos(); estos alias cubren cómo los escribe la gente.
# Alias -> nombre real. "madrid" suelto es el Real Madrid (quien dice "el Madrid" no habla del Atlético).
ALIAS: dict[str, str] = {
    "barca": "Barcelona", "fc barcelona": "Barcelona", "blaugrana": "Barcelona", "culé": "Barcelona", "cule": "Barcelona",
    "madrid": "Real Madrid", "merengues": "Real Madrid", "real madrid": "Real Madrid",
    "atleti": "Atletico Madrid", "atletico": "Atletico Madrid", "atletico de madrid": "Atletico Madrid",
    "athletic": "Athletic Club", "athletic bilbao": "Athletic Club", "bilbao": "Athletic Club",
    "betis": "Real Betis", "la real": "Real Sociedad", "sociedad": "Real Sociedad", "real sociedad": "Real Sociedad",
    "celta": "Celta Vigo", "rayo": "Rayo Vallecano", "valladolid": "Real Valladolid", "pucela": "Real Valladolid",
    "depor": "Deportivo La Coruna", "deportivo": "Deportivo La Coruna", "espanol": "Espanyol",
    "huesca": "SD Huesca", "sporting": "Sporting Gijon", "gijon": "Sporting Gijon", "palmas": "Las Palmas",
    "alaves": "Alaves", "submarino amarillo": "Villarreal",
}


def _patrones_equipos(equipos: list[str]) -> list[tuple[re.Pattern, str]]:
    """(patrón, nombre real) ordenados del alias más largo al más corto.

    Por qué el orden: 'atletico madrid' contiene 'madrid'; si probáramos 'madrid' primero, 'el Atlético de Madrid'
    contaría como Real Madrid. Al consumir el texto ya reconocido (ver detectar_equipos) lo largo gana.
    """
    alias = {_plano(e).strip(): e for e in equipos}
    alias |= {_plano(a).strip(): e for a, e in ALIAS.items() if e in equipos}
    return [(re.compile(rf" {re.escape(a)} "), e) for a, e in sorted(alias.items(), key=lambda kv: -len(kv[0]))]


def detectar_equipos(pregunta: str, equipos: list[str]) -> list[str]:
    """Equipos mencionados, en el orden en que aparecen en la pregunta y sin repetir."""
    texto = _plano(pregunta)
    halladas: list[tuple[int, str]] = []
    for patron, equipo in _patrones_equipos(equipos):
        while (m := patron.search(texto)):
            halladas.append((m.start(), equipo))
            # Se tapa lo reconocido con espacios del mismo largo: no se reutiliza y las posiciones siguen valiendo.
            texto = texto[:m.start()] + " " * (m.end() - m.start()) + texto[m.end():]
    vistos: list[str] = []
    for _, e in sorted(halladas):
        if e not in vistos:
            vistos.append(e)
    return vistos


# --- Señales -----------------------------------------------------------------------------------------------------
# Todas se buscan sobre el texto ya sin tildes. Los '\b' evitan que 'gana' case dentro de otra palabra.
# Verbos en futuro/presente/subjuntivo; el pasado ('ganó' -> 'gano') NO es predicción: es un dato histórico.
SENAL_PREDICCION = re.compile(
    r"\b(gana|ganara|ganaria|ganar|gane|ganen|ganan|ganador|vence|vencera|vencer|pierde|perdera|empatan|empatara|"
    r"prediccion|predecir|predices|pronostico|pronosticas|probabilidad|probabilidades|favorito|"
    r"que resultado|como ve|como le ira|como van|cuota|cuotas)\b")
# Reglamento, liga e historia del fútbol: lo que sí cubre el corpus (Normas, Reglas IFAB, Wikipedia).
SENAL_CONOCIMIENTO = re.compile(
    r"\b(suplentes?|sustituci\w+|cambios?|fuera de juego|offside|penal\w*|tarjetas?|amonestaci\w+|expulsi\w+|"
    r"reglas?|reglamento|normas?|articulo|arbitros?|var|saque\w*|corner|esquina|descien\w+|ascen\w+|asciende\w*|"
    r"puntos? (?:se |por |que )?(?:dan|otorga\w*|conceden|por)|desempat\w+|licencias?|inscri\w+|extranjeros?|comunitari\w+|duracion|dura|horarios?|jornadas?|"
    r"prorroga|falta|faltas|balon|clasico|historia|origen|fundad\w+|primera division|segunda division|laliga|la liga)\b")
CLASICO = re.compile(r"\bclasico\b")
# Estadísticas de un equipo (puntos que lleva, goles, tabla): ningún agente las tiene, el corpus es de reglamento y
# el modelo solo predice partidos. 'puntos' a secas ya NO cuenta como reglamento (arriba solo 'puntos se dan/por…').
SENAL_ESTADISTICA = re.compile(r"\b(puntos|goles|tabla|posicion|posiciones)\b")
# Dos equipos unidos por vs / contra / guion ('Barcelona vs Madrid') es el formato típico de un partido, aunque no
# haya verbo de pronóstico. Se busca sobre el texto ORIGINAL en minúsculas porque _plano convierte el guion en espacio.
CONECTOR_PARTIDO = re.compile(r"\b(?:vs|v/s|contra)\b|\s[-–—]\s")


@dataclass
class Decision:
    ruta: Ruta
    motivo: str
    equipos: list[str] = field(default_factory=list)


def enrutar(pregunta: str, equipos_validos: list[str] | None = None) -> Decision:
    """Decide a qué agente va la pregunta. Reglas en orden de PRIORIDAD: gana la primera que se cumple."""
    equipos_validos = equipos_validos if equipos_validos is not None else prediction.equipos_conocidos()
    texto = _plano(pregunta)
    equipos = detectar_equipos(pregunta, equipos_validos)
    pred = bool(SENAL_PREDICCION.search(texto))
    conoc = bool(SENAL_CONOCIMIENTO.search(texto))

    # R1: dos equipos + señal de predicción. Va primero porque es lo único que el agente predictivo puede resolver
    # y es la combinación más específica (aunque haya palabras como 'puntos', la intención es pronosticar).
    if len(equipos) >= 2 and pred:
        return Decision("prediccion", f"Mencionas dos equipos ({equipos[0]} y {equipos[1]}) y pides un pronóstico.", equipos[:2])

    # R1b: dos equipos unidos por vs/contra/guion y SIN vocabulario de reglamento -> el formato 'A vs B' ya es un partido.
    # Sin 'conoc' para no robarle a R5 casos como 'tarjetas del Barça contra el Madrid'.
    if len(equipos) >= 2 and not conoc and CONECTOR_PARTIDO.search(pregunta.lower()):
        return Decision("prediccion", f"Nombras un partido ({equipos[0]} contra {equipos[1]}).", equipos[:2])

    # R2: 'el clásico' implica Barcelona-Real Madrid aunque no se nombren; solo si hay señal de predicción
    # ('¿cuándo fue el primer clásico?' es historia y cae en R5).
    if CLASICO.search(texto) and pred and len(equipos) < 2:
        return Decision("prediccion", "El clásico es Barcelona contra Real Madrid y pides un pronóstico.",
                        ["Barcelona", "Real Madrid"])

    # R3: un solo equipo + señal de predicción: falta el rival, el modelo necesita un partido (local y visitante).
    if len(equipos) == 1 and pred:
        return Decision("aclarar", f"Pides un pronóstico de {equipos[0]} pero falta el rival.", equipos)

    # R4: quiere pronóstico, pero no dice de qué equipos. Si además trae vocabulario de reglamento ('puntos por
    # ganar'), se deja pasar a R5: es una duda de reglas, no un pronóstico.
    if pred and not conoc:
        return Decision("aclarar", "Pides un pronóstico pero no indicas ningún equipo.", [])

    # R4b: un equipo + estadística ('puntos del Madrid') y sin reglamento -> nadie la cubre. Va antes de R5 para que
    # ninguna palabra suelta (puntos, tabla) mande una estadística al RAG, que contestaría "no encontré" tras 4 s de LLM.
    if len(equipos) == 1 and SENAL_ESTADISTICA.search(texto) and not conoc:
        return Decision("fuera_de_alcance", f"Pides una estadística de {equipos[0]}, que ningún agente tiene.", equipos)

    # R5: vocabulario de reglamento, liga o historia -> RAG. Con o sin equipos: 'origen del Clásico entre
    # Barcelona y Real Madrid' nombra dos equipos pero NO pide predicción.
    if conoc:
        return Decision("conocimiento", "La pregunta trata de reglamento, competición o historia del fútbol.", equipos)

    # R6: nada que ningún agente cubra (saludos, estadísticas de jugadores, otros temas).
    return Decision("fuera_de_alcance", "No es un pronóstico entre dos equipos ni una duda de reglamento o historia.", equipos)


# --- API ---------------------------------------------------------------------------------------------------------
class PreguntarRequest(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=500, examples=["¿Quién gana el Barcelona contra el Real Madrid?"])
    fecha: date | None = Field(None, description="Fecha del partido a predecir. Por defecto, justo después del último dato disponible.")


class Probabilidades(BaseModel):
    # Nombres cortos para la interfaz; prediction.py usa victoria_local/victoria_visitante y se traduce en un solo sitio.
    local: float = Field(..., description="Probabilidad de victoria local (0-1)")
    empate: float = Field(..., description="Probabilidad de empate (0-1)")
    visitante: float = Field(..., description="Probabilidad de victoria visitante (0-1)")


class PrediccionDetalle(BaseModel):
    """Predicción estructurada para que la interfaz dibuje barras y gráficas sin interpretar el texto de `respuesta`."""
    local: str
    visitante: str
    probabilidades: Probabilidades
    fecha_forma: str = Field(..., description="La forma se calculó con los 5 partidos anteriores a esta fecha")
    datos_hasta: str = Field(..., description="Fecha del último dato disponible")
    modelo: Literal["a", "b"] = Field("b", description="Qué modelo produjo la predicción")
    fecha_origen: Literal["usuario", "calendario", "por_defecto"] | None = Field(None, description="De dónde salió la fecha (solo modelo B)")
    forma_local: dict[str, float]
    forma_visitante: dict[str, float]


class PreguntarResponse(BaseModel):
    respuesta: str
    ruta: Ruta = Field(..., description="Qué decidió el orquestador")
    motivo: str = Field(..., description="Por qué eligió esa ruta (la regla que se cumplió)")
    fuente: Literal["agente_predictivo", "agente_conocimiento", "orquestador"] = Field(
        ..., description="Quién produjo la respuesta (RF07)")
    equipos: list[str] = Field(default_factory=list, description="Equipos detectados; el primero se toma como local")
    fuentes: list[FuenteCitada] = Field(default_factory=list, description="Documento y página, solo en conocimiento")
    probabilidades: dict[str, float] | None = Field(None, description="Solo en predicción")
    datos_hasta: str | None = Field(None, description="Fecha del último dato con que se calculó la forma (solo en predicción)")
    prediccion: PrediccionDetalle | None = Field(None, description="Detalle estructurado; solo cuando la ruta es prediccion")
    ms_total: int


def _responder_prediccion(local: str, visitante: str, fecha: date | None) -> tuple[str, PrediccionDetalle]:
    # Sin fecha del usuario, el modelo B usa la del partido en el calendario o, si no está, el día siguiente al último dato.
    f = pd.Timestamp(fecha) if fecha else None
    r = prediction.predecir_partido(local, visitante, f)
    p = r["probabilidades"]
    pct = lambda k: f"{p[k] * 100:.1f} %"   # noqa: E731
    cuando = f"con la forma de sus últimos 5 partidos antes del {r['fecha']}"
    # Se avisa SIEMPRE de dónde terminan los datos. En el modelo B terminan ayer; en A, en mayo de 2025.
    cuando += f" (datos hasta el {r['datos_hasta']})"
    texto = (f"Predicción {local} (local) vs {visitante} (visitante), {cuando}: "
             f"victoria de {local} {pct('victoria_local')}, empate {pct('empate')}, victoria de {visitante} {pct('victoria_visitante')}. "
             f"Tomé como local al primer equipo que nombraste.")
    detalle = PrediccionDetalle(
        local=local, visitante=visitante, fecha_forma=r["fecha"], datos_hasta=r["datos_hasta"],
        probabilidades=Probabilidades(local=p["victoria_local"], empate=p["empate"], visitante=p["victoria_visitante"]),
        modelo=r["modelo"], fecha_origen=r.get("fecha_origen"), forma_local=r["forma_local"], forma_visitante=r["forma_visitante"])
    return texto, detalle


@router.post("/preguntar", response_model=PreguntarResponse, summary="Pregunta en lenguaje natural (orquestador)")
def preguntar(req: PreguntarRequest) -> PreguntarResponse:
    # `def` y no `async def`: el modelo y el LLM bloquean, FastAPI los corre en un hilo aparte.
    t0 = time.perf_counter()
    d = enrutar(req.pregunta)
    base = dict(ruta=d.ruta, motivo=d.motivo, equipos=d.equipos)
    ms = lambda: round((time.perf_counter() - t0) * 1000)   # noqa: E731

    if d.ruta == "prediccion":
        texto, det = _responder_prediccion(d.equipos[0], d.equipos[1], req.fecha)
        return PreguntarResponse(respuesta=texto, fuente="agente_predictivo", prediccion=det, datos_hasta=det.datos_hasta,
                                 probabilidades={"victoria_local": det.probabilidades.local, "empate": det.probabilidades.empate,
                                                 "victoria_visitante": det.probabilidades.visitante},
                                 ms_total=ms(), **base)
    if d.ruta == "conocimiento":
        r = responder_conocimiento(req.pregunta)
        return PreguntarResponse(respuesta=r.respuesta, fuente="agente_conocimiento", fuentes=r.fuentes, ms_total=ms(), **base)
    if d.ruta == "aclarar":
        texto = ("Para pronosticar necesito los dos equipos del partido, por ejemplo: "
                 "«¿Quién gana el Barcelona contra el Real Madrid?».")
    else:
        texto = ("Solo puedo ayudarte con pronósticos de un partido entre dos equipos de LaLiga "
                 "o con dudas de reglamento, competición e historia.")
    return PreguntarResponse(respuesta=texto, fuente="orquestador", ms_total=ms(), **base)
