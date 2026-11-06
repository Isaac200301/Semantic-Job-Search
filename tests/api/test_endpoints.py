"""Pruebas de los cuatro endpoints (`app/main.py`) con el TestClient de FastAPI.

Se recorre la API entera por HTTP —ruta, validación, serialización y códigos de
estado— sustituyendo solo la capa de búsqueda. Así se comprueba el contrato que
consume el frontend sin levantar uvicorn, sin Pinecone y sin cargar el modelo.
"""
import pytest
from fastapi.testclient import TestClient

from app import main, search


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


@pytest.fixture
def cliente(monkeypatch):
    """Cliente HTTP con la capa de búsqueda sustituida por dobles."""
    # Sin esto, arrancar la app descargaría el modelo y abriría Pinecone.
    monkeypatch.setattr(search, "cargar_recursos", lambda: None)
    monkeypatch.setattr(search, "buscar_ofertas", lambda **kwargs: [OFERTA])
    monkeypatch.setattr(search, "listar_paises", lambda: ["Chile", "Colombia"])
    monkeypatch.setattr(search, "listar_modalidades", lambda: ["Full-Time", "Part-Time"])
    return TestClient(main.app)


# --- GET /health -------------------------------------------------------------

def test_health_responde_ok(cliente):
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


# --- GET /filtros/* ----------------------------------------------------------

def test_paises_devuelve_una_lista_plana(cliente):
    """El frontend hace `[str(p) for p in datos]`: tiene que ser un array JSON."""
    respuesta = cliente.get("/filtros/paises")

    assert respuesta.status_code == 200
    assert respuesta.json() == ["Chile", "Colombia"]


def test_modalidades_devuelve_una_lista_plana(cliente):
    respuesta = cliente.get("/filtros/modalidades")

    assert respuesta.status_code == 200
    assert respuesta.json() == ["Full-Time", "Part-Time"]


# --- POST /buscar: camino feliz ---------------------------------------------

def test_buscar_devuelve_consulta_total_y_resultados(cliente):
    respuesta = cliente.post("/buscar", json={"consulta": "data scientist"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["consulta"] == "data scientist"
    assert cuerpo["total_resultados"] == 1
    assert len(cuerpo["resultados"]) == 1


def test_el_json_usa_los_nombres_con_espacios(cliente):
    """Contrato con el frontend: la tabla lee 'Job Title', no 'job_title'."""
    respuesta = cliente.post("/buscar", json={"consulta": "data scientist"})
    oferta = respuesta.json()["resultados"][0]

    assert oferta["Job Id"] == 123
    assert oferta["Job Title"] == "Data Scientist"
    assert "job_title" not in oferta


def test_los_filtros_llegan_a_la_capa_de_busqueda(cliente, monkeypatch):
    recibido = {}

    def espia(**kwargs):
        recibido.update(kwargs)
        return []

    monkeypatch.setattr(search, "buscar_ofertas", espia)

    cliente.post(
        "/buscar",
        json={
            "consulta": "backend",
            "k_plantillas": 3,
            "max_resultados": 7,
            "pais": "Colombia",
            "modalidad": "Full-Time",
            "experiencia_min": 2,
            "salario_min": 50,
            "salario_max": 90,
        },
    )

    assert recibido == {
        "consulta": "backend",
        "k_plantillas": 3,
        "max_resultados": 7,
        "pais": "Colombia",
        "modalidad": "Full-Time",
        "experiencia_min": 2,
        "salario_min": 50,
        "salario_max": 90,
    }


def test_los_filtros_omitidos_llegan_como_none(cliente, monkeypatch):
    """La API distingue 'sin filtro' de 'filtro en cero' por este None."""
    recibido = {}

    def espia(**kwargs):
        recibido.update(kwargs)
        return []

    monkeypatch.setattr(search, "buscar_ofertas", espia)

    cliente.post("/buscar", json={"consulta": "backend"})

    assert recibido["pais"] is None
    assert recibido["salario_min"] is None


def test_cero_resultados_es_200_no_404(cliente, monkeypatch):
    """Una combinación de filtros sin coincidencias no es un error."""
    monkeypatch.setattr(search, "buscar_ofertas", lambda **kwargs: [])

    respuesta = cliente.post("/buscar", json={"consulta": "xyz imposible"})

    assert respuesta.status_code == 200
    assert respuesta.json()["total_resultados"] == 0
    assert respuesta.json()["resultados"] == []


# --- POST /buscar: errores ---------------------------------------------------

@pytest.mark.parametrize(
    "cuerpo",
    [
        {},                                     # falta la consulta
        {"consulta": "a"},                      # demasiado corta
        {"consulta": "ok", "k_plantillas": 0},
        {"consulta": "ok", "k_plantillas": 21},
        {"consulta": "ok", "max_resultados": 0},
        {"consulta": "ok", "max_resultados": 101},
        {"consulta": "ok", "salario_min": -1},
    ],
)
def test_una_peticion_invalida_da_422(cliente, cuerpo):
    respuesta = cliente.post("/buscar", json=cuerpo)

    assert respuesta.status_code == 422


def test_el_422_explica_que_campo_falla(cliente):
    """El frontend arma su mensaje con `loc` y `msg` de cada error."""
    respuesta = cliente.post("/buscar", json={"consulta": "ok", "k_plantillas": 99})
    detalle = respuesta.json()["detail"]

    assert isinstance(detalle, list)
    assert any("k_plantillas" in str(item.get("loc", "")) for item in detalle)


def test_un_fallo_interno_se_traduce_a_500_legible(cliente, monkeypatch):
    """Si Pinecone se cae, el cliente debe ver un 500 con el motivo, no un cuelgue."""
    def revienta(**kwargs):
        raise RuntimeError("Pinecone no responde")

    monkeypatch.setattr(search, "buscar_ofertas", revienta)

    respuesta = cliente.post("/buscar", json={"consulta": "data scientist"})

    assert respuesta.status_code == 500
    assert "Pinecone no responde" in respuesta.json()["detail"]


# --- Metadatos y CORS --------------------------------------------------------

def test_la_documentacion_openapi_se_genera(cliente):
    """La demo enseña /docs; si el esquema no compila, esa página muere."""
    respuesta = cliente.get("/openapi.json")

    assert respuesta.status_code == 200
    rutas = respuesta.json()["paths"]
    assert set(rutas) == {"/health", "/buscar", "/filtros/paises", "/filtros/modalidades"}


def test_cors_permite_llamadas_desde_otro_origen(cliente):
    respuesta = cliente.get("/health", headers={"Origin": "https://ejemplo.streamlit.app"})

    assert respuesta.headers.get("access-control-allow-origin") == "*"
