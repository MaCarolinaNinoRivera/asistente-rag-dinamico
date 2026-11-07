from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Asistente RAG Agro"
    ENVIRONMENT: str = "development"
    PORT: int = 8001
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password_asistente@localhost:5433/bd_asistente"
    GEMINI_API_KEY: str = ""
    # Orígenes que pueden usar el asistente desde el navegador, separados por coma.
    # Desplegado: SOLO los dominios reales (por ejemplo https://agro.bancocontactar.com), nunca "*".
    ALLOWED_ORIGINS: str = "http://localhost:8081"

    # Quién pregunta: el token de la aplicación, verificado en su propio backend (ver 003).
    # False solo en desarrollo: acepta el usuario_id del cuerpo cuando no llega token.
    AUTENTICACION_REQUERIDA: bool = True
    SEGUNDOS_CACHE_TOKEN: int = 300          # un token verificado se recuerda 5 minutos
    ZONA_HORARIA: str = "America/Bogota"     # el límite diario se reinicia a medianoche de aquí

    # Modelos. El de chat se elige en asistente.configuracion_modelo (este es solo el respaldo).
    # El de embeddings y sus dimensiones van aquí: cambiarlos obliga a recalcular todos los fragmentos.
    MODELO_CHAT_RESPALDO: str = "gemini-3.1-flash-lite"
    MODELO_EMBEDDING: str = "gemini-embedding-001"
    EMBEDDING_DIMENSIONES: int = 768          # pgvector indexa hasta 2.000; init.sql usa VECTOR(768)

    # Búsqueda
    PROYECTO_POR_DEFECTO: str = "agro"
    FRAGMENTOS_POR_RESPUESTA: int = 4
    SIMILITUD_MINIMA: float = 0.45            # por debajo, el fragmento no tiene que ver con la pregunta
    BONO_PANTALLA: float = 0.05               # ventaja para los fragmentos de la pantalla actual (0 = ninguna)

    # Fichas de pantallas y textos del equipo: conocimiento/<proyecto>/pantallas.yaml
    CARPETA_CONOCIMIENTO: str = "conocimiento"

    # Carga de documentos
    ADMIN_API_KEY: str = ""                   # obligatoria para /admin; sin ella, /admin queda cerrado
    MAX_MB_DOCUMENTO: int = 20
    TAMANO_FRAGMENTO: int = 1000              # caracteres
    SOLAPE_FRAGMENTO: int = 150

    STORAGE_TYPE: str = "local"
    AWS_S3_BUCKET: str = ""
    AWS_S3_REGION: str = "us-east-1"
    AWS_S3_ENDPOINT: str = ""
    AWS_S3_PREFIJO: str = "asistente/"
    # Solo para pruebas fuera de AWS: desplegado, el permiso lo da el rol de IAM (sin claves)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
