"""Pruebas de `search.compactar`.

Esta función es la que redujo el dataframe de 304 MB a 42 MB. Su requisito
irrenunciable es que NO cambie ningún valor: solo el tipo con el que se guarda.
Un fallo aquí no se vería como un error, se vería como resultados mal.
"""
import pandas as pd
import pytest

from app import search


def tabla_de_ejemplo() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Job Id": [1, 2, 3, 4],
            "Job Title": ["Data Scientist", "Data Scientist", "Backend Dev", "Backend Dev"],
            "Role": ["Analytics", "Analytics", "Platform", "Platform"],
            "Country": ["Colombia", "Chile", "Colombia", "Chile"],
            "Work Type": ["Full-Time", "Part-Time", "Full-Time", "Contract"],
            "Salary Range": ["$60K-$80K", "$40K-$60K", "$70K-$90K", "$50K-$70K"],
            "Experience": ["2 to 5 Years", "0 to 2 Years", "5 to 8 Years", "1 to 3 Years"],
            "Company": ["Acme", "Globex", "Acme", "Initech"],
            "experiencia_min": [2, 0, 5, 1],
            "experiencia_max": [5, 2, 8, 3],
            "salario_min": [60, 40, 70, 50],
            "salario_max": [80, 60, 90, 70],
            "template_id": [10, 10, 3759, 3759],
        }
    )


def test_las_columnas_de_texto_repetitivo_pasan_a_category():
    df = search.compactar(tabla_de_ejemplo())

    for columna in ["Job Title", "Role", "Country", "Work Type",
                    "Salary Range", "Experience", "Company"]:
        assert isinstance(df[columna].dtype, pd.CategoricalDtype), columna


def test_los_enteros_de_rango_corto_bajan_de_64_bits():
    original = tabla_de_ejemplo()
    df = search.compactar(original.copy())

    for columna in ["experiencia_min", "experiencia_max",
                    "salario_min", "salario_max", "template_id"]:
        assert df[columna].dtype.itemsize < 8, (
            f"{columna} sigue ocupando {df[columna].dtype.itemsize} bytes"
        )


def test_ningun_valor_cambia():
    """El punto crítico: compactar es un cambio de representación, no de datos."""
    original = tabla_de_ejemplo()
    compactada = search.compactar(original.copy())

    assert list(compactada.columns) == list(original.columns)
    for columna in original.columns:
        esperado = original[columna].tolist()
        obtenido = compactada[columna].tolist()
        assert obtenido == esperado, f"la columna {columna} cambió de valores"


def test_es_idempotente():
    """Aplicarla dos veces debe dar exactamente lo mismo que aplicarla una."""
    una_vez = search.compactar(tabla_de_ejemplo())
    dos_veces = search.compactar(search.compactar(tabla_de_ejemplo()))

    pd.testing.assert_frame_equal(una_vez, dos_veces)


def test_tolera_que_falten_columnas():
    """El camino de respaldo arma la tabla con un merge y puede traer menos columnas."""
    parcial = pd.DataFrame({"Country": ["Colombia"], "salario_min": [60]})

    df = search.compactar(parcial)

    assert isinstance(df["Country"].dtype, pd.CategoricalDtype)
    assert df["salario_min"].dtype.itemsize < 8


def test_devuelve_el_mismo_objeto_no_una_copia():
    """Se modifica en el sitio; duplicar 1,6 millones de filas anularía el ahorro."""
    df = tabla_de_ejemplo()

    assert search.compactar(df) is df


@pytest.mark.parametrize("valor_nulo", [None, float("nan")])
def test_conserva_los_nulos_de_texto(valor_nulo):
    df = pd.DataFrame({"Country": ["Colombia", valor_nulo]})

    resultado = search.compactar(df)

    assert resultado["Country"].isna().sum() == 1
