"""
Configuración de la API, leída desde variables de entorno.

En local: crea un archivo .env (ver .env.example) y usa `python-dotenv`,
o exporta las variables directamente en tu shell.

En un despliegue en la nube se definen como variables del servicio.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Carga las variables definidas en el archivo .env (si existe) hacia el entorno.
# Si no hay archivo .env no hace nada: en un contenedor o en un servicio
# gestionado las variables ya vienen inyectadas en el entorno.
load_dotenv()

# --- Pinecone ---
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise RuntimeError(
        "Falta la variable de entorno PINECONE_API_KEY. "
        "Copia .env.example a .env, complétala con tu API key de Pinecone, "
        "y asegúrate de correr uvicorn desde la carpeta api/ (donde está el .env)."
    )
PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "ofertas-laborales")

# --- Modelo de embeddings ---
# Debe ser el mismo con el que se generaron los vectores subidos a Pinecone
# (decisión final tomada en 05_Evaluacion_Metricas.ipynb: all-MiniLM-L6-v2)
MODELO_EMBEDDINGS = os.environ.get("MODELO_EMBEDDINGS", "all-MiniLM-L6-v2")

# --- Datos locales ---
# Estos parquet se generan en 02_Preprocesamiento.ipynb y 03_Embeddings_BusquedaVectorial.ipynb
# y deben copiarse a esta carpeta antes de levantar la API (ver README.md y descargar_datos.py)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))

# Archivo preferido: solo las 13 columnas que la búsqueda usa (~27 MB).
# Se genera con generar_datos_busqueda.py y SÍ está versionado en el repositorio,
# para que el despliegue no dependa de descargar 438 MB desde Google Drive.
RUTA_BUSQUEDA = DATA_DIR / "ofertas_busqueda.parquet"

# Archivos originales de Colab (438 MB entre los dos). Solo se usan como respaldo
# si el reducido no está presente, y para regenerarlo.
RUTA_CLEAN = DATA_DIR / "job_descriptions_clean.parquet"
RUTA_MAPEO = DATA_DIR / "job_id_template_map.parquet"

# Columnas que app/search.py necesita. Leer solo estas baja el consumo del proceso
# de 6,7 GB a ~2,2 GB; el resto del dataset (Job Description, texto_combinado,
# Company Profile, Benefits...) no interviene en la búsqueda.
COLUMNAS_BUSQUEDA = [
    "Job Id",
    "Job Title",
    "Role",
    "Country",
    "Work Type",
    "Salary Range",
    "Experience",
    "Company",
    "experiencia_min",
    "experiencia_max",
    "salario_min",
    "salario_max",
]

# Columnas de texto muy repetitivas: sobre 1,6 millones de filas hay apenas unos
# cientos de valores distintos. Guardarlas como `category` (un diccionario de
# valores + índices) baja el dataframe de 304 MB a 42 MB, y con ello el proceso
# entero de 6,7 GB a menos de 1 GB.
COLUMNAS_CATEGORICAS = [
    "Job Title",
    "Role",
    "Country",
    "Work Type",
    "Salary Range",
    "Experience",
    "Company",
]

# Rangos pequeños que no necesitan 64 bits: experiencia va de 0 a ~25 años,
# salario en miles de USD, y template_id llega a 3.759.
COLUMNAS_ENTERO_CORTO = [
    "experiencia_min",
    "experiencia_max",
    "salario_min",
    "salario_max",
    "template_id",
]

# --- Límites de la API ---
MAX_K_PLANTILLAS = 20
MAX_RESULTADOS = 100
