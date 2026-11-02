"""SIN RAG vs CON RAG: ¿cuánto aporta recuperar fragmentos?

Las mismas 11 preguntas de evaluar_frases se hacen (a) al qwen2.5:7b directamente, sin fragmentos y con un prompt neutro,
y (b) al sistema completo (/chat). El acierto se mide igual en ambos: ¿aparece el hecho clave en la respuesta? (mismas
variantes HECHOS y mismo _contiene que evaluar_respuestas, para que la comparación sea justa).

Aviso: el hecho clave es una cifra corta ("tres", "20"); un modelo sin contexto puede acertarla por azar o por
conocimiento general (p. ej. 20 equipos en Primera). Lo que RAG añade además es la cita; eso no entra en esta métrica.
Y el reglamento es el de 2026/27, posterior al conocimiento del modelo: sin RAG no puede conocer artículos concretos.

Requiere el servidor y Ollama corriendo. Ejecutar desde backend/:  python -m scripts.evaluar_sin_rag [--url ...]
"""
import argparse
import time

from langchain_core.messages import HumanMessage, SystemMessage

from app.chat import crear_llm
from scripts.evaluar_frases import CASOS
from scripts.evaluar_respuestas import HECHOS, _chat, _contiene

# Prompt NEUTRO: no menciona fragmentos, ni citas, ni "di que no sabes". Es lo que haría un usuario con el LLM a pelo.
SISTEMA_NEUTRO = "Eres un asistente experto en fútbol. Responde en español, de forma clara y breve (máximo 5 frases)."


def sin_rag(pregunta: str) -> tuple[str, int]:
    # Mismo objeto LLM que usa el sistema (mismo modelo, temperature=0, num_ctx=2048): solo cambia el contexto.
    t0 = time.perf_counter()
    r = crear_llm().invoke([SystemMessage(content=SISTEMA_NEUTRO), HumanMessage(content=pregunta)])
    return str(r.content).strip(), round((time.perf_counter() - t0) * 1000)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    url = ap.parse_args().url.rstrip("/")

    sin_rag("hola")   # calentamiento: que la carga del modelo no cuente en los ms de la primera pregunta
    filas = []
    for (pregunta, _, _), variantes in zip(CASOS, HECHOS):
        r_sin, ms_sin = sin_rag(pregunta)
        r_con = _chat(url, pregunta)
        filas.append(dict(p=pregunta, ok_sin=any(_contiene(r_sin, v) for v in variantes), ms_sin=ms_sin, r_sin=r_sin,
                          ok_con=any(_contiene(r_con["respuesta"], v) for v in variantes),
                          ms_con=r_con["ms_busqueda"] + r_con["ms_llm"], r_con=r_con["respuesta"]))

    print("| Pregunta | Sin RAG | ms | Con RAG | ms |\n|---|---|---|---|---|")
    for f in filas:
        print(f"| {f['p']} | {'✔' if f['ok_sin'] else '✘'} | {f['ms_sin']} | {'✔' if f['ok_con'] else '✘'} | {f['ms_con']} |")
    n = len(filas)
    print(f"\nSin RAG: {sum(f['ok_sin'] for f in filas)}/{n}, {sum(f['ms_sin'] for f in filas) // n} ms medio | "
          f"Con RAG: {sum(f['ok_con'] for f in filas)}/{n}, {sum(f['ms_con'] for f in filas) // n} ms medio (búsqueda + LLM)")
    for f in filas:
        print(f"\n- {f['p']}\n  SIN: {f['r_sin']}\n  CON: {f['r_con']}")


if __name__ == "__main__":
    main()
