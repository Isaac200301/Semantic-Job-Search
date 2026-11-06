"""Paquete de la API de búsqueda semántica.

Este archivo deja `app` como paquete regular en lugar de un *namespace
package*. Sin él, cualquier módulo llamado `app.py` que esté en el sys.path
—por ejemplo el `frontend/app.py` de Streamlit— tiene prioridad y se importa
en su lugar. No cambia cómo arranca la API: `uvicorn app.main:app` sigue igual.
"""
