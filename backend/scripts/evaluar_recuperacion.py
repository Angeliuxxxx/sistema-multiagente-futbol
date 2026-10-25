"""Reproduce la evaluación del notebook 05 con el código del backend (app/retrieval.py).

Si este script da 16/17 (como el notebook), sabemos que al pasar el código del notebook al backend no se rompió nada.
Ejecutar desde la carpeta backend/:  python -m scripts.evaluar_recuperacion
"""
from app.retrieval import buscar

PREGUNTAS = [
    ("¿Cuántos suplentes se pueden usar en un partido?",              'normas_competicion', ['Art. 25']),
    ("¿Cuántas sustituciones puede hacer cada equipo?",               'normas_competicion', ['Art. 25']),
    ("¿Cómo funciona la sustitución por conmoción cerebral?",         'normas_competicion', ['Art. 25']),
    ("¿Cuántos equipos descienden de Primera División?",              'normas_competicion', ['Art. 8']),
    ("¿Cuántos puntos se dan por una victoria?",                      'normas_competicion', ['Art. 7']),
    ("¿Cuántos equipos participan en Primera División?",              'normas_competicion', ['Art. 6']),
    ("¿Cómo se desempata si dos equipos terminan con los mismos puntos?", 'normas_competicion', ['Art. 10', 'Art. 17']),
    ("¿Cuántas amonestaciones llevan a una suspensión?",              'normas_competicion', ['Art. 34']),
    ("¿Cuántos futbolistas extranjeros no comunitarios puede inscribir un club?", 'normas_competicion', ['Art. 22']),
    ("¿Cuándo abre el periodo de inscripción de licencias de invierno?", 'normas_competicion', ['Art. 23']),
    ("¿En qué horarios se juegan los partidos del sábado?",           'normas_competicion', ['Art. 31']),
    ("¿Qué es el fuera de juego?",                                    'reglas_juego', ['Regla 11']),
    ("¿Cuánto dura un partido?",                                      'reglas_juego', ['Regla 7']),
    ("¿Cómo se ejecuta un penal?",                                    'reglas_juego', ['Regla 14', 'Regla 12']),
    ("¿Qué es un saque de esquina?",                                  'reglas_juego', ['Regla 17']),
    ("¿Para qué sirve el VAR?",                                       'reglas_juego', ['VAR']),
    ("¿Qué es El Clásico entre el Barcelona y el Real Madrid?",       'clasico', ['']),
]

if __name__ == "__main__":
    aciertos = 0
    for q, doc_esperado, subcadenas in PREGUNTAS:
        frags = buscar(q)
        ok = any(f.documento == doc_esperado and any(s in f.seccion for s in subcadenas) for f in frags)
        aciertos += ok
        print(("✔" if ok else "✘"), q)
    print(f"\nHit@{len(frags)}: {aciertos}/{len(PREGUNTAS)}  (el notebook 05 dio 16/17)")
