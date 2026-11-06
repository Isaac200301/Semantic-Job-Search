"""
Prototipo de interfaz para el motor de búsqueda semántica de ofertas laborales.

Proyecto Integrador 1 — Deus Ex Code.

Esta app NO contiene lógica de búsqueda: toda la inteligencia vive en la API
(api/app/search.py), y aquí solo se consumen sus endpoints vía api_client.py.
Esa separación es intencional — es lo que se planteó en el README del proyecto.

Correr:  streamlit run app.py     (desde la carpeta frontend/)
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

import api_client
from api_client import ErrorAPI

# set_page_config tiene que ser la primera llamada a Streamlit del script.
st.set_page_config(
    page_title="Búsqueda Semántica de Empleos",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

OPCION_TODOS = "Todos"

CONSULTAS_EJEMPLO = [
    "python developer with machine learning and NLP experience",
    "senior backend engineer with cloud and microservices experience",
    "marketing manager with social media and branding skills",
    "frontend developer react and javascript",
    "financial analyst with excel and forecasting skills",
]


# --- Configuración -----------------------------------------------------------

def hay_archivo_secrets() -> bool:
    """Indica si existe un secrets.toml en alguna de las rutas que Streamlit lee.

    Es importante comprobarlo ANTES de tocar `st.secrets`: cuando el archivo no
    existe, Streamlit pinta un recuadro rojo de error en la propia página antes
    de lanzar la excepción, así que un try/except no basta para evitarlo. Correr
    en local sin secrets.toml es el caso normal, no un error.
    """
    rutas = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
    ]
    return any(ruta.is_file() for ruta in rutas)


def url_por_defecto() -> str:
    """URL inicial de la API: secrets.toml > variable de entorno > localhost.

    Es solo el valor con el que arranca el campo de la barra lateral; una vez la
    app está abierta, manda lo que haya escrito ahí.
    """
    url = ""
    if hay_archivo_secrets():
        try:
            url = st.secrets.get("API_URL", "")
        except Exception:
            url = ""
    if not url:
        url = os.environ.get("API_URL", "")
    return normalizar_url(url or "http://localhost:8000")


def normalizar_url(url: str) -> str:
    """Limpia una URL pegada a mano: espacios, barra final y esquema ausente."""
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return url


# --- Llamadas cacheadas ------------------------------------------------------
# Las listas de filtros no cambian entre búsquedas: se cachean para no golpear
# la API en cada rerun de Streamlit (que ocurre ante cualquier interacción).

@st.cache_data(ttl=300, show_spinner=False)
def cargar_paises(url_base: str) -> list[str]:
    return api_client.obtener_paises(url_base)


@st.cache_data(ttl=300, show_spinner=False)
def cargar_modalidades(url_base: str) -> list[str]:
    return api_client.obtener_modalidades(url_base)


@st.cache_data(ttl=30, show_spinner=False)
def consultar_estado(url_base: str) -> tuple[bool, str]:
    return api_client.verificar_estado(url_base)


# --- Utilidades de presentación ---------------------------------------------

def campo(oferta: dict, *nombres: str, defecto="—"):
    """Lee un campo de una oferta probando varios nombres posibles.

    La API declara los campos con alias ("Job Id", "Job Title", ...) sobre
    atributos en snake_case (job_id, job_title, ...). Según cómo serialice
    FastAPI, el JSON puede venir con unos u otros, así que se aceptan ambos.
    """
    for nombre in nombres:
        valor = oferta.get(nombre)
        if valor is not None and valor != "":
            return valor
    return defecto


def a_dataframe(resultados: list[dict]) -> pd.DataFrame:
    """Normaliza los resultados a una tabla con nombres de columna estables."""
    filas = []
    for oferta in resultados:
        similitud = campo(oferta, "similitud", defecto=0.0)
        try:
            similitud = float(similitud)
        except (TypeError, ValueError):
            similitud = 0.0

        filas.append(
            {
                "Job Id": campo(oferta, "Job Id", "job_id"),
                "Cargo": campo(oferta, "Job Title", "job_title"),
                "Rol": campo(oferta, "Role", "role"),
                "Empresa": campo(oferta, "Company", "company"),
                "País": campo(oferta, "Country", "country"),
                "Modalidad": campo(oferta, "Work Type", "work_type"),
                "Experiencia": campo(oferta, "Experience", "experience"),
                "Salario": campo(oferta, "Salary Range", "salary_range"),
                "Similitud": similitud,
            }
        )
    return pd.DataFrame(filas)


def usar_consulta_ejemplo(ejemplo: str) -> None:
    """Coloca una consulta de ejemplo en el campo de búsqueda.

    Tiene que ser un callback (`on_click`) y no código en línea tras el `if
    st.button(...)`: el campo de texto usa `key="consulta"`, y Streamlit prohíbe
    modificar `st.session_state["consulta"]` una vez que ese widget ya se
    instanció en la misma ejecución. Los callbacks corren ANTES del rerun, que
    es el único momento en que la asignación es legal.
    """
    st.session_state.consulta = ejemplo


def pintar_tarjeta(oferta: dict) -> None:
    with st.container(border=True):
        columna_info, columna_score = st.columns([5, 1])

        with columna_info:
            st.markdown("#### " + str(campo(oferta, "Job Title", "job_title")))
            st.caption(
                "{empresa}  ·  {rol}  ·  ID {job_id}".format(
                    empresa=campo(oferta, "Company", "company"),
                    rol=campo(oferta, "Role", "role"),
                    job_id=campo(oferta, "Job Id", "job_id"),
                )
            )
            etiquetas = [
                "📍 " + str(campo(oferta, "Country", "country")),
                "🕒 " + str(campo(oferta, "Work Type", "work_type")),
                "📈 " + str(campo(oferta, "Experience", "experience")),
                "💵 " + str(campo(oferta, "Salary Range", "salary_range")),
            ]
            st.markdown("  ".join("`" + e + "`" for e in etiquetas))

        with columna_score:
            similitud = campo(oferta, "similitud", defecto=0.0)
            try:
                similitud = float(similitud)
            except (TypeError, ValueError):
                similitud = 0.0
            st.metric("Similitud", "{:.1f}%".format(similitud * 100))


# --- Barra lateral: estado de la API y filtros -------------------------------

with st.sidebar:
    st.markdown("### Conexión")

    # La URL normalmente viene de los secrets (la API vive en Cloud Run con una
    # dirección fija), pero se deja editable aquí para poder apuntar a otra
    # instancia sin redesplegar: una API local durante el desarrollo, o una
    # dirección temporal si hiciera falta levantarla en otro sitio.
    if "api_url" not in st.session_state:
        st.session_state.api_url = url_por_defecto()

    st.text_input(
        "URL de la API",
        key="api_url",
        help="Normalmente ya viene configurada. Cámbiala para apuntar a otra "
             "instancia; si la dejas vacía se usa http://localhost:8000.",
    )
    API_URL = normalizar_url(st.session_state.api_url) or "http://localhost:8000"

    st.markdown("### Estado del servicio")

    # GET /health — no es decorativo: distingue "API arrancando o dormida" de
    # "la aplicación se colgó", y confirma que la URL pegada arriba responde.
    api_ok, mensaje_estado = consultar_estado(API_URL)
    if api_ok:
        st.success(mensaje_estado, icon="✅")
    else:
        st.error(mensaje_estado, icon="🚫")

    if st.button("Reintentar conexión", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    st.markdown("### Filtros")

    # GET /filtros/paises y GET /filtros/modalidades
    paises: list[str] = []
    modalidades: list[str] = []
    error_filtros = ""
    if api_ok:
        try:
            paises = cargar_paises(API_URL)
            modalidades = cargar_modalidades(API_URL)
        except ErrorAPI as exc:
            error_filtros = str(exc)

    if error_filtros:
        st.warning("No se pudieron cargar los filtros. " + error_filtros, icon="⚠️")

    pais_elegido = st.selectbox("País", [OPCION_TODOS] + paises, disabled=not paises)
    modalidad_elegida = st.selectbox(
        "Modalidad de trabajo", [OPCION_TODOS] + modalidades, disabled=not modalidades
    )

    st.markdown("###### Experiencia")
    filtrar_experiencia = st.checkbox("Filtrar por mi experiencia")
    experiencia = st.slider(
        "Años de experiencia",
        min_value=0,
        max_value=20,
        value=3,
        disabled=not filtrar_experiencia,
        help="Devuelve ofertas cuyo rango de experiencia requerida incluye este valor.",
    )

    st.markdown("###### Salario")
    filtrar_salario = st.checkbox("Filtrar por salario")
    salario = st.slider(
        "Rango deseado (miles de USD)",
        min_value=0,
        max_value=200,
        value=(60, 120),
        step=5,
        disabled=not filtrar_salario,
        help="Mismo formato que Salary Range del dataset, p. ej. $59K-$99K.",
    )

    st.divider()

    with st.expander("Opciones avanzadas"):
        k_plantillas = st.slider(
            "Plantillas semánticas (k)",
            min_value=1,
            max_value=20,
            value=5,
            help=(
                "Cuántas plantillas de texto distintas se piden a Pinecone. "
                "El dataset reutiliza plantillas: subir k amplía la variedad "
                "temática de los resultados."
            ),
        )
        max_resultados = st.slider(
            "Máximo de ofertas a devolver",
            min_value=1,
            max_value=100,
            value=20,
        )


# --- Área principal: consulta ------------------------------------------------

st.title("🔎 Búsqueda Semántica de Ofertas Laborales")
st.caption(
    "Proyecto Integrador 1 — Deus Ex Code  ·  "
    "Busca por significado, no por coincidencia exacta de palabras."
)

if "consulta" not in st.session_state:
    st.session_state.consulta = CONSULTAS_EJEMPLO[0]

with st.form("formulario_busqueda"):
    st.text_input(
        "¿Qué trabajo estás buscando?",
        key="consulta",
        placeholder="Ej: python developer with machine learning experience",
        help="Escribe en lenguaje natural. Mínimo 2 caracteres.",
    )
    buscar_pulsado = st.form_submit_button(
        "Buscar ofertas", type="primary", use_container_width=True, disabled=not api_ok
    )

st.caption("Consultas de ejemplo:")
columnas_ejemplo = st.columns(len(CONSULTAS_EJEMPLO))
for columna, ejemplo in zip(columnas_ejemplo, CONSULTAS_EJEMPLO):
    with columna:
        etiqueta = ejemplo if len(ejemplo) <= 28 else ejemplo[:25] + "..."
        st.button(
            etiqueta,
            key="ej_" + ejemplo,
            use_container_width=True,
            help=ejemplo,
            on_click=usar_consulta_ejemplo,
            args=(ejemplo,),
        )


# --- Ejecución de la búsqueda ------------------------------------------------

if buscar_pulsado:
    consulta = st.session_state.consulta.strip()
    if len(consulta) < 2:
        st.warning("Escribe al menos 2 caracteres para buscar.", icon="✏️")
    else:
        with st.spinner("Consultando la API… (la primera búsqueda puede tardar)"):
            try:
                st.session_state.resultado = api_client.buscar(
                    API_URL,
                    consulta,
                    k_plantillas=k_plantillas,
                    max_resultados=max_resultados,
                    pais=None if pais_elegido == OPCION_TODOS else pais_elegido,
                    modalidad=None if modalidad_elegida == OPCION_TODOS else modalidad_elegida,
                    experiencia_min=experiencia if filtrar_experiencia else None,
                    salario_min=salario[0] if filtrar_salario else None,
                    salario_max=salario[1] if filtrar_salario else None,
                )
                st.session_state.error_busqueda = ""
            except ErrorAPI as exc:
                st.session_state.resultado = None
                st.session_state.error_busqueda = str(exc)


# --- Resultados --------------------------------------------------------------

if st.session_state.get("error_busqueda"):
    st.error(st.session_state.error_busqueda, icon="🚫")

resultado = st.session_state.get("resultado")

if resultado is not None:
    st.divider()

    encabezado, tiempo = st.columns([4, 1])
    with encabezado:
        st.subheader(
            "{n} {palabra} para: {q}".format(
                n=resultado.total_resultados,
                palabra="oferta" if resultado.total_resultados == 1 else "ofertas",
                q=resultado.consulta,
            )
        )
    with tiempo:
        st.metric("Tiempo", "{:.0f} ms".format(resultado.duracion_ms))

    with st.expander("Ver la petición enviada a POST /buscar"):
        st.json(resultado.peticion_enviada)

    if not resultado.resultados:
        st.info(
            "La búsqueda no devolvió ofertas. Prueba a relajar los filtros del panel "
            "izquierdo o a subir el número de plantillas en Opciones avanzadas.",
            icon="🔍",
        )
    else:
        tabla = a_dataframe(resultado.resultados)

        pestana_tarjetas, pestana_tabla = st.tabs(["Tarjetas", "Tabla"])

        with pestana_tarjetas:
            for oferta in resultado.resultados:
                pintar_tarjeta(oferta)

        with pestana_tabla:
            st.dataframe(
                tabla,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Similitud": st.column_config.ProgressColumn(
                        "Similitud", min_value=0.0, max_value=1.0, format="%.3f"
                    )
                },
            )
            st.download_button(
                "Descargar resultados (CSV)",
                data=tabla.to_csv(index=False).encode("utf-8-sig"),
                file_name="resultados_busqueda.csv",
                mime="text/csv",
            )
else:
    st.info("Escribe una consulta y pulsa **Buscar ofertas** para empezar.", icon="👋")
