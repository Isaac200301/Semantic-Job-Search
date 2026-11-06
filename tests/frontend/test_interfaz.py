"""Pruebas de la interfaz de Streamlit (`frontend/app.py`) con AppTest.

AppTest ejecuta el script completo en un runtime simulado: no abre navegador ni
servidor, pero recorre el mismo código que ve el usuario. La API se sustituye
por dobles en `api_client`, así que estas pruebas no necesitan ni Cloud Run ni
Pinecone.

Cubren los dos fallos que aparecieron durante el desarrollo y que las pruebas
anteriores no veían: el recuadro rojo de "No secrets found" y la excepción al
pulsar un botón de consulta de ejemplo.
"""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import api_client


APP = str(Path(__file__).resolve().parents[2] / "frontend" / "app.py")

PAISES = ["Chile", "Colombia", "Peru"]
MODALIDADES = ["Contract", "Full-Time", "Part-Time"]

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


@pytest.fixture(autouse=True)
def sin_cache():
    """Las listas de filtros se cachean 300 s; sin limpiar, una prueba contagia a la siguiente."""
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def api(monkeypatch):
    """Sustituye la API por dobles y registra las búsquedas que se le piden."""
    estado = {
        "salud": (True, "API conectada (12 ms)"),
        "resultados": [OFERTA],
        "error": None,
        "busquedas": [],
    }

    def verificar_estado(url_base):
        return estado["salud"]

    def buscar(url_base, consulta, **kwargs):
        estado["busquedas"].append({"url": url_base, "consulta": consulta, **kwargs})
        if estado["error"] is not None:
            raise estado["error"]
        return api_client.ResultadoBusqueda(
            consulta=consulta,
            total_resultados=len(estado["resultados"]),
            resultados=estado["resultados"],
            peticion_enviada={"consulta": consulta},
            duracion_ms=42.0,
        )

    monkeypatch.setattr(api_client, "verificar_estado", verificar_estado)
    monkeypatch.setattr(api_client, "obtener_paises", lambda url: PAISES)
    monkeypatch.setattr(api_client, "obtener_modalidades", lambda url: MODALIDADES)
    monkeypatch.setattr(api_client, "buscar", buscar)
    monkeypatch.setenv("API_URL", "http://api-de-prueba:8000")
    return estado


def arrancar(timeout=30) -> AppTest:
    prueba = AppTest.from_file(APP, default_timeout=timeout)
    prueba.run()
    return prueba


def boton_buscar(prueba):
    """El botón del formulario, no los de la barra lateral ni los de ejemplo.

    No basta con tomar el último de `prueba.button`: ahí dentro conviven el
    botón del formulario, los cinco de consultas de ejemplo y el de reintentar
    conexión de la barra lateral.
    """
    return next(b for b in prueba.button if b.label == "Buscar ofertas")


def botones_de_ejemplo(prueba):
    """Los cinco botones de consulta de ejemplo, por su `key` 'ej_...'."""
    return [b for b in prueba.button if "-ej_" in b.proto.id]


# --- Arranque ----------------------------------------------------------------

def test_la_app_arranca_sin_excepciones(api):
    prueba = arrancar()

    assert not prueba.exception


def test_no_aparece_ningun_error_al_arrancar(api):
    """Regresión del recuadro rojo 'No secrets found' al correr en local."""
    prueba = arrancar()

    assert prueba.error == []


def test_los_selectores_se_llenan_desde_la_api(api):
    prueba = arrancar()

    opciones_pais = prueba.selectbox[0].options
    opciones_modalidad = prueba.selectbox[1].options
    assert PAISES[0] in opciones_pais
    assert MODALIDADES[0] in opciones_modalidad


def test_al_arrancar_invita_a_buscar(api):
    prueba = arrancar()

    assert any("Buscar ofertas" in info.value for info in prueba.info)


# --- API caída ---------------------------------------------------------------

def test_si_la_api_esta_caida_se_avisa_y_se_bloquea_la_busqueda(api):
    api["salud"] = (False, "No se pudo conectar con la API")

    prueba = arrancar()

    assert not prueba.exception
    assert any("No se pudo conectar" in e.value for e in prueba.error)
    assert boton_buscar(prueba).proto.disabled


# --- Consultas de ejemplo ----------------------------------------------------

def test_pulsar_una_consulta_de_ejemplo_rellena_el_campo(api):
    """Regresión: esto lanzaba StreamlitAPIException al modificar session_state."""
    prueba = arrancar()
    botones = botones_de_ejemplo(prueba)

    assert len(botones) == 5, "se esperaban cinco consultas de ejemplo"
    botones[0].click().run()

    assert not prueba.exception
    assert prueba.session_state.consulta


@pytest.mark.parametrize("indice", [0, 1, 2, 3, 4])
def test_todos_los_botones_de_ejemplo_funcionan(api, indice):
    prueba = arrancar()
    botones_de_ejemplo(prueba)[indice].click().run()

    assert not prueba.exception


# --- Búsqueda ----------------------------------------------------------------

def test_una_busqueda_pinta_los_resultados(api):
    prueba = arrancar()

    boton_buscar(prueba).click().run()

    assert not prueba.exception
    assert any("oferta" in s.value for s in prueba.subheader)


def test_la_tabla_de_resultados_se_construye(api):
    prueba = arrancar()

    boton_buscar(prueba).click().run()

    assert len(prueba.dataframe) == 1
    assert "Cargo" in prueba.dataframe[0].value.columns


def test_cero_resultados_se_explica_sin_romper(api):
    api["resultados"] = []

    prueba = arrancar()
    boton_buscar(prueba).click().run()

    assert not prueba.exception
    assert any("no devolvió ofertas" in i.value for i in prueba.info)


def test_un_error_de_la_api_se_muestra_y_la_app_sigue_viva(api):
    api["error"] = api_client.ErrorAPI("La API no respondió en 120 s")

    prueba = arrancar()
    boton_buscar(prueba).click().run()

    assert not prueba.exception
    assert any("120 s" in e.value for e in prueba.error)


def test_una_consulta_demasiado_corta_avisa_antes_de_llamar(api):
    """Se valida en el cliente para no gastar una petición de 120 s."""
    prueba = arrancar()
    prueba.session_state.consulta = "a"

    boton_buscar(prueba).click().run()

    assert api["busquedas"] == []
    assert any("2 caracteres" in w.value for w in prueba.warning)


# --- Filtros -----------------------------------------------------------------

def test_sin_filtros_activos_no_se_envia_ninguno(api):
    prueba = arrancar()

    boton_buscar(prueba).click().run()

    enviado = api["busquedas"][-1]
    assert enviado["pais"] is None
    assert enviado["modalidad"] is None
    assert enviado["experiencia_min"] is None
    assert enviado["salario_min"] is None


def test_elegir_pais_lo_envia_a_la_api(api):
    prueba = arrancar()
    prueba.selectbox[0].select("Colombia").run()

    boton_buscar(prueba).click().run()

    assert api["busquedas"][-1]["pais"] == "Colombia"


def test_la_experiencia_solo_viaja_si_se_activa_la_casilla(api):
    prueba = arrancar()
    prueba.checkbox[0].check().run()

    boton_buscar(prueba).click().run()

    assert api["busquedas"][-1]["experiencia_min"] is not None


def test_el_salario_viaja_como_rango(api):
    prueba = arrancar()
    prueba.checkbox[1].check().run()

    boton_buscar(prueba).click().run()

    enviado = api["busquedas"][-1]
    assert enviado["salario_min"] is not None
    assert enviado["salario_max"] >= enviado["salario_min"]


# --- URL de la API -----------------------------------------------------------

def test_la_url_se_toma_de_la_variable_de_entorno(api):
    prueba = arrancar()

    assert prueba.session_state.api_url == "http://api-de-prueba:8000"


def test_una_url_sin_esquema_se_completa_con_https(api):
    """Pegar 'mi-api.run.app' a mano tiene que funcionar igual."""
    prueba = arrancar()
    prueba.text_input(key="api_url").set_value("mi-api.run.app").run()

    boton_buscar(prueba).click().run()

    assert api["busquedas"][-1]["url"] == "https://mi-api.run.app"


def test_una_url_vacia_cae_a_localhost(api):
    prueba = arrancar()
    prueba.text_input(key="api_url").set_value("").run()

    boton_buscar(prueba).click().run()

    assert api["busquedas"][-1]["url"] == "http://localhost:8000"
