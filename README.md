# Quiniela Mundial - Familiar

Pequeña aplicación Streamlit para gestionar una quiniela del Mundial.

Requisitos

- Python 3.10+ recomendado
- Git (opcional para desplegar en Streamlit Cloud)

Instalación y ejecución local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Despliegue en Streamlit Cloud

1. Empuja este repositorio a GitHub.
2. En https://share.streamlit.io crea una nueva app apuntando al repositorio y rama.
3. Streamlit instalará `requirements.txt` automáticamente y ejecutará `streamlit run app.py`.

Notas

- La aplicación persiste usuarios y pronósticos directamente en Google Sheets.
- Asegúrate de que `app.py` pueda acceder a Internet y que las credenciales de Google Sheets estén configuradas en `st.secrets`.
