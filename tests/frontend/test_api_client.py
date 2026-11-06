"""Pruebas de `frontend/api_client.py`.

Este módulo es el único punto por el que el frontend habla con la API, así que
aquí se cubren sobre todo los caminos de error: timeout, API caída, 500, JSON
roto y URL mal escrita. Son situaciones que la API real no produce a demanda y
que, sin embargo, son las que el jurado puede provocar en vivo.

Nada sale a la red: se sustituye `requests.request` por un doble.
"""
import json

import pytest
import requests

import api_client


URL = "http://api-de-prueba:8000"


class RespuestaFalsa:
    """Imita lo justo de `requests.Response` que usa el módulo."""

    def __init__(self, status_code=200, cuerpo=None, texto=None, json_roto=False):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self._json_roto = json_roto
        self.text = texto if texto is not None else json.dumps(cuerpo)

    def json(self):
        if self._json_roto:
            raise ValueError("no es JSON")
        return self._cuerpo


@pytest.fixture
def peticiones(monkeypatch):
    """Captura las llamadas salientes y deja elegir qué responder."""
    registro = {"llamadas": [], "respuesta": RespuestaFalsa(cuerpo={}), "excepcion": None}

    def falsa(metodo, url, json=None, timeout=None):
        registro["llamadas"].append(
            {"metodo": metodo, "url": url, "cuerpo": json, "timeout": timeout}
        )
        if registro["excepcion"] is not None:
            raise registro["excepcion"]
        return registro["respuesta"]

    monkeypatch.setattr(requests, "request", falsa)
    return registro


# --- Construcción de la URL --------------------------------------------------

def test_la_barra_final_de_la_url_no_duplica_la_ruta(peticiones):
    """Pegar la URL con barra final desde la barra lateral es lo normal."""
    api_client.verificar_estado("http://api-de-prueba:8000/")

    assert peticiones["llamadas"][0]["url"] == "http://api-de-prueba:8000/health"


def test_cada_endpoint_pega_a_su_ruta(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=[])
    api_client.obtener_paises(URL)
    api_client.obtener_modalidades(URL)

    rutas = [llamada["url"] for llamada in peticiones["llamadas"]]
    assert rutas == [f"{URL}/filtros/paises", f"{URL}/filtros/modalidades"]


# --- Timeouts ----------------------------------------------------------------

def test_la_busqueda_usa_un_timeout_mas_largo_que_el_resto(peticiones):
    """La primera búsqueda espera al arranque en frío de Cloud Run."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"status": "ok"})
    api_client.verificar_estado(URL)
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"resultados": []})
    api_client.buscar(URL, "data scientist")

    assert peticiones["llamadas"][0]["timeout"] == api_client.TIMEOUT_RAPIDO
    assert peticiones["llamadas"][1]["timeout"] == api_client.TIMEOUT_BUSQUEDA
    assert api_client.TIMEOUT_BUSQUEDA > api_client.TIMEOUT_RAPIDO


# --- Traducción de errores de red -------------------------------------------

def test_un_timeout_se_explica_mencionando_los_segundos(peticiones):
    peticiones["excepcion"] = requests.exceptions.Timeout()

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert str(api_client.TIMEOUT_RAPIDO) in str(error.value)


def test_una_api_caida_sugiere_revisar_la_url(peticiones):
    peticiones["excepcion"] = requests.exceptions.ConnectionError()

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert "API_URL" in str(error.value)


def test_cualquier_otro_error_de_requests_tambien_es_errorapi(peticiones):
    peticiones["excepcion"] = requests.exceptions.TooManyRedirects()

    with pytest.raises(api_client.ErrorAPI):
        api_client.obtener_paises(URL)


def test_un_error_que_no_hereda_de_requests_no_tumba_la_app(peticiones):
    """Una URL mal escrita revienta en urllib3 con errores ajenos a requests.

    Sin la captura final, la excepción subiría hasta Streamlit y la página
    moriría en vez de mostrar un mensaje.
    """
    peticiones["excepcion"] = ValueError("host demasiado largo")

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert "no parece válida" in str(error.value)


# --- Traducción de errores HTTP ---------------------------------------------

def test_un_detail_de_texto_se_muestra_tal_cual(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(500, {"detail": "Pinecone no responde"})

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert "500" in str(error.value)
    assert "Pinecone no responde" in str(error.value)


def test_un_422_de_pydantic_se_resume_campo_por_campo(peticiones):
    """FastAPI manda una lista de errores; al usuario hay que darle una frase."""
    peticiones["respuesta"] = RespuestaFalsa(
        422,
        {
            "detail": [
                {"loc": ["body", "consulta"], "msg": "String should have at least 2 characters"},
                {"loc": ["body", "k_plantillas"], "msg": "Input should be less than or equal to 20"},
            ]
        },
    )

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.buscar(URL, "a")

    mensaje = str(error.value)
    assert "consulta" in mensaje
    assert "k_plantillas" in mensaje
    assert "body" not in mensaje, "el prefijo 'body' es ruido para el usuario"


def test_un_error_sin_json_cae_al_texto_crudo(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(502, texto="<html>Bad Gateway</html>", json_roto=True)

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert "502" in str(error.value)


def test_un_200_con_json_invalido_tambien_es_errorapi(peticiones):
    """Pasa cuando un proxy o un túnel devuelve una página en vez de la API."""
    peticiones["respuesta"] = RespuestaFalsa(200, texto="no soy json", json_roto=True)

    with pytest.raises(api_client.ErrorAPI) as error:
        api_client.obtener_paises(URL)

    assert "JSON" in str(error.value)


# --- verificar_estado --------------------------------------------------------

def test_estado_ok_informa_el_tiempo_de_respuesta(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"status": "ok"})

    esta_ok, mensaje = api_client.verificar_estado(URL)

    assert esta_ok is True
    assert "ms" in mensaje


def test_estado_distinto_de_ok_se_considera_caida(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"status": "degradado"})

    esta_ok, mensaje = api_client.verificar_estado(URL)

    assert esta_ok is False
    assert "inesperado" in mensaje


def test_verificar_estado_nunca_lanza_devuelve_false(peticiones):
    """La barra lateral llama a esto en cada rerun: no puede propagar errores."""
    peticiones["excepcion"] = requests.exceptions.ConnectionError()

    esta_ok, mensaje = api_client.verificar_estado(URL)

    assert esta_ok is False
    assert mensaje


# --- Listados ----------------------------------------------------------------

def test_los_paises_llegan_como_lista_de_texto(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=["Colombia", "Chile"])

    assert api_client.obtener_paises(URL) == ["Colombia", "Chile"]


def test_una_respuesta_que_no_es_lista_da_lista_vacia(peticiones):
    """Mejor un selector vacío que una excepción a mitad de la demo."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"paises": ["Colombia"]})

    assert api_client.obtener_paises(URL) == []
    assert api_client.obtener_modalidades(URL) == []


# --- buscar ------------------------------------------------------------------

RESPUESTA_BUSQUEDA = {
    "consulta": "data scientist",
    "total_resultados": 1,
    "resultados": [{"Job Title": "Data Scientist", "similitud": 0.9}],
}


def test_buscar_devuelve_un_resultado_completo(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    resultado = api_client.buscar(URL, "data scientist")

    assert resultado.consulta == "data scientist"
    assert resultado.total_resultados == 1
    assert resultado.resultados[0]["Job Title"] == "Data Scientist"
    assert resultado.duracion_ms > 0


def test_los_filtros_vacios_no_se_envian(peticiones):
    """La API distingue 'sin filtro' de 'filtro en cero' por la ausencia de clave."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    api_client.buscar(URL, "data scientist")

    cuerpo = peticiones["llamadas"][0]["cuerpo"]
    assert set(cuerpo) == {"consulta", "k_plantillas", "max_resultados"}


def test_los_filtros_presentes_si_se_envian(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    api_client.buscar(URL, "data scientist", pais="Colombia", salario_min=50)

    cuerpo = peticiones["llamadas"][0]["cuerpo"]
    assert cuerpo["pais"] == "Colombia"
    assert cuerpo["salario_min"] == 50
    assert "modalidad" not in cuerpo


def test_un_filtro_en_cero_si_viaja(peticiones):
    """0 no es None: si se perdiera, 'sin experiencia' dejaría de filtrar."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    api_client.buscar(URL, "data scientist", experiencia_min=0)

    assert peticiones["llamadas"][0]["cuerpo"]["experiencia_min"] == 0


def test_la_peticion_enviada_queda_guardada_para_mostrarla(peticiones):
    """La interfaz la enseña en el expander durante la sustentación."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    resultado = api_client.buscar(URL, "data scientist", pais="Colombia")

    assert resultado.peticion_enviada["pais"] == "Colombia"


def test_buscar_usa_post(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=RESPUESTA_BUSQUEDA)

    api_client.buscar(URL, "data scientist")

    assert peticiones["llamadas"][0]["metodo"] == "POST"


def test_una_respuesta_que_no_es_objeto_da_errorapi(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo=["esto no es un objeto"])

    with pytest.raises(api_client.ErrorAPI):
        api_client.buscar(URL, "data scientist")


def test_una_respuesta_incompleta_no_rompe(peticiones):
    """Si faltan claves se usan valores por defecto en vez de reventar."""
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={})

    resultado = api_client.buscar(URL, "data scientist")

    assert resultado.consulta == "data scientist"
    assert resultado.total_resultados == 0
    assert resultado.resultados == []


def test_resultados_nulos_se_normalizan_a_lista(peticiones):
    peticiones["respuesta"] = RespuestaFalsa(cuerpo={"resultados": None})

    assert api_client.buscar(URL, "x").resultados == []
