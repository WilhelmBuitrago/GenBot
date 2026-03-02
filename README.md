# GenBot MVP Backend

## Requisitos
- Python 3.11+
- Variables de entorno configuradas

## Instalacion local
1. Crear entorno virtual.
2. Instalar dependencias:
   - `pip install -r requirements.txt`
3. Copiar `.env.example` a `.env` y completar valores.
4. Ejecutar:
   - `uvicorn app.main:app --reload`

## Variables de entorno
- APP_NAME
- ENVIRONMENT
- CORS_ORIGINS
- DATA_DIR
- LLM_PROVIDER
- LLM_BASE_URL
- LLM_CHAT_PATH
- LLM_MODEL
- LLM_API_KEY
- LLM_TIMEOUT_SECONDS
- LLM_REFERER
- LLM_TITLE
- MEMORY_MAX_MESSAGES

## Docker
1. Construir imagen:
   - `docker build -t genbot .`
2. Ejecutar:
   - `docker run -p 8000:8000 --env-file .env genbot`

## Migracion a Google Sheets API
- Implementar `load_from_google_api` en `app/services/sheet_loader.py`.
- Reemplazar `CSVSheetLoader` por un loader compatible sin tocar normalizador ni rutas.
