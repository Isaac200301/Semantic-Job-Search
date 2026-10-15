# Semantic-Job-Search

**Proyecto Integrador 1 — Deus Ex Code**
Ingeniería de Sistemas

Motor de búsqueda semántica de ofertas laborales: el usuario escribe lo que busca
en lenguaje natural ("python developer with machine learning experience") y el
sistema devuelve ofertas relevantes **por significado**, no por coincidencia de
palabras, con filtros estructurados encima (país, modalidad, experiencia, salario).

### Participantes

- Simon Correa Rios
- Pablo Serna Valencia
- Juan Sebastian Andraus Lopez
- Isaac Cano Orozco

---

## 1. Qué hay en este repositorio

```
Semantic-Job-Search/
├── notebooks/     # investigación: EDA, limpieza, embeddings, evaluación
├── api/           # servicio FastAPI que expone la búsqueda
├── frontend/      # prototipo de interfaz en Streamlit
└── README.md      # este archivo
```

Las tres piezas encajan así:

```
  notebooks  ──genera──>  Pinecone (3.760 vectores)
      │                          ▲
      └──genera──> parquet       │ consulta
                      │          │
                      ▼          │
                     api  ───────┘
                      ▲
                      │ HTTP
                   frontend
```

Los notebooks son el trabajo de investigación y **ya se ejecutaron**: su producto
son los vectores que viven en Pinecone y dos archivos parquet en Google Drive. La
API y el frontend consumen ese producto; no hace falta volver a correr los
notebooks para levantar el sistema.

---

## 2. Decisiones del proyecto (resumen)

| Decisión | Valor | Dónde se tomó |
|---|---|---|
| Dataset | Kaggle `ravindrasinghrana/job-description-dataset` — 1.615.940 ofertas | `01_EDA.ipynb` |
| Modelo de embeddings | `all-MiniLM-L6-v2` (384 dimensiones) | `05_Evaluacion_Metricas.ipynb` |
| Base vectorial | Pinecone, índice `ofertas-laborales` | `04_BaseDatosVectorial.ipynb` |
| Estrategia de indexado | Deduplicar por plantilla de texto | `03_Embeddings_BusquedaVectorial.ipynb` |

**El hallazgo central del proyecto:** el dataset es sintético y solo tiene **3.760
textos únicos** entre sus 1,6 millones de filas. En vez de generar 1,6M de
embeddings (caros y redundantes), se deduplica por `texto_combinado`, se asigna un
`template_id`, y se embeben solo las 3.760 plantillas. Después la búsqueda expande
de plantilla a ofertas reales. El índice vectorial queda **430 veces más pequeño
que el dataset sin perder una sola oferta**.

Resultado de la evaluación sobre 15 consultas etiquetadas manualmente:

| Sistema | precision@5 | precision@10 | MRR | nDCG@10 | ms |
|---|---|---|---|---|---|
| **MiniLM** | 1.000 | 1.000 | 1.000 | **0.986** | 9.2 |
| MPNet | 1.000 | 1.000 | 1.000 | 0.978 | 16.7 |
| TF-IDF (léxico) | 0.933 | 0.933 | 0.933 | 0.933 | 4.0 |

Se eligió MiniLM: iguala o supera a MPNet y es casi el doble de rápido.

---

## 3. Requisitos previos

- **Python 3.11 o superior.** La API se probó en 3.14.3 y el frontend en 3.13.2
  y 3.14.3.
- **La API key de Pinecone** del equipo (pídela a quien creó el índice).
- **Los dos parquet** generados en Colab (ver paso 4.3).
- ~3 GB de disco para las dependencias (PyTorch es la mayor parte).
- ~7 GB de RAM libre para correr la API (ver sección 8).

> **Ojo si tienes varios Python instalados.** Usa el mismo intérprete para todo.
> Para saber cuál está usando tu terminal: `python -c "import sys; print(sys.executable)"`.

---

## 4. Poner a andar la API

Todo esto se hace **una sola vez**.

### 4.1 Entorno virtual e instalación

**Windows (PowerShell):**

```powershell
cd api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell bloquea la activación del entorno, corre antes, en esa misma
terminal: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

**Linux / macOS:**

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

La instalación descarga PyTorch y tarda varios minutos. Es normal.

> PowerShell 5.1 **no admite `&&`** para encadenar comandos. Ejecuta una
> instrucción por línea, o separa con `;`.

### 4.2 Credenciales

```powershell
copy .env.example .env      # Linux/macOS: cp .env.example .env
```

Abre `api/.env` y pon la API key real:

```
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=ofertas-laborales
```

El archivo `.env` está en el `.gitignore`. **Nunca lo subas al repositorio.**

### 4.3 Los datos

La API necesita dos archivos que están en Google Drive, en
`MyDrive/proyecto_integrador/data/processed/`:

- `job_descriptions_clean.parquet` (444 MB)
- `job_id_template_map.parquet` (16 MB)

**Opción A — copiarlos a mano:** descárgalos de Drive y ponlos en `api/data/`.

**Opción B — descarga automática:** pon los IDs de Drive en `api/.env` como
`DRIVE_FILE_ID_CLEAN` y `DRIVE_FILE_ID_MAPEO`, y luego:

```powershell
$env:DRIVE_FILE_ID_CLEAN = "..."
$env:DRIVE_FILE_ID_MAPEO = "..."
python descargar_datos.py
```

> Nota: `descargar_datos.py` lee las variables del **entorno**, no del archivo
> `.env` (no llama a `load_dotenv()`). Por eso hay que exportarlas a mano como
> muestra el ejemplo, o añadir la llamada al script.

No hace falta el índice FAISS ni el `.npy` de embeddings: esos ya están "vivos"
dentro de Pinecone. La API solo necesita los datos tabulares.

### 4.4 Levantar la API

```powershell
python -m uvicorn app.main:app --reload
```

Desde la carpeta `api/`, no desde la raíz — `load_dotenv()` busca el `.env` en el
directorio actual. Espera a ver `Application startup complete`: la API carga el
modelo y el dataset al arrancar, y toma alrededor de un minuto.

Abre **http://localhost:8000/docs** para la documentación interactiva (Swagger),
donde se puede probar cada endpoint desde el navegador.

---

## 5. Poner a andar el frontend

En **otra terminal**, con la API ya corriendo:

```powershell
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

Abre **http://localhost:8501**.

Por defecto apunta a `http://localhost:8000`. Para apuntar a otra URL, copia
`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y edita `API_URL`,
o define la variable de entorno `API_URL`.

Detalles de la interfaz en [frontend/README.md](frontend/README.md).

---

## 6. Endpoints de la API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Chequeo de que el servicio está arriba |
| POST | `/buscar` | Búsqueda semántica con filtros opcionales |
| GET | `/filtros/paises` | Países disponibles (216) |
| GET | `/filtros/modalidades` | Modalidades disponibles (5) |

### Cuerpo de `/buscar`

```json
{
  "consulta": "python developer with machine learning experience",
  "k_plantillas": 5,
  "max_resultados": 20,
  "pais": "Colombia",
  "modalidad": "Full-Time",
  "experiencia_min": 3,
  "salario_min": 60,
  "salario_max": 120
}
```

Solo `consulta` es obligatoria. Los filtros que se omiten no se aplican.

- `experiencia_min` son los **años de experiencia del candidato**: se devuelven
  ofertas cuyo rango `[Experience min, Experience max]` lo cubre.
- `salario_min` / `salario_max` van en **miles de USD**, igual que el campo
  `Salary Range` del dataset (`$59K-$99K`).
- `k_plantillas` es cuántas plantillas semánticas pedirle a Pinecone. Subirlo
  amplía la variedad temática de los resultados.

### Ejemplo

**Windows (PowerShell).** No uses `curl` aquí: el alias de PowerShell mangla el
escapado del JSON. Lo idiomático es `Invoke-RestMethod`:

```powershell
$cuerpo = @{
    consulta       = "python developer with machine learning experience"
    pais           = "Colombia"
    max_resultados = 2
} | ConvertTo-Json

$r = Invoke-RestMethod -Uri "http://localhost:8000/buscar" -Method Post -ContentType "application/json" -Body $cuerpo
$r.resultados | Select-Object 'Job Title', 'Country', 'Work Type', similitud | Format-Table
```

**Linux / macOS / Git Bash:**

```bash
curl -X POST http://localhost:8000/buscar \
  -H "Content-Type: application/json" \
  -d '{"consulta": "python developer with machine learning experience", "pais": "Colombia"}'
```

Lo más cómodo para probar sigue siendo Swagger en `/docs`, sin necesidad de nada
de esto.

---

## 7. Los notebooks

Están en [notebooks/](notebooks/) y se ejecutan en Google Colab, montando Drive
en `MyDrive/proyecto_integrador/`. Se corren en orden; cada uno depende del
anterior.

| Notebook | Qué hace | Produce |
|---|---|---|
| `01_EDA.ipynb` | Explora el dataset crudo: nulos, duplicados, distribuciones | Conclusiones para la limpieza |
| `02_Preprocesamiento.ipynb` | Limpia texto, parsea experiencia y salario, arma `texto_combinado` | `job_descriptions_clean.parquet` |
| `03_Embeddings_BusquedaVectorial.ipynb` | Deduplica por plantilla, genera embeddings, índice FAISS de baseline | `embeddings_plantillas.npy`, `plantillas_meta.parquet`, `job_id_template_map.parquet` |
| `04_BaseDatosVectorial.ipynb` | Sube las plantillas a Pinecone y define la búsqueda | Índice `ofertas-laborales` poblado |
| `05_Evaluacion_Metricas.ipynb` | Compara MiniLM, MPNet y TF-IDF con precision@k, MRR y nDCG | La decisión final del modelo |

**No hace falta volver a correrlos** para levantar el sistema. Solo si se cambia
el modelo de embeddings, la estrategia de indexado o el dataset.

---

## 8. Estado actual y limitaciones conocidas

### Funciona y está verificado

El sistema completo se probó de punta a punta contra Pinecone real: los cuatro
endpoints responden, la búsqueda con los ocho parámetros funciona, los filtros sin
coincidencias devuelven cero resultados en vez de error, y el frontend se ejecuta
sin excepciones.

Cobertura confirmada: **3.760 plantillas únicas en el dataset completo y 3.760
vectores en Pinecone.** Toda oferta es alcanzable por la búsqueda.

### Consumo de memoria: resuelto

La API cargaba las 25 columnas del dataset, incluidas `Job Description`,
`texto_combinado`, `Company Profile` y `Benefits`, que la búsqueda **nunca usa**.
Ahora carga solo las 13 necesarias, desde un único parquet reducido:

| | Antes | Ahora |
|---|---|---|
| Archivos de datos | 438,6 MB (2 archivos) | **27,4 MB** (1 archivo, versionado) |
| DataFrame en memoria | 2.845 MB | **304 MB** |
| Proceso de la API | 6,74 GB | **1,1 GB** (working set) |
| Tiempo de arranque | ~60 s | **4 s** |

Los resultados de búsqueda son **idénticos**: se verificó ejecutando las mismas
consultas con ambas cargas y comparando las respuestas completas (6 de 6
iguales, además de las listas de países y modalidades). Lo semántico ocurre
entero dentro de Pinecone; el parquet solo sirve para expandir `template_id` a
ofertas reales, filtrar y mostrar.

El archivo `api/data/ofertas_busqueda.parquet` está versionado, así que un clon
del repositorio ya puede levantar la API sin pasar por Google Drive. Para
regenerarlo tras un cambio en los notebooks: `python generar_datos_busqueda.py`.

### Otros pendientes

- `@app.on_event("startup")` en `api/app/main.py` está obsoleto en FastAPI
  moderno; migrar a *lifespan handlers*.
- CORS está abierto a `*` en `api/app/main.py`. Cerrarlo al dominio real del
  frontend antes de exponer la API públicamente.
- No hay autenticación. Si la API queda pública antes de la sustentación,
  conviene al menos una API key propia.
- Cachear consultas repetidas (por ejemplo con `functools.lru_cache`) si en la
  demo se hacen muchas búsquedas iguales.

---

## 9. Despliegue

El sistema está desplegado y es público. **No hay que encender nada** para usarlo.

| Pieza | Dónde | URL |
|---|---|---|
| API | Google Cloud Run (`us-central1`) | `https://semantic-job-search-api-6s7pi2umqq-uc.a.run.app` |
| Documentación interactiva | la misma, en `/docs` | [Swagger](https://semantic-job-search-api-6s7pi2umqq-uc.a.run.app/docs) |
| Frontend | Streamlit Community Cloud | ver la app del equipo |

El frontend toma la URL de la API de sus *Secrets* (`API_URL`), o del campo
**URL de la API** de la barra lateral si se quiere apuntar a otra instancia —por
ejemplo una API corriendo en local durante el desarrollo.

### Cómo se construye el despliegue

La API se despliega desde `api/`, que contiene el `Dockerfile`. El contenedor
instala PyTorch en su variante solo-CPU, descarga el modelo de embeddings al
construir la imagen —para que el arranque en frío no dependa de Hugging Face— y
toma el puerto de la variable `PORT` que inyecta Cloud Run.

```powershell
gcloud run deploy semantic-job-search-api --source api --region us-central1 --allow-unauthenticated --memory 1Gi
```

`--memory 1Gi` no es opcional: el valor por defecto de Cloud Run es 512 MiB y la
API necesita unos 700 MB. Con el defecto, el contenedor entra en bucle de
reinicios sin que el error indique la causa.

Los archivos `api/.dockerignore` y `api/.gcloudignore` tampoco son prescindibles.
El primero evita que el entorno virtual, los parquet de 438 MB y el `.env` con la
clave de Pinecone acaben dentro de la imagen, que pasaría de 2,6 GB a casi 13 GB.
El segundo controla qué se sube a Cloud Build y garantiza que
`data/ofertas_busqueda.parquet` sí viaje, porque sin él el contenedor no arranca.

La clave de Pinecone se configura como variable del servicio en Cloud Run.

### Arranque en frío

Cloud Run escala a cero, así que no genera costo cuando nadie lo usa, pero la
primera petición tras un periodo inactivo puede tardar entre 30 y 60 segundos.
Antes de una demostración conviene abrir la URL con unos minutos de antelación.

---

## 10. Qué NO se sube al repositorio

Está cubierto por el `.gitignore`, pero conviene tenerlo presente:

| Archivo | Por qué |
|---|---|
| `api/.env` | Contiene la API key de Pinecone |
| `frontend/.streamlit/secrets.toml` | Configuración local |
| `api/data/*.parquet` | 460 MB en total |
| `.venv/` | Entorno virtual, se regenera |
| `__pycache__/` | Artefactos de Python |

Los archivos `.env.example` y `secrets.toml.example` **sí** se versionan: son las
plantillas para que cada quien arme su configuración local.
