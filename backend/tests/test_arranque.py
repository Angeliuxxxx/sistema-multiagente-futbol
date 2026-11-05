"""Prueba de REGISTRAR_AL_ARRANCAR. Ejecutar desde backend/:  python -m tests.test_arranque"""
import os

from app import main


def test_registrar_al_arrancar_por_variable() -> None:
    antes = os.environ.get("REGISTRAR_AL_ARRANCAR")
    try:
        os.environ.pop("REGISTRAR_AL_ARRANCAR", None)
        assert main.registrar_al_arrancar() is True, "por defecto registra (como antes)"
        os.environ["REGISTRAR_AL_ARRANCAR"] = "1"
        assert main.registrar_al_arrancar() is True
        os.environ["REGISTRAR_AL_ARRANCAR"] = "0"
        assert main.registrar_al_arrancar() is False, "con 0 el arranque no registra"
    finally:  # restaurar: la variable es global del proceso
        if antes is None:
            os.environ.pop("REGISTRAR_AL_ARRANCAR", None)
        else:
            os.environ["REGISTRAR_AL_ARRANCAR"] = antes


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
