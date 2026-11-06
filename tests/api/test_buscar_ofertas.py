"""Pruebas de `search.buscar_ofertas`, el corazón del motor.

El modelo de embeddings y Pinecone se sustituyen por dobles: lo que se prueba
aquí no es la calidad semántica (eso se midió con nDCG en el notebook 05), sino
la lógica que rodea a la búsqueda vectorial —expansión de plantillas a ofertas,
filtros, orden y recorte—, que es donde un error pasa desapercibido.
"""
import json

import numpy as np
import pandas as pd
import pytest

from app import search


class ModeloFalso:
    """Devuelve siempre el mismo vector; registra con qué texto se le llamó."""

    def __init__(self):
        self.consultas = []

    def encode(self, consulta, normalize_embeddings=True, convert_to_numpy=True):
        self.consultas.append(consulta)
        return np.zeros(384, dtype=np.float32)


class IndiceFalso:
    """Simula el índice de Pinecone devolviendo plantillas fijas."""

    def __init__(self, matches):
        self.matches = matches
        self.llamadas = []

    def query(self, vector, top_k, include_metadata=False):
        self.llamadas.append({"top_k": top_k, "include_metadata": include_metadata})
        return {"matches": self.matches[:top_k]}


MATCHES = [
    {"id": "10", "score": 0.90},
    {"id": "20", "score": 0.70},
]


def tabla() -> pd.DataFrame:
    """Cinco ofertas sobre tres plantillas; la 30 nunca la devuelve Pinecone."""
    return pd.DataFrame(
        {
            "Job Id": [1, 2, 3, 4, 5],
            "Job Title": ["Data Sci", "Data Sci", "Backend", "Backend", "Otro"],
            "Role": ["Analytics", "Analytics", "Platform", "Platform", "Varios"],
            "Country": ["Colombia", "Chile", "Colombia", "Peru", "Colombia"],
            "Work Type": ["Full-Time", "Part-Time", "Contract", "Full-Time", "Full-Time"],
            "Salary Range": ["$60K-$80K", "$40K-$60K", "$70K-$90K", "$50K-$70K", "$10K-$200K"],
            "Experience": ["2 to 5", "0 to 2", "5 to 8", "1 to 3", "0 to 10"],
            "Company": ["Acme", "Globex", "Acme", "Initech", "Umbrella"],
            "experiencia_min": [2, 0, 5, 1, 0],
            "experiencia_max": [5, 2, 8, 3, 10],
            "salario_min": [60, 40, 70, 50, 10],
            "salario_max": [80, 60, 90, 70, 200],
            "template_id": [10, 10, 20, 20, 30],
        }
    )


@pytest.fixture
def motor(monkeypatch):
    """Deja el módulo con recursos falsos ya cargados."""
    modelo = ModeloFalso()
    indice = IndiceFalso(MATCHES)
    monkeypatch.setattr(search, "_modelo", modelo)
    monkeypatch.setattr(search, "_pinecone_index", indice)
    monkeypatch.setattr(search, "_df_clean", tabla())
    return modelo, indice


def ids(resultados) -> list:
    return [r["Job Id"] for r in resultados]


# --- Estructura de la respuesta ---------------------------------------------

def test_devuelve_exactamente_las_columnas_del_contrato(motor):
    """El frontend y el schema OfertaResultado dependen de estos nombres."""
    resultados = search.buscar_ofertas("data scientist")

    assert resultados, "la búsqueda no devolvió nada"
    assert list(resultados[0].keys()) == [
        "Job Id", "Job Title", "Role", "Country", "Work Type",
        "Salary Range", "Experience", "Company", "similitud",
    ]


def test_solo_incluye_ofertas_de_las_plantillas_que_devolvio_pinecone(motor):
    """La oferta 5, de la plantilla 30, no debe aparecer nunca."""
    resultados = search.buscar_ofertas("data scientist")

    assert sorted(ids(resultados)) == [1, 2, 3, 4]


def test_cada_oferta_hereda_la_similitud_de_su_plantilla(motor):
    resultados = search.buscar_ofertas("data scientist")
    por_id = {r["Job Id"]: r["similitud"] for r in resultados}

    assert por_id[1] == pytest.approx(0.90)
    assert por_id[2] == pytest.approx(0.90)
    assert por_id[3] == pytest.approx(0.70)
    assert por_id[4] == pytest.approx(0.70)


def test_los_resultados_vienen_ordenados_por_similitud_descendente(motor):
    resultados = search.buscar_ofertas("data scientist")
    similitudes = [r["similitud"] for r in resultados]

    assert similitudes == sorted(similitudes, reverse=True)


def test_la_consulta_se_pasa_al_modelo_tal_cual(motor):
    modelo, _ = motor

    search.buscar_ofertas("ingeniero de datos con spark")

    assert modelo.consultas == ["ingeniero de datos con spark"]


def test_k_plantillas_se_reenvia_a_pinecone(motor):
    _, indice = motor

    search.buscar_ofertas("data scientist", k_plantillas=1)

    assert indice.llamadas[-1]["top_k"] == 1


def test_con_una_sola_plantilla_solo_salen_sus_ofertas(motor):
    resultados = search.buscar_ofertas("data scientist", k_plantillas=1)

    assert sorted(ids(resultados)) == [1, 2]


def test_max_resultados_recorta_sin_romper_el_orden(motor):
    resultados = search.buscar_ofertas("data scientist", max_resultados=2)

    assert len(resultados) == 2
    assert all(r["similitud"] == pytest.approx(0.90) for r in resultados)


# --- Filtros exactos ---------------------------------------------------------

def test_filtro_por_pais(motor):
    resultados = search.buscar_ofertas("x", pais="Colombia")

    assert sorted(ids(resultados)) == [1, 3]


def test_filtro_por_modalidad(motor):
    resultados = search.buscar_ofertas("x", modalidad="Full-Time")

    assert sorted(ids(resultados)) == [1, 4]


def test_el_filtro_de_pais_es_exacto_no_parcial(motor):
    """Un país a medio escribir no debe traer nada: el filtro es igualdad."""
    assert search.buscar_ofertas("x", pais="Colomb") == []


# --- Filtros por rango -------------------------------------------------------

def test_experiencia_devuelve_ofertas_cuyo_rango_contiene_al_candidato(motor):
    """Las ofertas 1 (2-5), 2 (0-2) y 4 (1-3) incluyen 2 años; la 3 (5-8) no."""
    resultados = search.buscar_ofertas("x", experiencia_min=2)

    assert sorted(ids(resultados)) == [1, 2, 4]


@pytest.mark.parametrize(
    "anios, esperados",
    [
        (0, [2]),
        (5, [1, 3]),
        (8, [3]),
        (30, []),
    ],
)
def test_los_extremos_del_rango_de_experiencia_se_incluyen(motor, anios, esperados):
    resultados = search.buscar_ofertas("x", experiencia_min=anios)

    assert sorted(ids(resultados)) == esperados


def test_salario_min_conserva_ofertas_cuyo_techo_alcanza(motor):
    """Pedir 75 deja la oferta 1, que llega a 80, y la 3, que llega a 90."""
    resultados = search.buscar_ofertas("x", salario_min=75)

    assert sorted(ids(resultados)) == [1, 3]


def test_salario_max_conserva_ofertas_cuyo_piso_no_lo_supera(motor):
    """Un techo de 45 solo admite la oferta 2, que empieza en 40."""
    resultados = search.buscar_ofertas("x", salario_max=45)

    assert sorted(ids(resultados)) == [2]


def test_banda_salarial_combinada(motor):
    resultados = search.buscar_ofertas("x", salario_min=55, salario_max=65)

    assert sorted(ids(resultados)) == [1, 2, 4]


# --- Casos límite ------------------------------------------------------------

def test_una_combinacion_imposible_devuelve_lista_vacia_no_error(motor):
    """Requisito de la interfaz: cero resultados es una respuesta válida."""
    resultados = search.buscar_ofertas("x", pais="Colombia", modalidad="Part-Time")

    assert resultados == []


def test_los_filtros_se_acumulan(motor):
    resultados = search.buscar_ofertas(
        "x", pais="Colombia", modalidad="Full-Time", experiencia_min=3, salario_min=70
    )

    assert ids(resultados) == [1]


def test_un_cero_no_se_trata_como_ausencia_de_filtro(motor):
    """experiencia_min=0 es un filtro real; confundirlo con None daría otra cosa."""
    con_cero = search.buscar_ofertas("x", experiencia_min=0)
    sin_filtro = search.buscar_ofertas("x")

    assert sorted(ids(con_cero)) == [2]
    assert sorted(ids(sin_filtro)) == [1, 2, 3, 4]


def test_sin_coincidencias_en_pinecone_no_hay_resultados(monkeypatch):
    monkeypatch.setattr(search, "_modelo", ModeloFalso())
    monkeypatch.setattr(search, "_pinecone_index", IndiceFalso([]))
    monkeypatch.setattr(search, "_df_clean", tabla())

    assert search.buscar_ofertas("algo que no existe") == []


def test_el_resultado_es_serializable_a_json(motor):
    """FastAPI tiene que poder devolverlo; un tipo de numpy reventaría aquí."""
    resultados = search.buscar_ofertas("x")

    json.dumps(resultados)


# --- La optimización de memoria no cambia los resultados ---------------------

def test_compactar_el_dataframe_no_altera_la_busqueda(monkeypatch):
    """Regresión del cambio que bajó la memoria de 6,7 GB a 700 MB.

    La misma consulta sobre la tabla original y sobre la compactada debe dar
    exactamente lo mismo; si `category` o el downcast rompieran un filtro, se
    vería aquí y no en producción.
    """
    monkeypatch.setattr(search, "_modelo", ModeloFalso())
    monkeypatch.setattr(search, "_pinecone_index", IndiceFalso(MATCHES))

    monkeypatch.setattr(search, "_df_clean", tabla())
    sin_compactar = search.buscar_ofertas("x", pais="Colombia", experiencia_min=2)

    monkeypatch.setattr(search, "_df_clean", search.compactar(tabla()))
    compactada = search.buscar_ofertas("x", pais="Colombia", experiencia_min=2)

    assert sin_compactar == compactada
