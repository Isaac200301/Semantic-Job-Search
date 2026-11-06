"""
Genera `data/ofertas_busqueda.parquet`: el único archivo de datos que la API
necesita en tiempo de ejecución.

¿Por qué existe este script?
----------------------------
`job_descriptions_clean.parquet` (444 MB) trae las 25 columnas del dataset,
incluidas `Job Description`, `texto_combinado`, `Company Profile` y `Benefits`,
que son enormes y que la búsqueda **nunca usa**. Cargarlas costaba 6,7 GB de RAM
y obligaba a descargar 438 MB desde Google Drive en cada despliegue.

Este script se queda solo con las 13 columnas que `app/search.py` realmente lee
y las guarda en un único parquet de ~27 MB, lo bastante pequeño para versionarlo
en el repositorio. El resultado de la búsqueda es idéntico: lo semántico ocurre
dentro de Pinecone, y este archivo solo sirve para expandir `template_id` a
ofertas reales, filtrar y mostrar.

Cuándo correrlo
---------------
Solo si cambia el dataset o el preprocesamiento (notebooks 02 y 03). El archivo
generado ya está versionado, así que en un clon normal no hace falta.

Uso:
    python generar_datos_busqueda.py

Requiere los dos parquet originales en `data/` (ver README.md, sección 4.3).
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"

RUTA_CLEAN = DATA_DIR / "job_descriptions_clean.parquet"
RUTA_MAPEO = DATA_DIR / "job_id_template_map.parquet"
RUTA_SALIDA = DATA_DIR / "ofertas_busqueda.parquet"

# Las únicas columnas que app/search.py toca: filtros, expansión y salida.
COLUMNAS = [
    # identificación y salida
    "Job Id",
    "Job Title",
    "Role",
    "Country",
    "Work Type",
    "Salary Range",
    "Experience",
    "Company",
    # filtros por rango
    "experiencia_min",
    "experiencia_max",
    "salario_min",
    "salario_max",
]

# Texto muy repetitivo: sobre 1,6 millones de filas hay solo unos cientos de
# valores distintos, así que `category` ahorra muchísimo.
CATEGORICAS = [
    "Job Title",
    "Role",
    "Country",
    "Work Type",
    "Salary Range",
    "Experience",
    "Company",
]

# Rangos pequeños que no justifican 64 bits.
ENTEROS_CORTOS = [
    "experiencia_min",
    "experiencia_max",
    "salario_min",
    "salario_max",
    "template_id",
]


def main() -> None:
    faltantes = [r.name for r in (RUTA_CLEAN, RUTA_MAPEO) if not r.exists()]
    if faltantes:
        raise SystemExit(
            f"Faltan los archivos de origen en {DATA_DIR}: {', '.join(faltantes)}. "
            "Descárgalos de Drive o corre descargar_datos.py (ver README.md)."
        )

    print(f"Leyendo {RUTA_CLEAN.name} (solo {len(COLUMNAS)} columnas)...")
    df = pd.read_parquet(RUTA_CLEAN, columns=COLUMNAS)

    print(f"Uniendo con {RUTA_MAPEO.name}...")
    mapeo = pd.read_parquet(RUTA_MAPEO)
    df = df.merge(mapeo, on="Job Id", how="left")

    sin_plantilla = int(df["template_id"].isna().sum())
    if sin_plantilla:
        print(f"[AVISO] {sin_plantilla:,} ofertas quedaron sin template_id tras el merge.")

    # Tipos compactos: las columnas de texto repetitivas como `category` y los
    # enteros de rango corto a 16/32 bits. Pandas guarda esta información en los
    # metadatos del parquet, así que al leerlo vuelven con el mismo tipo y la API
    # no gasta tiempo ni memoria reconvirtiéndolos.
    print("Compactando tipos...")
    antes_mb = df.memory_usage(deep=True).sum() / 1024**2
    for columna in CATEGORICAS:
        df[columna] = df[columna].astype("category")
    for columna in ENTEROS_CORTOS:
        df[columna] = pd.to_numeric(df[columna], downcast="integer")
    despues_mb = df.memory_usage(deep=True).sum() / 1024**2
    print(f"  en memoria: {antes_mb:.0f} MB -> {despues_mb:.0f} MB")

    print(f"Escribiendo {RUTA_SALIDA.name}...")
    df.to_parquet(RUTA_SALIDA, index=False, compression="zstd")

    mb_origen = (RUTA_CLEAN.stat().st_size + RUTA_MAPEO.stat().st_size) / 1024**2
    mb_salida = RUTA_SALIDA.stat().st_size / 1024**2
    print()
    print(f"Filas: {len(df):,} | Columnas: {df.shape[1]}")
    print(f"Origen (2 archivos): {mb_origen:7.1f} MB")
    print(f"Salida (1 archivo) : {mb_salida:7.1f} MB")


if __name__ == "__main__":
    main()
