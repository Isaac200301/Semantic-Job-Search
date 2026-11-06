"""Configuración común a todas las pruebas.

Este archivo se importa antes que cualquier módulo de prueba, lo que permite
dejar el entorno listo antes de que se importe `app.config`, que lanza
RuntimeError si no encuentra PINECONE_API_KEY.

Ninguna prueba sale a la red: ni a Pinecone, ni a la API desplegada, ni a
Hugging Face a descargar el modelo. Todo lo externo se sustituye por dobles.
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Clave falsa a propósito. Se fija (no `setdefault`) para que, aunque el equipo
# tenga la clave real exportada en su shell, las pruebas nunca puedan usarla.
os.environ["PINECONE_API_KEY"] = "clave-de-prueba-no-real"
os.environ["PINECONE_INDEX_NAME"] = "indice-de-prueba"

# Carpeta inexistente: así ninguna prueba carga por accidente los parquet
# reales de api/data (424 MB). Las que necesitan datos crean los suyos en tmp.
os.environ["DATA_DIR"] = str(RAIZ / "tests" / "_sin_datos")

# `api/` y `frontend/` son dos raíces de importación distintas: la API importa
# el paquete `app`, y el frontend importa `api_client` como módulo suelto.
#
# El orden importa y no es arbitrario: existen a la vez el paquete `api/app/` y
# el módulo `frontend/app.py`, así que ambos reclaman el nombre `app`. Poniendo
# `api/` primero, `import app` resuelve al paquete de la API; el frontend solo
# necesita que `api_client` sea importable, y ese nombre no choca con nada.
# El script de Streamlit (`frontend/app.py`) no se importa nunca por su nombre:
# las pruebas de interfaz lo cargan por ruta con AppTest.
for carpeta in (RAIZ / "frontend", RAIZ / "api"):
    ruta_carpeta = str(carpeta)
    if ruta_carpeta in sys.path:
        sys.path.remove(ruta_carpeta)
    sys.path.insert(0, ruta_carpeta)
