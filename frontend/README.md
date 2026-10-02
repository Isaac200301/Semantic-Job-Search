# Frontend — Prototipo de interfaz (Streamlit)

Interfaz web del motor de búsqueda semántica de ofertas laborales.
Consume la API de `../api/` por HTTP; **no** contiene lógica de búsqueda propia.

## 1. Estructura

```
frontend/
├── app.py                        # interfaz: filtros, búsqueda y resultados
├── api_client.py                 # una función por endpoint de la API (HTTP puro)
├── requirements.txt
└── .streamlit/
    ├── config.toml               # tema visual
    └── secrets.toml.example      # plantilla de configuración (copiar a secrets.toml)
```

La separación entre `app.py` y `api_client.py` es intencional: `api_client.py`
no importa Streamlit, así que se puede probar desde una consola normal o
reutilizar si en el futuro se cambia la interfaz.

## 2. Endpoints consumidos

Los cuatro endpoints que expone la API se usan desde la interfaz:

| Endpoint | Función en `api_client.py` | Dónde se ve |
|---|---|---|
| `GET /health` | `verificar_estado()` | Indicador de estado en la barra lateral |
| `GET /filtros/paises` | `obtener_paises()` | Poblado del selector de país |
| `GET /filtros/modalidades` | `obtener_modalidades()` | Poblado del selector de modalidad |
| `POST /buscar` | `buscar()` | Botón "Buscar ofertas" → resultados |

Los ocho campos de `SolicitudBusqueda` son controlables desde la interfaz:
`consulta` (campo de texto), `pais` y `modalidad` (selectores), `experiencia_min`
(slider, activable), `salario_min` / `salario_max` (slider de rango, activable),
y `k_plantillas` / `max_resultados` (dentro de "Opciones avanzadas").

Los filtros que no se activan **no se envían** en el cuerpo de la petición, que
es como la API espera distinguir "sin filtro" de "filtro en cero". El expander
*"Ver la petición enviada a POST /buscar"* muestra el JSON exacto que se mandó,
útil durante la sustentación.

## 3. Correr en local

Con la API ya levantada en otra terminal (`uvicorn app.main:app --reload` desde
`../api/`):

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py
```

En Windows PowerShell (una instrucción por línea — PowerShell 5.1 no admite `&&`):

```powershell
cd frontend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

streamlit run app.py
```

Si PowerShell bloquea la activación del entorno virtual, corre antes
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` en esa misma terminal.

Abre `http://localhost:8501`.

Por defecto apunta a `http://localhost:8000`. Para cambiarlo, copia
`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y edita `API_URL`,
o exporta la variable de entorno `API_URL`.

**Antes de subir al repo:** agrega `frontend/.streamlit/secrets.toml` al
`.gitignore` de la raíz. Ese archivo hoy solo guarda una URL (la API key de
Pinecone vive del lado de la API, no aquí), pero conviene no versionarlo.

## 4. Desplegar en Streamlit Community Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io) con la cuenta de GitHub
   dueña del repositorio.
2. *New app* → selecciona el repo, la rama, y como *Main file path* pon
   `frontend/app.py`.
3. Deploy. Streamlit instala `frontend/requirements.txt` automáticamente.

No hace falta configurar *Secrets*: la URL de la API se pega en el campo de la
barra lateral, porque el túnel de Cloudflare genera un dominio distinto en cada
arranque. Ver la sección 9 del [README del repositorio](../README.md).

Como Streamlit llama a la API **desde su servidor** y no desde el navegador, la
configuración de CORS de la API no afecta a este frontend.

## 5. Comportamiento esperado en la primera búsqueda

La API carga el modelo de embeddings y el dataset al arrancar, y el túnel puede
tardar un instante en establecerse. Por eso:

- El timeout de `POST /buscar` es de 120 s (el del resto, 15 s).
- El indicador de la barra lateral distingue "API caída" de "API pensando".
- Si el indicador está en rojo, el botón de búsqueda queda deshabilitado y hay
  un botón *Reintentar conexión* que limpia la caché y vuelve a consultar.

## 6. Verificación hecha

Contra la **API real** (con Pinecone e índice `ofertas-laborales` cargado):

- Los cuatro endpoints responden correctamente.
- Búsqueda sin filtros y con los ocho parámetros a la vez.
- Combinación de filtros sin coincidencias → devuelve 0 resultados, no un error.
- Consulta inválida → la API responde 422 y el mensaje se muestra legible.
- La app completa se ejecutó con `streamlit.testing.v1.AppTest`: cero
  excepciones, filtros poblados desde la API (216 países, 5 modalidades),
  resultados renderizados en tarjetas y tabla.
- Los cinco botones de consulta de ejemplo, uno por uno: click, que rellene el
  campo de búsqueda, y búsqueda posterior.

Las pruebas se corrieron con Streamlit 1.39 (Python 3.13) y 1.64 (Python 3.14).

Adicionalmente, `api_client.py` se probó contra un servidor simulado para los
casos que la API real no produce a demanda: error 500 y API caída. Las funciones
de presentación se probaron con respuestas en formato alias (`"Job Title"`) y
snake_case (`"job_title"`), y con ofertas incompletas.

### Dato de cobertura

El dataset tiene 1.615.940 ofertas pero solo **3.760 plantillas de texto
únicas**, y Pinecone contiene exactamente esos 3.760 vectores. La cobertura es
del 100%: toda oferta es alcanzable por la búsqueda, con un índice 430 veces
más pequeño que el dataset.
