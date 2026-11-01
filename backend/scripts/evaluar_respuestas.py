"""Evaluación de RESPUESTAS: ¿el hecho clave aparece en el texto que devuelve /chat, no solo en los fragmentos?

Por qué existe: evaluar_frases.py mide si la frase llega al contexto del LLM, pero el LLM aún puede ignorarla o citar mal.
Aquí se pregunta de verdad por /chat y se busca el hecho en la respuesta final.

Requiere el servidor y Ollama corriendo. Ejecutar desde backend/:
    uvicorn app.main:app            (en otra terminal)
    python -m scripts.evaluar_respuestas [--url http://localhost:8000]
"""
import argparse
import json
import re
import unicodedata
import urllib.request

from scripts.evaluar_frases import CASOS

# Hecho clave por pregunta, en el MISMO orden que CASOS (se comprueba abajo). Basta con que aparezca UNA de las
# variantes: el modelo puede escribir "doce" o "12". Se comparan sin acentos ni mayúsculas.
HECHOS: list[tuple[str, ...]] = [
    ("doce", "12"),                                  # suplentes: lista de doce futbolistas
    ("cinco", "5"),                                  # sustituciones: cinco
    ("unica", "una sola", "una sustitucion"),        # conmoción: una única sustitución adicional
    ("18", "19", "20", "tres"),                      # descenso: posiciones 18ª, 19ª y 20ª
    ("tres puntos", "3 puntos"),                     # victoria
    ("veinte", "20"),                                # clubes en Primera
    ("diferencia de goles", "entre ellos", "enfrentamientos directos"),   # desempate
    ("cinco", "5"),                                  # amonestaciones
    ("tres", "3"),                                   # extranjeros no comunitarios
    ("2 de enero", "2 enero"),                       # inicio del periodo de invierno
    ("12:00", "12 horas", "12h"),                    # sábados: desde las 12:00
]
assert len(HECHOS) == len(CASOS), "HECHOS y CASOS deben tener la misma longitud y orden"


def _plano(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _contiene(respuesta: str, variante: str) -> bool:
    # Los números sueltos ("5", "12") con bordes de palabra: que "12" no acierte con "2026/27" ni "5" con "15".
    return re.search(rf"(?<![\w:]){re.escape(variante)}(?![\w:])", _plano(respuesta)) is not None


def _chat(url: str, pregunta: str) -> dict:
    req = urllib.request.Request(f"{url}/chat", data=json.dumps({"pregunta": pregunta}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    url = ap.parse_args().url.rstrip("/")

    filas, aciertos = [], 0
    for (pregunta, _, _), variantes in zip(CASOS, HECHOS):
        r = _chat(url, pregunta)
        ok = any(_contiene(r["respuesta"], v) for v in variantes)
        aciertos += ok
        fuentes = ", ".join(dict.fromkeys(
            (m.group(0) if (m := re.match(r"(Art\. \d+|Regla \d+)", f["seccion"])) else f["documento"])
            + (f" p.{f['pagina']}" if f["pagina"] else "")
            for f in r["fuentes"])) or "—"
        filas.append(("✔" if ok else "✘", r["ms_llm"], fuentes, pregunta, r["respuesta"]))

    print(f"{'':2}{'ms_llm':>7}  {'fuentes citadas':<46} pregunta")
    for ok, ms, fuentes, pregunta, _ in filas:
        print(f"{ok:2}{ms:>7}  {fuentes[:46]:<46} {pregunta}")
    print(f"\nHecho clave en la respuesta: {aciertos}/{len(CASOS)}   ms_llm medio: {sum(f[1] for f in filas) // len(filas)}")
    fallos = [f for f in filas if f[0] == "✘"]
    for _, _, _, pregunta, respuesta in fallos:   # lo que dijo el modelo, para distinguir fallo real de hecho mal formulado
        print(f"\n✘ {pregunta}\n  -> {respuesta}")


if __name__ == "__main__":
    main()
