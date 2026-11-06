"""
Cliente HTTP de la API de búsqueda semántica (api/app/main.py).

Hay una función por endpoint expuesto por la API, de modo que todo el consumo
quede concentrado en un solo módulo y sea fácil de revisar o de reutilizar
desde otro frontend:

    GET  /health              -> verificar_estado()
    GET  /filtros/paises      -> obtener_paises()
    GET  /filtros/modalidades -> obtener_modalidades()
    POST /buscar              -> buscar()

Este módulo no importa Streamlit a propósito: es HTTP puro, así se puede probar
desde una consola normal (`python -c "import api_client; ..."`) sin levantar la
interfaz.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

# La API tarda en responder la PRIMERA petición porque al arrancar carga el
# modelo de embeddings y el parquet del dataset (ver search.cargar_recursos).
# Por eso la búsqueda usa un timeout mucho más generoso que el resto de
# llamadas, que son instantáneas una vez el servicio está en marcha.
TIMEOUT_RAPIDO = 15
TIMEOUT_BUSQUEDA = 120


class ErrorAPI(RuntimeError):
    """Error de comunicación con la API, con un mensaje legible para la interfaz."""


@dataclass
class ResultadoBusqueda:
    """Respuesta de POST /buscar, junto con datos útiles para mostrar en la demo."""

    consulta: str
    total_resultados: int
    resultados: list[dict]
    peticion_enviada: dict = field(default_factory=dict)
    duracion_ms: float = 0.0


def _mensaje_de_error(respuesta: requests.Response) -> str:
    """Traduce una respuesta HTTP de error al mensaje más legible posible.

    FastAPI devuelve `{"detail": "..."}` para HTTPException y `{"detail": [...]}`
    (una lista de errores por campo) cuando falla la validación de Pydantic.
    """
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return f"HTTP {respuesta.status_code}: {respuesta.text[:300]}"

    detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else None

    if isinstance(detalle, str):
        return f"HTTP {respuesta.status_code}: {detalle}"

    if isinstance(detalle, list):
        problemas = []
        for item in detalle:
            if isinstance(item, dict):
                campo = " → ".join(str(p) for p in item.get("loc", []) if p != "body")
                problemas.append(f"{campo or 'petición'}: {item.get('msg', 'inválido')}")
        if problemas:
            return f"HTTP {respuesta.status_code}: " + "; ".join(problemas)

    return f"HTTP {respuesta.status_code}: {respuesta.text[:300]}"


def _pedir(
    metodo: str,
    url_base: str,
    ruta: str,
    *,
    timeout: int,
    cuerpo: Optional[dict] = None,
) -> tuple[Any, float]:
    """Ejecuta una petición y devuelve (json, duración en ms).

    Cualquier fallo de red o de la API se convierte en `ErrorAPI` con un mensaje
    que se puede mostrar tal cual al usuario.
    """
    url = f"{url_base.rstrip('/')}{ruta}"
    inicio = time.perf_counter()

    try:
        respuesta = requests.request(metodo, url, json=cuerpo, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ErrorAPI(
            f"La API no respondió en {timeout} s ({ruta}). "
            "Si es la primera petición, puede seguir cargando el modelo y el dataset."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise ErrorAPI(
            f"No se pudo conectar con la API en {url_base}. "
            "Verifica que esté levantada y que API_URL sea correcta."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise ErrorAPI(f"Error inesperado al llamar {ruta}: {exc}") from exc
    except Exception as exc:
        # Una URL mal formada puede reventar por debajo de requests, en urllib3,
        # con errores que NO heredan de RequestException (por ejemplo
        # LocationParseError si el host es larguísimo). Como la URL de la API se
        # pega a mano desde la interfaz, aquí nunca debe escaparse nada: un
        # error tipográfico tiene que verse como un mensaje, no tumbar la app.
        raise ErrorAPI(f"La URL no parece válida ({url_base}): {exc}") from exc

    duracion_ms = (time.perf_counter() - inicio) * 1000

    if respuesta.status_code >= 400:
        raise ErrorAPI(_mensaje_de_error(respuesta))

    try:
        return respuesta.json(), duracion_ms
    except ValueError as exc:
        raise ErrorAPI(f"La API devolvió una respuesta que no es JSON válido ({ruta}).") from exc


# --- GET /health -------------------------------------------------------------

def verificar_estado(url_base: str) -> tuple[bool, str]:
    """Indica si la API está arriba. Devuelve (está_ok, mensaje)."""
    try:
        datos, duracion_ms = _pedir("GET", url_base, "/health", timeout=TIMEOUT_RAPIDO)
    except ErrorAPI as exc:
        return False, str(exc)

    estado = datos.get("status") if isinstance(datos, dict) else None
    if estado == "ok":
        return True, f"API conectada ({duracion_ms:.0f} ms)"
    return False, f"La API respondió algo inesperado: {datos!r}"


# --- GET /filtros/paises -----------------------------------------------------

def obtener_paises(url_base: str) -> list[str]:
    datos, _ = _pedir("GET", url_base, "/filtros/paises", timeout=TIMEOUT_RAPIDO)
    return [str(p) for p in datos] if isinstance(datos, list) else []


# --- GET /filtros/modalidades ------------------------------------------------

def obtener_modalidades(url_base: str) -> list[str]:
    datos, _ = _pedir("GET", url_base, "/filtros/modalidades", timeout=TIMEOUT_RAPIDO)
    return [str(m) for m in datos] if isinstance(datos, list) else []


# --- POST /buscar ------------------------------------------------------------

def buscar(
    url_base: str,
    consulta: str,
    *,
    k_plantillas: int = 5,
    max_resultados: int = 20,
    pais: Optional[str] = None,
    modalidad: Optional[str] = None,
    experiencia_min: Optional[int] = None,
    salario_min: Optional[int] = None,
    salario_max: Optional[int] = None,
) -> ResultadoBusqueda:
    """Búsqueda semántica con filtros opcionales.

    Los filtros que valen None simplemente no se envían: la API los trata como
    "sin filtro" (ver SolicitudBusqueda en api/app/schemas.py).
    """
    cuerpo: dict[str, Any] = {
        "consulta": consulta,
        "k_plantillas": k_plantillas,
        "max_resultados": max_resultados,
    }
    opcionales = {
        "pais": pais,
        "modalidad": modalidad,
        "experiencia_min": experiencia_min,
        "salario_min": salario_min,
        "salario_max": salario_max,
    }
    cuerpo.update({clave: valor for clave, valor in opcionales.items() if valor is not None})

    datos, duracion_ms = _pedir("POST", url_base, "/buscar", timeout=TIMEOUT_BUSQUEDA, cuerpo=cuerpo)

    if not isinstance(datos, dict):
        raise ErrorAPI("La API devolvió un cuerpo inesperado en /buscar.")

    return ResultadoBusqueda(
        consulta=datos.get("consulta", consulta),
        total_resultados=datos.get("total_resultados", 0),
        resultados=datos.get("resultados", []) or [],
        peticion_enviada=cuerpo,
        duracion_ms=duracion_ms,
    )
