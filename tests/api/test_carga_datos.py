"""Pruebas de `search._cargar_dataset` y de los listados de filtros.

`_cargar_dataset` tiene tres caminos y los tres importan: el archivo reducido
que viaja en el repositorio, el respaldo que reconstruye la tabla desde los dos
parquet originales de Colab, y el error claro cuando no hay nada. Las pruebas
escriben sus propios parquet en tmp, nunca tocan los 424 MB reales.
"""
import pandas as pd
import pytest

from app import config, search


COLUMNAS_MINIMAS = {
    "Job Id": [1, 2, 3],
    "Job Title": ["Data Sci", "Backend", "Data Sci"],
    "Role": ["Analytics", "Platform", "Analytics"],
    "Country": ["Colombia", "Chile", "Colombia"],
    "Work Type": ["Full-Time", "Part-Time", "Contract"],
    "Salary Range": ["$60K-$80K", "$40K-$60K", "$70K-$90K"],
    "Experience": ["2 to 5", "0 to 2", "5 to 8"],
    "Company": ["Acme", "Globex", "Acme"],
    "experiencia_min": [2, 0, 5],
    "experiencia_max": [5, 2, 8],
    "salario_min": [60, 40, 70],
    "salario_max": [80, 60, 90],
}


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    """Redirige las tres rutas de datos a una carpeta temporal vacía."""
    destinos = {
        "RUTA_BUSQUEDA": tmp_path / "ofertas_busqueda.parquet",
        "RUTA_CLEAN": tmp_path / "job_descriptions_clean.parquet",
        "RUTA_MAPEO": tmp_path / "job_id_template_map.parquet",
    }
    for nombre, ruta in destinos.items():
        monkeypatch.setattr(config, nombre, ruta)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return destinos


# --- Camino preferido --------------------------------------------------------

def test_usa_el_parquet_reducido_cuando_existe(rutas):
    df = pd.DataFrame({**COLUMNAS_MINIMAS, "template_id": [10, 20, 10]})
    df.to_parquet(rutas["RUTA_BUSQUEDA"])

    cargado = search._cargar_dataset()

    assert len(cargado) == 3
    assert "template_id" in cargado.columns


def test_el_parquet_reducido_llega_ya_compactado(rutas):
    """Si no se compactara, el proceso volvería a pedir gigabytes de RAM."""
    df = pd.DataFrame({**COLUMNAS_MINIMAS, "template_id": [10, 20, 10]})
    df.to_parquet(rutas["RUTA_BUSQUEDA"])

    cargado = search._cargar_dataset()

    assert isinstance(cargado["Country"].dtype, pd.CategoricalDtype)
    assert cargado["template_id"].dtype.itemsize < 8


def test_el_reducido_tiene_prioridad_sobre_los_originales(rutas):
    """Con los tres archivos presentes debe ganar el de 27 MB, no los de 438."""
    pd.DataFrame({**COLUMNAS_MINIMAS, "template_id": [10, 20, 10]}).to_parquet(
        rutas["RUTA_BUSQUEDA"]
    )
    solo_una_fila = {clave: valor[:1] for clave, valor in COLUMNAS_MINIMAS.items()}
    pd.DataFrame(solo_una_fila).to_parquet(rutas["RUTA_CLEAN"])
    pd.DataFrame({"Job Id": [1], "template_id": [99]}).to_parquet(rutas["RUTA_MAPEO"])

    cargado = search._cargar_dataset()

    assert len(cargado) == 3, "cargó el respaldo en vez del archivo reducido"


# --- Camino de respaldo ------------------------------------------------------

def test_reconstruye_desde_los_dos_parquet_originales(rutas):
    pd.DataFrame(COLUMNAS_MINIMAS).to_parquet(rutas["RUTA_CLEAN"])
    pd.DataFrame({"Job Id": [1, 2, 3], "template_id": [10, 20, 10]}).to_parquet(
        rutas["RUTA_MAPEO"]
    )

    cargado = search._cargar_dataset()

    assert len(cargado) == 3
    assert cargado.sort_values("Job Id")["template_id"].tolist() == [10, 20, 10]


def test_el_respaldo_tambien_deja_la_tabla_compactada(rutas):
    pd.DataFrame(COLUMNAS_MINIMAS).to_parquet(rutas["RUTA_CLEAN"])
    pd.DataFrame({"Job Id": [1, 2, 3], "template_id": [10, 20, 10]}).to_parquet(
        rutas["RUTA_MAPEO"]
    )

    cargado = search._cargar_dataset()

    assert isinstance(cargado["Country"].dtype, pd.CategoricalDtype)


def test_el_respaldo_necesita_los_dos_archivos(rutas):
    """Con el mapeo ausente no se puede saber a qué plantilla va cada oferta."""
    pd.DataFrame(COLUMNAS_MINIMAS).to_parquet(rutas["RUTA_CLEAN"])

    with pytest.raises(FileNotFoundError):
        search._cargar_dataset()


# --- Sin datos ---------------------------------------------------------------

def test_sin_ningun_archivo_el_error_dice_que_falta_y_donde(rutas):
    """El mensaje es lo único que guía a un compañero que clona el repo."""
    with pytest.raises(FileNotFoundError) as error:
        search._cargar_dataset()

    mensaje = str(error.value)
    assert "ofertas_busqueda.parquet" in mensaje
    assert "README" in mensaje


# --- Listados que alimentan los selectores de la interfaz --------------------

@pytest.fixture
def datos_cargados(monkeypatch):
    tabla = pd.DataFrame(
        {
            "Country": ["Peru", "Colombia", "Colombia", None, "Chile"],
            "Work Type": ["Part-Time", "Full-Time", "Full-Time", "Contract", None],
        }
    )
    monkeypatch.setattr(search, "_df_clean", tabla)
    monkeypatch.setattr(search, "_modelo", object())
    monkeypatch.setattr(search, "_pinecone_index", object())
    return tabla


def test_listar_paises_sin_repetidos_y_en_orden(datos_cargados):
    assert search.listar_paises() == ["Chile", "Colombia", "Peru"]


def test_listar_modalidades_sin_repetidos_y_en_orden(datos_cargados):
    assert search.listar_modalidades() == ["Contract", "Full-Time", "Part-Time"]


def test_los_listados_no_incluyen_nulos(datos_cargados):
    """Un None colándose al selector de Streamlit rompería la interfaz."""
    assert all(p is not None for p in search.listar_paises())
    assert all(m is not None for m in search.listar_modalidades())


def test_los_listados_funcionan_sobre_una_tabla_compactada(monkeypatch):
    """Con dtype `category`, `unique()` devuelve un Categorical, no una lista."""
    tabla = search.compactar(
        pd.DataFrame(
            {
                "Country": ["Peru", "Colombia", "Colombia"],
                "Work Type": ["Part-Time", "Full-Time", "Full-Time"],
            }
        )
    )
    monkeypatch.setattr(search, "_df_clean", tabla)
    monkeypatch.setattr(search, "_modelo", object())
    monkeypatch.setattr(search, "_pinecone_index", object())

    assert search.listar_paises() == ["Colombia", "Peru"]
    assert search.listar_modalidades() == ["Full-Time", "Part-Time"]
