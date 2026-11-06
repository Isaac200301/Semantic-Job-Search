"""Pruebas de los esquemas Pydantic (`app/schemas.py`).

Son la primera línea de defensa de la API: todo lo que validan aquí es trabajo
que `buscar_ofertas` no tiene que repetir, y cada límite que se respeta evita
una consulta cara o un 500. También fijan el contrato de nombres con alias
(`Job Id`, `Job Title`...) del que depende el frontend.
"""
import pytest
from pydantic import ValidationError

from app import config
from app.schemas import OfertaResultado, RespuestaBusqueda, SolicitudBusqueda


# --- SolicitudBusqueda: valores por defecto ---------------------------------

def test_solo_la_consulta_es_obligatoria():
    solicitud = SolicitudBusqueda(consulta="data scientist")

    assert solicitud.k_plantillas == 5
    assert solicitud.max_resultados == 20
    assert solicitud.pais is None
    assert solicitud.modalidad is None
    assert solicitud.experiencia_min is None
    assert solicitud.salario_min is None
    assert solicitud.salario_max is None


def test_sin_consulta_no_hay_solicitud_valida():
    with pytest.raises(ValidationError):
        SolicitudBusqueda()


# --- SolicitudBusqueda: límites ---------------------------------------------

@pytest.mark.parametrize("texto", ["", "a"])
def test_rechaza_consultas_demasiado_cortas(texto):
    """Menos de dos caracteres no da una búsqueda semántica con sentido."""
    with pytest.raises(ValidationError):
        SolicitudBusqueda(consulta=texto)


def test_acepta_la_consulta_mas_corta_permitida():
    assert SolicitudBusqueda(consulta="ab").consulta == "ab"


@pytest.mark.parametrize("valor", [1, 5, config.MAX_K_PLANTILLAS])
def test_k_plantillas_dentro_del_rango(valor):
    assert SolicitudBusqueda(consulta="x y", k_plantillas=valor).k_plantillas == valor


@pytest.mark.parametrize("valor", [0, -1, config.MAX_K_PLANTILLAS + 1])
def test_k_plantillas_fuera_del_rango(valor):
    """El tope protege a Pinecone de consultas innecesariamente anchas."""
    with pytest.raises(ValidationError):
        SolicitudBusqueda(consulta="x y", k_plantillas=valor)


@pytest.mark.parametrize("valor", [1, 20, config.MAX_RESULTADOS])
def test_max_resultados_dentro_del_rango(valor):
    assert SolicitudBusqueda(consulta="x y", max_resultados=valor).max_resultados == valor


@pytest.mark.parametrize("valor", [0, -5, config.MAX_RESULTADOS + 1])
def test_max_resultados_fuera_del_rango(valor):
    with pytest.raises(ValidationError):
        SolicitudBusqueda(consulta="x y", max_resultados=valor)


@pytest.mark.parametrize(
    "campo", ["experiencia_min", "salario_min", "salario_max"]
)
def test_los_campos_numericos_no_admiten_negativos(campo):
    with pytest.raises(ValidationError):
        SolicitudBusqueda(consulta="x y", **{campo: -1})


@pytest.mark.parametrize(
    "campo", ["experiencia_min", "salario_min", "salario_max"]
)
def test_cero_si_es_un_valor_valido(campo):
    """Cero es un filtro legítimo (sin experiencia, salario desde 0)."""
    solicitud = SolicitudBusqueda(consulta="x y", **{campo: 0})

    assert getattr(solicitud, campo) == 0


def test_los_limites_salen_de_config_no_estan_escritos_a_mano():
    """Si alguien sube el tope en config, el esquema debe seguirlo solo."""
    assert config.MAX_K_PLANTILLAS == 20
    assert config.MAX_RESULTADOS == 100


# --- OfertaResultado: contrato de nombres con el frontend --------------------

OFERTA = {
    "Job Id": 123,
    "Job Title": "Data Scientist",
    "Role": "Analytics",
    "Country": "Colombia",
    "Work Type": "Full-Time",
    "Salary Range": "$60K-$80K",
    "Experience": "2 to 5 Years",
    "Company": "Acme",
    "similitud": 0.87,
}


def test_se_construye_desde_los_nombres_con_espacios():
    oferta = OfertaResultado(**OFERTA)

    assert oferta.job_id == 123
    assert oferta.job_title == "Data Scientist"
    assert oferta.work_type == "Full-Time"


def test_tambien_se_construye_desde_los_nombres_en_snake_case():
    """`populate_by_name` permite ambas formas; el frontend acepta las dos."""
    oferta = OfertaResultado(
        job_id=1, job_title="Backend", role="Platform", country="Chile",
        work_type="Contract", salary_range="$40K", experience="1 to 3",
        company="Globex", similitud=0.5,
    )

    assert oferta.job_id == 1


def test_al_serializar_por_alias_salen_los_nombres_con_espacios():
    """Es lo que realmente viaja por HTTP y lo que lee la tabla del frontend."""
    datos = OfertaResultado(**OFERTA).model_dump(by_alias=True)

    assert datos["Job Id"] == 123
    assert datos["Job Title"] == "Data Scientist"
    assert "job_id" not in datos


def test_el_job_id_se_convierte_a_entero():
    oferta = OfertaResultado(**{**OFERTA, "Job Id": "456"})

    assert oferta.job_id == 456


def test_una_oferta_sin_similitud_es_invalida():
    incompleta = {clave: valor for clave, valor in OFERTA.items() if clave != "similitud"}

    with pytest.raises(ValidationError):
        OfertaResultado(**incompleta)


# --- RespuestaBusqueda -------------------------------------------------------

def test_la_respuesta_envuelve_consulta_total_y_resultados():
    respuesta = RespuestaBusqueda(
        consulta="data scientist", total_resultados=1, resultados=[OFERTA]
    )

    assert respuesta.consulta == "data scientist"
    assert respuesta.total_resultados == 1
    assert respuesta.resultados[0].job_title == "Data Scientist"


def test_una_respuesta_sin_resultados_es_valida():
    respuesta = RespuestaBusqueda(consulta="x", total_resultados=0, resultados=[])

    assert respuesta.resultados == []
