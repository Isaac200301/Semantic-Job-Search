# Pruebas automatizadas

Suite de pruebas del motor de búsqueda semántica. Cubre la API (FastAPI) y la
interfaz (Streamlit).

```
142 pruebas · 92 % de cobertura · ~17 s · sin acceso a red
```

## 1. Cómo correrlas

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

Desde la raíz del repositorio. Una instrucción por línea: PowerShell 5.1 no
admite `&&`.

Esto deja tres cosas:

| Salida | Para qué |
|---|---|
| Resumen en la terminal | Ver qué pasó y qué falló |
| `htmlcov/index.html` | Cobertura navegable, línea por línea |
| `coverage.xml` | Lo que consume SonarQube Cloud |

Cobertura por módulo:

| Módulo | Cobertura |
|---|---:|
| `frontend/api_client.py` | 96 % |
| `api/app/main.py` | 96 % |
| `api/app/search.py` | 93 % |
| `api/app/config.py` | 90 % |
| `frontend/app.py` | 90 % |
| `api/app/schemas.py` | 100 % |
| **Total** | **92 %** |

Para correr solo una parte:

```powershell
python -m pytest tests/api
python -m pytest tests/frontend
python -m pytest -k compactar
```

## 2. Principio: ninguna prueba sale a la red

Es la decisión que define toda la suite. Las pruebas **no** llaman a Pinecone,
**no** descargan el modelo de Hugging Face y **no** consultan la API desplegada
en Cloud Run. Todo lo externo se sustituye por dobles.

Las razones son prácticas:

- **Rapidez.** 17 segundos en vez de varios minutos. Una suite lenta se deja de
  correr.
- **Determinismo.** Una prueba que depende de Pinecone falla cuando falla la red,
  y entonces deja de dar información sobre el código.
- **Costo.** No se consumen consultas del plan gratuito de Pinecone en cada
  ejecución de CI.
- **Seguridad.** `tests/conftest.py` fija `PINECONE_API_KEY` a un valor falso
  aunque el equipo tenga la clave real exportada en su shell. La clave real
  nunca puede usarse desde las pruebas.

Lo que **no** cubre esta suite, dicho explícitamente: la calidad semántica de los
resultados. Eso no es asunto de pruebas unitarias; se midió con nDCG@10 en
`notebooks/05_Evaluacion_Metricas.ipynb` (MiniLM 0,986 · MPNet 0,978 · TF-IDF
0,933). Aquí se prueba la *lógica alrededor* de la búsqueda vectorial.

## 3. Qué se prueba

### `tests/api/` — 94 pruebas

| Archivo | N.º | Qué verifica |
|---|---:|---|
| `test_schemas.py` | 31 | Validación Pydantic y el contrato de nombres con alias |
| `test_buscar_ofertas.py` | 25 | El motor: expansión de plantillas, filtros, orden, recorte |
| `test_endpoints.py` | 19 | Los cuatro endpoints por HTTP, con códigos de estado |
| `test_carga_datos.py` | 11 | Los tres caminos de carga del dataset y los listados de filtros |
| `test_compactar.py` | 8 | La optimización de memoria no altera ningún valor |

### `tests/frontend/` — 48 pruebas

| Archivo | N.º | Qué verifica |
|---|---:|---|
| `test_api_client.py` | 25 | El cliente HTTP, sobre todo sus caminos de error |
| `test_interfaz.py` | 23 | La app de Streamlit completa, con `AppTest` |

## 4. Tres pruebas que merecen mención

**`test_compactar_el_dataframe_no_altera_la_busqueda`**

La optimización que bajó el consumo de 6,7 GB a ~700 MB cambia los tipos de las
columnas: textos repetitivos a `category`, enteros de 64 a 8 o 16 bits. Un error
ahí no se vería como un fallo, se vería como *resultados distintos*. La prueba
corre la misma consulta sobre la tabla original y sobre la compactada, y exige
que den exactamente lo mismo.

**`test_un_cero_no_se_trata_como_ausencia_de_filtro`**

La API distingue «sin filtro» (`None`) de «filtro en cero» (`0`). Es el tipo de
confusión que `if salario_min:` introduce sin avisar. Hay una prueba equivalente
del lado del cliente: `test_un_filtro_en_cero_si_viaja`.

**`test_pulsar_una_consulta_de_ejemplo_rellena_el_campo`**

Regresión de un fallo real. Los botones de consulta de ejemplo lanzaban
`StreamlitAPIException` porque modificaban `st.session_state` después de que el
widget ya se había instanciado; la solución fue pasar la asignación a un
callback `on_click`. Las pruebas anteriores no lo detectaron porque nunca
pulsaban esos botones. Ahora se pulsan los cinco, uno por uno.

## 5. Cómo se sustituyen las dependencias

**Pinecone y el modelo** (`tests/api/test_buscar_ofertas.py`): dos clases,
`ModeloFalso` e `IndiceFalso`, se inyectan en las variables de módulo de
`search`. `IndiceFalso` devuelve plantillas fijas con puntuaciones conocidas,
lo que permite afirmar sobre el orden y la similitud exactos.

**La capa de búsqueda** (`tests/api/test_endpoints.py`): `TestClient` de FastAPI
recorre la aplicación real —rutas, validación, serialización, CORS— con
`search.buscar_ofertas` sustituida. Así se prueba el contrato HTTP sin levantar
uvicorn.

**La API** (`tests/frontend/`): se sustituyen las funciones de `api_client`.
En `test_interfaz.py`, `AppTest` ejecuta `frontend/app.py` entero en un runtime
simulado: pulsa botones, marca casillas y elige opciones de los selectores, y
después comprueba qué se pintó y qué se le pidió a la API.

## 6. Nota sobre `api/app/__init__.py`

Se añadió al montar la suite. Sin ese archivo, `api/app/` era un *namespace
package* y Python daba prioridad a cualquier módulo llamado `app.py` que
estuviera en la ruta de importación —en concreto, al `frontend/app.py` de
Streamlit—, así que `from app import search` importaba el archivo equivocado.

No cambia cómo arranca la API: `uvicorn app.main:app` funciona igual, y la
imagen de Cloud Run no se ve afectada.

## 7. Integración continua

`.github/workflows/ci.yml` corre la suite en cada push a `main` y a las ramas
`develop/**`, y en cada pull request a `main`. Después envía `coverage.xml` a
SonarQube Cloud.

El workflow instala PyTorch en su versión de CPU antes que el resto de
dependencias. Es el mismo truco de `api/Dockerfile`: la rueda por defecto
incluye CUDA y pesa más de 2 GB, que en CI es tiempo perdido porque no hay GPU.

La configuración del análisis está en `sonar-project.properties`. El token vive
en el secreto `SONAR_TOKEN` del repositorio, nunca en el código.
