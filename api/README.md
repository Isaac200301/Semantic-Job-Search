# API — Motor de Búsqueda Semántica de Ofertas Laborales

Proyecto Integrador 1 — Deus Ex Code.

API en FastAPI que codifica la consulta del usuario con `all-MiniLM-L6-v2`,
busca las plantillas más similares en Pinecone, expande el resultado a ofertas
reales y aplica filtros estructurados.

Para el montaje local y el despliegue, ver el
[README del repositorio](../README.md).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Chequeo de estado |
| POST | `/buscar` | Búsqueda semántica con filtros opcionales |
| GET | `/filtros/paises` | Países disponibles |
| GET | `/filtros/modalidades` | Modalidades disponibles |
| GET | `/docs` | Documentación interactiva (Swagger) |

## Variables de entorno

| Variable | Obligatoria | Por defecto |
|---|---|---|
| `PINECONE_API_KEY` | **sí** | — |
| `PINECONE_INDEX_NAME` | no | `ofertas-laborales` |
| `MODELO_EMBEDDINGS` | no | `all-MiniLM-L6-v2` |

Sin `PINECONE_API_KEY` el proceso no arranca: falla al importar `app/config.py`.
Va en el archivo `.env` de esta carpeta; parte de `.env.example`.

El puerto se elige al lanzar uvicorn (`--port 8000`), no por variable de entorno.

## Datos

`data/ofertas_busqueda.parquet` (~27 MB) viene incluido y es lo único que la API
necesita en tiempo de ejecución. Contiene solo las 13 columnas que la búsqueda
usa, con tipos categóricos y enteros cortos: ocupa 42 MB en memoria frente a los
2.858 MB del dataset completo, sin cambiar un solo resultado.

Para regenerarlo tras un cambio en los notebooks, con los dos parquet de Colab en
`data/`:

```powershell
python generar_datos_busqueda.py
```
