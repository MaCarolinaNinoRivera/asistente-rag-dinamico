-- =============================================================================
-- Asistente RAG · esquema de la base de datos
--
-- Se ejecuta solo la PRIMERA vez que se crea el contenedor de PostgreSQL (volumen vacío).
-- Para aplicarlo de nuevo en local:  docker compose down -v && docker compose up -d
--
-- Principios:
--   - Todo pertenece a un PROYECTO (el asistente sirve a varias aplicaciones).
--   - Vectores de 768 dimensiones: pgvector solo indexa hasta 2.000 (HNSW/IVFFlat).
--   - Cada documento tiene una huella (SHA-256): si no cambió, no se vuelve a procesar.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS asistente;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid() en PostgreSQL < 13

-- -----------------------------------------------------------------------------
-- 1. Proyectos: cada aplicación que usa el asistente
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.proyectos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo              VARCHAR(50)  NOT NULL UNIQUE CHECK (codigo ~ '^[a-z0-9_-]+$'),   -- 'agro'
    nombre              VARCHAR(100) NOT NULL,
    descripcion         TEXT,
    minutos_inactividad INT NOT NULL DEFAULT 120 CHECK (minutos_inactividad > 0),         -- luego, conversación nueva
    personalidad        TEXT,                                                              -- NULL = la del código
    url_validacion_token TEXT,                                 -- GET con el token → datos del usuario (ver 003)
    campo_usuario_id    VARCHAR(50) NOT NULL DEFAULT 'id',     -- campo de esa respuesta con el id del usuario
    limite_mensajes_dia INT NOT NULL DEFAULT 50 CHECK (limite_mensajes_dia >= 0),   -- 0 = sin límite
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    creado_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 2. Pantallas: qué es cada pantalla y qué se puede hacer en ella
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.pantallas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id UUID NOT NULL REFERENCES asistente.proyectos(id) ON DELETE CASCADE,
    codigo      VARCHAR(100) NOT NULL,                    -- 'productos', 'panorama'…
    nombre      VARCHAR(150) NOT NULL,
    descripcion TEXT,
    acciones    TEXT[] NOT NULL DEFAULT '{}',             -- "Crear un producto", "Definir su unidad"…
    activo      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (proyecto_id, codigo)
);

-- -----------------------------------------------------------------------------
-- 3. Documentos fuente (los originales viven en S3 o en la carpeta local)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.documentos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id     UUID NOT NULL REFERENCES asistente.proyectos(id) ON DELETE CASCADE,
    titulo          VARCHAR(255) NOT NULL,
    tipo            VARCHAR(50)  NOT NULL DEFAULT 'manual'
                    CHECK (tipo IN ('manual', 'glosario', 'pantalla', 'faq', 'guia')),
    pantalla_codigo VARCHAR(100),                         -- NULL = sirve en cualquier pantalla
    ruta_archivo    VARCHAR(500),                         -- s3://… o ruta local
    huella          CHAR(64) NOT NULL,                    -- SHA-256 del archivo
    fragmentos      INT NOT NULL DEFAULT 0,
    creado_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (proyecto_id, titulo)                          -- mismo título = nueva versión del mismo documento
);

-- -----------------------------------------------------------------------------
-- 4. Fragmentos con su vector (Gemini, 768 dimensiones normalizadas)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.fragmentos (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    documento_id     UUID NOT NULL REFERENCES asistente.documentos(id) ON DELETE CASCADE,
    proyecto_id      UUID NOT NULL REFERENCES asistente.proyectos(id) ON DELETE CASCADE,
    pantalla_codigo  VARCHAR(100),
    orden            INT  NOT NULL,
    contenido        TEXT NOT NULL,
    embedding        VECTOR(768) NOT NULL,
    modelo_embedding VARCHAR(100) NOT NULL,               -- si cambia el modelo, hay que recalcular
    metadata         JSONB NOT NULL DEFAULT '{}',
    -- Para la búsqueda por palabras exactas (búsqueda híbrida, segunda ronda)
    busqueda         TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', contenido)) STORED,
    creado_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (documento_id, orden)
);
CREATE INDEX IF NOT EXISTS ix_fragmentos_embedding ON asistente.fragmentos USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_fragmentos_busqueda  ON asistente.fragmentos USING gin (busqueda);
CREATE INDEX IF NOT EXISTS ix_fragmentos_proyecto  ON asistente.fragmentos (proyecto_id, pantalla_codigo);

-- -----------------------------------------------------------------------------
-- 5. Conversaciones (una nueva tras `minutos_inactividad` sin mensajes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.conversaciones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id     UUID NOT NULL REFERENCES asistente.proyectos(id) ON DELETE CASCADE,
    usuario_id      VARCHAR(100) NOT NULL,                -- el id del usuario EN su aplicación
    pantalla_inicial VARCHAR(100),
    titulo          VARCHAR(255),
    resumen         TEXT,
    creado_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()     -- último mensaje
);
CREATE INDEX IF NOT EXISTS ix_conversaciones_usuario
    ON asistente.conversaciones (proyecto_id, usuario_id, actualizado_at DESC);

-- -----------------------------------------------------------------------------
-- 6. Mensajes
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.mensajes (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversacion_id    UUID NOT NULL REFERENCES asistente.conversaciones(id) ON DELETE CASCADE,
    rol                VARCHAR(20) NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido          TEXT NOT NULL,
    pantalla_codigo    VARCHAR(100),
    fuentes_utilizadas JSONB,                             -- fragmentos usados, con su similitud
    modelo             VARCHAR(100),
    tokens_entrada     INT,
    tokens_salida      INT,
    duracion_ms        INT,
    creado_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_mensajes_conversacion ON asistente.mensajes (conversacion_id, creado_at);
CREATE INDEX IF NOT EXISTS ix_mensajes_rol_fecha ON asistente.mensajes (conversacion_id, rol, creado_at);
CREATE INDEX IF NOT EXISTS ix_conversaciones_proyecto_usuario ON asistente.conversaciones (proyecto_id, usuario_id);

-- -----------------------------------------------------------------------------
-- 7. Calificaciones: una por mensaje (si se califica otra vez, se actualiza)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.calificaciones (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mensaje_id   UUID NOT NULL UNIQUE REFERENCES asistente.mensajes(id) ON DELETE CASCADE,
    usuario_id   VARCHAR(100) NOT NULL,
    calificacion INT NOT NULL CHECK (calificacion BETWEEN 1 AND 5),
    comentario   TEXT,
    creado_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- 7b. Consumo de IA: tokens y costo de cada llamada a Gemini
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.consumo (
    id               BIGSERIAL PRIMARY KEY,
    proyecto_id      UUID NOT NULL REFERENCES asistente.proyectos(id) ON DELETE CASCADE,
    usuario_id       VARCHAR(100),                      -- NULL en la carga de documentos
    operacion        VARCHAR(30) NOT NULL CHECK (operacion IN ('chat', 'busqueda', 'ingesta', 'prueba_modelo')),
    modelo           VARCHAR(100) NOT NULL,
    tokens_entrada   INT NOT NULL DEFAULT 0,
    tokens_salida    INT NOT NULL DEFAULT 0,
    tokens_estimados BOOLEAN NOT NULL DEFAULT FALSE,    -- Gemini no informa los tokens de los vectores
    costo_usd        NUMERIC(12, 6),                    -- NULL si el modelo no tiene precio configurado
    duracion_ms      INT,
    creado_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_consumo_proyecto_fecha ON asistente.consumo (proyecto_id, creado_at DESC);


-- -----------------------------------------------------------------------------
-- 8. Configuración de modelos (se cambian sin tocar el código)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistente.configuracion_modelo (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre           VARCHAR(255) NOT NULL,
    codigo           VARCHAR(100) UNIQUE NOT NULL,        -- 'chat_default', 'embedding_default'
    proveedor        VARCHAR(50)  NOT NULL,
    nombre_modelo    VARCHAR(100) NOT NULL,
    parametros_extra JSONB NOT NULL DEFAULT '{}',
    esta_activo      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- Datos iniciales
-- -----------------------------------------------------------------------------
INSERT INTO asistente.proyectos (codigo, nombre, descripcion, url_validacion_token)
VALUES ('agro', 'Agro Inventory', 'Inventario, precios y recomendaciones para productores agrícolas',
        'http://localhost:8000/api/v1/auth/me')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO asistente.configuracion_modelo (nombre, codigo, proveedor, nombre_modelo)
VALUES ('Modelo de chat', 'chat_default', 'google', 'gemini-3.1-flash-lite'),
       ('Modelo de vectores (RAG)', 'embedding_default', 'google', 'gemini-embedding-001')
ON CONFLICT (codigo) DO NOTHING;
