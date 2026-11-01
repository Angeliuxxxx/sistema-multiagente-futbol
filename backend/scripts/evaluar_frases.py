"""Evaluación por FRASE CLAVE: ¿el texto que contiene la respuesta llegó a los fragmentos que verá el LLM?

Por qué existe: evaluar_recuperacion.py cuenta un acierto si llega CUALQUIER chunk de la sección correcta. Con la pregunta
de "suplentes" llegó el chunk del Art. 25 sobre conmoción cerebral, no el que dice "doce futbolistas": acierto en la métrica,
respuesta equivocada del LLM. Aquí el acierto exige que aparezca la frase que contiene la respuesta.

Ejecutar desde backend/:  python -m scripts.evaluar_frases
"""
from app.retrieval import Fragmento, buscar

# (pregunta, frase que contiene la respuesta, texto que debe tener la sección del fragmento; '' = cualquiera)
CASOS = [
    ("¿Cuántos suplentes se pueden usar en un partido?",                          "de doce futbolistas", "Art. 25"),
    ("¿Cuántas sustituciones puede hacer cada equipo?",                           "cinco futbolistas suplentes", "Art. 25"),
    ("¿Cómo funciona la sustitución por conmoción cerebral?",                     "única sustitución por conmoción cerebral", "Art. 25"),
    ("¿Cuántos equipos descienden de Primera División?",                          "posiciones 18ª, 19ª y 20ª", "Art. 8"),
    ("¿Cuántos puntos se dan por una victoria?",                                  "tres puntos por partido ganado", "Art. 7"),
    ("¿Cuántos equipos participan en Primera División?",                          "en veinte clubes", "Art. 6"),
    ("¿Cómo se desempata si dos equipos terminan con los mismos puntos?",         "partidos disputados entre ellos", "Art. 10"),
    ("¿Cuántas amonestaciones llevan a una suspensión?",                          "cinco amonestaciones", "Art. 34"),
    ("¿Cuántos futbolistas extranjeros no comunitarios puede inscribir un club?", "tres futbolistas extranjeros no comunitarios", "Art. 22"),
    ("¿Cuándo abre el periodo de inscripción de licencias de invierno?",          "2 de enero de 2027", "Art. 23"),
    ("¿En qué horarios se juegan los partidos del sábado?",                       "Sábados y domingos en horario comprendido entre las 12:00", "Art. 31"),
]


# Alcance (solo Primera salvo que la pregunta mencione "segunda"). Art. 10 (Primera) y Art. 17 (Segunda) son casi idénticos,
# así que el desempate es el caso donde se nota. Formato: (pregunta, frase, sección que DEBE aparecer, sección que NO debe aparecer)
CASOS_ALCANCE = [
    ("¿Cómo se desempata en Segunda División si dos equipos terminan con los mismos puntos?",
     "partidos disputados entre ellos", "Art. 17", None),
    ("¿Cómo se desempata si dos equipos terminan con los mismos puntos?", None, None, "Art. 17"),
]


def _norm(t: str) -> str:
    return " ".join(t.split())  # el PDF parte líneas: comparamos sin saltos ni dobles espacios


def evaluar(buscar_fn=buscar, nombre: str = "retrieval.buscar") -> int:
    aciertos = 0
    for pregunta, frase, seccion in CASOS:
        frags: list[Fragmento] = buscar_fn(pregunta)
        pos = next((i for i, f in enumerate(frags, 1) if seccion in f.seccion and frase in _norm(f.texto)), None)
        aciertos += pos is not None
        print(f"{'✔ pos ' + str(pos) if pos else '✘      '} | {pregunta}")
    print(f"\n{nombre}: frase clave en los {len(frags)} fragmentos -> {aciertos}/{len(CASOS)}")

    ok_alcance = 0
    for pregunta, frase, debe, no_debe in CASOS_ALCANCE:
        frags = buscar_fn(pregunta)
        ok = (debe is None or any(debe in f.seccion and frase in _norm(f.texto) for f in frags)) \
            and not (no_debe and any(no_debe in f.seccion for f in frags))
        ok_alcance += ok
        print(f"{'✔' if ok else '✘'} alcance | {pregunta}")
    print(f"{nombre}: casos de alcance -> {ok_alcance}/{len(CASOS_ALCANCE)}")
    return aciertos + ok_alcance


if __name__ == "__main__":
    evaluar()
