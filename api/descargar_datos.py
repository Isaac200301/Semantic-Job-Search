"""
Descarga los archivos de datos necesarios (job_descriptions_clean.parquet y
job_id_template_map.parquet) desde Google Drive hacia ./data/, para no tener
que subirlos manualmente cada vez que se despliega la API.

Uso:
    1. En Google Drive, clic derecho sobre cada archivo -> "Obtener enlace" -> "Cualquiera con el enlace".
    2. Copia el ID del archivo (la parte del enlace entre /d/ y /view).
    3. Define las variables de entorno DRIVE_FILE_ID_CLEAN y DRIVE_FILE_ID_MAPEO
       (en tu archivo .env, o exportadas en la terminal).
    4. Corre: python descargar_datos.py

Si prefieres copiar los archivos a mano, simplemente ignora este script y
coloca los dos parquet directamente en ./data/.
"""
import os
from pathlib import Path

import gdown

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

ARCHIVOS = {
    "DRIVE_FILE_ID_CLEAN": DATA_DIR / "job_descriptions_clean.parquet",
    "DRIVE_FILE_ID_MAPEO": DATA_DIR / "job_id_template_map.parquet",
}


def main() -> None:
    for variable_entorno, destino in ARCHIVOS.items():
        file_id = os.environ.get(variable_entorno)
        if not file_id:
            print(f"[AVISO] {variable_entorno} no está definida, se omite {destino.name}.")
            continue
        if destino.exists():
            print(f"{destino.name} ya existe, se omite la descarga.")
            continue

        url = f"https://drive.google.com/uc?id={file_id}"
        print(f"Descargando {destino.name}...")
        gdown.download(url, str(destino), quiet=False)


if __name__ == "__main__":
    main()
