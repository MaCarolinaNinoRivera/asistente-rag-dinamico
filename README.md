# Asistente RAG

Un asistente conversacional reutilizable: responde las dudas de los usuarios de una aplicación según **la pantalla donde están**, **lo que se ha hablado** y **una base de conocimiento** (RAG). Hoy lo usa Agro Inventory como "Aliado del Campesino", pero no sabe nada de agricultura: todo lo propio de cada aplicación (personalidad, pantallas, documentos, verificación de usuarios) es configuración del **proyecto**.

- **API:** FastAPI (asíncrona) · **Base de datos:** PostgreSQL 16 con `pgvector` · **IA:** Gemini (respuestas y vectores) · **Documentos:** carpeta local o S3.

## Cómo responde una pregunta

1. **Quién pregunta.** El widget envía el token de la aplicación. El asistente lo verifica en el backend de esa aplicación (ver [Autenticación](#autenticación)).
2. **Límite diario.** Si el usuario ya llegó al máximo de preguntas de hoy, se le avisa y no se gasta en IA.
3. **Contexto.** Se busca la conversación activa (o se crea una tras 2 horas sin mensajes), los últimos 10 mensajes y la **ficha de la pantalla** actual.
4. **Búsqueda híbrida en el conocimiento.** Por significado (vectores de 768 dimensiones, índice HNSW) y por palabras exactas (búsqueda de texto en español). Se combinan con *Reciprocal Rank Fusion*, con una pequeña ventaja para los fragmentos de la pantalla actual.
5. **Respuesta.** Gemini recibe la personalidad y las reglas del proyecto, más la pantalla, el conocimiento, la conversación y la pregunta (`app/core/prompt.py`).
6. **Registro.** Se guardan la pregunta, la respuesta, las fuentes usadas y el **consumo** (tokens y costo).

## Arquitectura

Arquitectura hexagonal: el núcleo (`core`) no depende de la base de datos ni de Gemini. Se conecta con ellos por **puertos** (interfaces), y los **adaptadores** los implementan. Así se puede cambiar Gemini por otro proveedor, o la carpeta local por S3, sin tocar la lógica.

```
asistente-rag/
├── main.py                       Arranque: FastAPI, CORS, rutas
├── init.sql                      Esquema completo (base nueva)
├── migraciones/                  Cambios para una base que ya existe (002, 003, 004…)
├── conocimiento/<proyecto>/      Textos del equipo, versionados en Git
│   └── pantallas.yaml            Ficha de cada pantalla
├── static/                       Widget web (widget.js, widget.css) y página de prueba
└── app/
    ├── config.py                 Configuración (variables de entorno / .env)
    ├── core/                     NÚCLEO: reglas del negocio
    │   ├── prompt.py             Personalidad, reglas y cómo se arma cada pregunta
    │   ├── consumo.py            Costo de cada llamada (precios desde la base)
    │   ├── entities.py           Fragmento, respuesta del modelo, resultado de una carga
    │   └── use_cases/            chat, calificación, carga de documentos, administración
    ├── ports/                    PUERTOS (interfaces)
    │   ├── llm_service.py        Vectores y respuestas
    │   ├── vector_repository.py  Conocimiento, conversaciones, consumo
    │   ├── admin_repository.py   Consultas y mantenimiento
    │   ├── identidad.py          ¿De quién es este token?
    │   └── storage_service.py    Dónde se guardan los archivos originales
    ├── adapters/
    │   ├── inbound/              Lo que RECIBE peticiones
    │   │   ├── chat_controller.py, admin_controller.py
    │   │   └── autenticacion.py  Decide quién pregunta
    │   └── outbound/             Lo que el asistente USA
    │       ├── gemini_adapter.py
    │       ├── postgres_adapter.py, postgres_admin_adapter.py, database.py
    │       ├── identidad_http_adapter.py   Verifica tokens en la app (con caché)
    │       └── storage_local_adapter.py, s3_adapter.py, storage_factory.py
    └── utils/logger.py
```

### Tablas (esquema `asistente`)

| Tabla | Qué guarda |
|---|---|
| `proyectos` | Cada aplicación: personalidad, minutos para una conversación nueva, límite diario, cómo verificar sus tokens |
| `pantallas` | Las fichas de las pantallas (desde `pantallas.yaml`) |
| `documentos` y `fragmentos` | El conocimiento: cada documento con su huella SHA-256, y sus fragmentos con su vector |
| `conversaciones` y `mensajes` | El historial, con la pantalla, las fuentes usadas y los tokens de cada respuesta |
| `calificaciones` | 👍/👎 (guardados como 5 y 1, en una escala de 1 a 5) |
| `consumo` | Cada llamada a Gemini: operación, modelo, tokens y costo |
| `configuracion_modelo` | El modelo de chat y el de vectores, con sus precios |

## Correrlo en local

```bash
cp .env.example .env               # y completa GEMINI_API_KEY y ADMIN_API_KEY
docker compose up -d               # PostgreSQL con pgvector; init.sql crea el esquema la primera vez
pip install -r requirements.txt
python main.py                     # http://localhost:8001/docs
```

Para generar la clave de administración sin que se vea en pantalla:

```bash
echo "ADMIN_API_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" >> .env
```

**Si la base ya existía**, aplica las migraciones en orden (todas se pueden ejecutar más de una vez):

```bash
for m in migraciones/0*.sql; do docker compose exec -T db psql -U postgres -d bd_asistente < "$m"; done
```

Después, la primera vez:

1. `POST /api/v1/admin/pantallas/sincronizar`: carga las fichas de pantalla.
2. `POST /api/v1/admin/ingestar-documento`: carga el glosario, las preguntas frecuentes y las guías.
3. `PUT /api/v1/admin/modelos/chat_default`: configura los precios (ver [Consumo](#consumo-de-ia)).

## Servicios

La documentación interactiva está en `/docs`. Los de **Administración** exigen la cabecera `X-Admin-Key` con el valor de `ADMIN_API_KEY`. Si esa variable no está configurada, la administración queda **cerrada**.

### Chat

| Servicio | Para qué |
|---|---|
| `POST /api/v1/chat` | Hacer una pregunta. Cuerpo: `pregunta`, `pantalla_codigo`, `proyecto_codigo`. Cabecera: `Authorization: Bearer <token>` |
| `POST /api/v1/chat/calificar` | Calificar una respuesta propia: `mensaje_id`, `calificacion` (1 a 5), `comentario` opcional |

```bash
curl -X POST http://localhost:8001/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"pregunta": "¿qué hago acá?", "pantalla_codigo": "productos", "proyecto_codigo": "agro"}'
```

Respuestas posibles: **200** con la respuesta · **401** sin token o con la sesión cerrada · **404** el proyecto no existe · **429** se alcanzó el límite del día · **503** Gemini o la verificación del token no respondieron (con un mensaje para el usuario).

### Administración del conocimiento

| Servicio | Para qué |
|---|---|
| `POST /admin/ingestar-documento` | Cargar un PDF, TXT o MD (`tipo`: manual, glosario, pantalla, faq, guía; `pantalla_codigo` opcional). Si el archivo no cambió, no se reprocesa; si cambió, reemplaza la versión anterior. Los `.md` se parten por títulos |
| `GET /admin/documentos` | Los documentos cargados |
| `GET /admin/documentos/{id}/fragmentos` | Cómo quedó partido un documento |
| `DELETE /admin/documentos/{id}` | Retirar un documento (el asistente deja de usarlo de inmediato; el original se conserva) |
| `POST /admin/buscar` | Qué encontraría el chat para una pregunta, **sin gastar en la respuesta**: los fragmentos, su similitud, si se encontraron por significado o por palabras, y el mensaje completo que recibiría el modelo |
| `GET /admin/pantallas` | Las fichas de pantalla en la base |
| `POST /admin/pantallas/sincronizar` | Deja la base igual a `conocimiento/<proyecto>/pantallas.yaml`: crea, actualiza y desactiva. Si el archivo tiene un error, no cambia nada y dice qué corregir |

### Administración de proyectos, modelos y consumo

| Servicio | Para qué |
|---|---|
| `GET /admin/proyectos` | Los proyectos, con sus documentos y pantallas |
| `PUT /admin/proyectos/{codigo}` | Cambiar solo lo que se envía: `personalidad`, `limite_mensajes_dia` (0 = sin límite), `minutos_inactividad`, `url_validacion_token`, `campo_usuario_id`, `activo` |
| `GET /admin/modelos` | Los modelos configurados y sus precios |
| `PUT /admin/modelos/{codigo}` | Cambiar el modelo de chat y sus precios. Con `probar: true` (por defecto), si el modelo no responde, no se guarda |
| `GET /admin/consumo?dias=30` | Llamadas, tokens y costo: en total, por día, por operación y por modelo |

### Salud

`GET /health`: si el servicio está en pie.

## Autenticación

**El asistente nunca conoce las claves con que cada aplicación firma sus tokens.** Si las tuviera, también podría fabricar tokens, y cada proyecto nuevo obligaría a compartirlas. En su lugar, le pregunta a la aplicación de quién es cada token:

```
Widget ──(Authorization: Bearer <token>)──▶ Asistente
                                              │  1. ¿Lo verifiqué hace menos de 5 minutos? → uso la caché
                                              │  2. Si no: GET <url_validacion_token> con el mismo token
                                              ▼
                                         Aplicación (por ejemplo, GET /api/v1/auth/me de Agro)
                                              │  200 {"id": "e40ffaa4-…", …} → el usuario es e40ffaa4-…
                                              │  401 / 403                    → sesión cerrada: el asistente responde 401
                                              │  sin respuesta                → el asistente responde 503
```

- **El usuario sale siempre del token**, nunca del cuerpo de la petición: nadie puede hacerse pasar por otro.
- **La caché guarda la huella del token** (SHA-256), nunca el token, durante `SEGUNDOS_CACHE_TOKEN` (por defecto 300).
- **En desarrollo**, con `AUTENTICACION_REQUERIDA=false`, se acepta `usuario_id` en el cuerpo cuando no llega token. **Nunca en producción.**
- **La administración** usa otra cosa: la clave `X-Admin-Key`, que solo deben tener los backends y el equipo técnico, nunca un front.

### Conectar otro proyecto

1. **La aplicación debe tener un servicio que, con el token del usuario, devuelva sus datos** (normalmente ya existe: `/me`, `/perfil`…). Debe responder 401 si la sesión no es válida o se cerró.
2. **Crear el proyecto** con una semilla SQL:
   ```sql
   INSERT INTO asistente.proyectos (codigo, nombre, url_validacion_token, campo_usuario_id, limite_mensajes_dia)
   VALUES ('ventas', 'App de ventas', 'http://ventas-api:8000/api/me', 'usuario_id', 30);
   ```
   `campo_usuario_id` es el campo de esa respuesta que trae el id del usuario.
3. **Opcional:** su personalidad, con `PUT /admin/proyectos/ventas` (si no tiene, usa la de por defecto).
4. **Sus pantallas** en `conocimiento/ventas/pantallas.yaml`, y sincronizarlas con `?proyecto_codigo=ventas`.
5. **Sus documentos**, con `proyecto_codigo=ventas` al cargarlos.
6. **Su dominio en `ALLOWED_ORIGINS`.**
7. **En su front**, el widget con `data-proyecto="ventas"` y, al iniciar sesión, `AsistenteAgro.setToken(token)`.

Si algún día un proyecto usa tokens firmados con una clave pública (por ejemplo JWKS de un proveedor de identidad), se puede agregar otro adaptador del puerto `identidad.py` que los verifique sin consultar a la aplicación. El resto no cambia.

## Consumo de IA

Cada llamada a Gemini queda en `asistente.consumo`:

| Operación | Qué es | Tokens |
|---|---|---|
| `chat` | Cada respuesta | Exactos (los informa Gemini) |
| `busqueda` | El vector de cada pregunta | Estimados (~4 caracteres por token) |
| `ingesta` | Los vectores de un documento al cargarlo | Estimados |

**Los precios no están en el código.** Van en `configuracion_modelo.parametros_extra`, en dólares por millón de tokens. Confirma los valores con la lista de precios vigente de Google antes de ponerlos:

```bash
curl -X PUT http://localhost:8001/api/v1/admin/modelos/chat_default -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"nombre_modelo": "gemini-3.1-flash-lite", "parametros_extra": {"precio_entrada_millon": 0.10, "precio_salida_millon": 0.40}}'
```

Haz lo mismo con `embedding_default` (solo `precio_entrada_millon`). Mientras un modelo no tenga precio, su costo queda vacío y aparece en `modelos_sin_precio`.

**En Agro**, la pantalla *Consumo de IA* muestra una tarjeta del asistente. La pide el **backend** de Agro (`GET /api/v1/analitica/ia-consumo/asistente`), que guarda la clave de administración como secreto. El front nunca la ve.

## Producción

| Qué | Cómo |
|---|---|
| Publicación | Bajo el dominio de la aplicación, por ejemplo `https://agro.bancocontactar.com/asistente/`, con Nginx: un solo certificado, y el asistente no queda expuesto directamente |
| `url_validacion_token` | La dirección **interna** de la aplicación (por ejemplo `http://api:8000/api/v1/auth/me`): más rápida y sin salir a internet |
| `ALLOWED_ORIGINS` | Solo los dominios reales, nunca `*` |
| `AUTENTICACION_REQUERIDA` | `true` |
| Secretos | `GEMINI_API_KEY`, `ADMIN_API_KEY` y la contraseña de la base, en el gestor de secretos (Secrets Manager en AWS) |
| Documentos | `STORAGE_TYPE=s3`, con el bucket, la región y el endpoint de la VPC. El permiso lo da el **rol de IAM** del contenedor, sin claves |
| Base de datos | Una base propia (`asistente_db`) en el servidor PostgreSQL, con la extensión `vector` activada |

```nginx
location /asistente/ {
    proxy_pass http://asistente:8001/;
    include /etc/nginx/proxy_comun.inc;
}
```

## Problemas comunes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| "No tengo certeza de dónde estás" | La pantalla no tiene ficha | `GET /admin/pantallas`; si falta, `POST /admin/pantallas/sincronizar`. El código debe ser igual al que envía el widget |
| "No tengo esa información" y sí está en un documento | La similitud mínima es alta para esa pregunta | `POST /admin/buscar` con la pregunta: mira la similitud del fragmento correcto y ajusta `SIMILITUD_MINIMA` (0,35 a 0,45) |
| 401 "Inicia sesión" | No llega el token | Revisa que el front lo envíe (`setToken` en el widget, o el componente de Agro con sesión abierta) |
| 401 "Tu sesión se cerró" | El servicio de verificación rechazó el token | Inicia sesión de nuevo; revisa que `url_validacion_token` sea correcta |
| 503 "No pude verificar tu sesión" | La aplicación no responde a la verificación | Revisa que esté en pie y que la dirección interna sea alcanzable desde el contenedor del asistente |
| 429 | Se alcanzó el límite del día | Es lo esperado; se ajusta con `PUT /admin/proyectos/{codigo}` |
| El costo sale en 0 | Falta el precio del modelo | `GET /admin/consumo`: revisa `modelos_sin_precio` |

**Para ver el prompt completo de cada pregunta:** `LOG_LEVEL=DEBUG`. En producción, déjalo en `INFO`: las conversaciones son privadas y no deben quedar en los registros.

## Lo que sigue

- **Herramientas:** que el asistente consulte los datos del propio usuario (primeros pasos, lotes, tendencias), con su mismo token.
- **Memoria de días anteriores:** un resumen corto de cada conversación.
- **Voz:** notas de voz de ida y vuelta.
- **Retención:** cuánto se guardan las conversaciones, y un botón para borrar el historial.
