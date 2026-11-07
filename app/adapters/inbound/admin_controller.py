import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbound.database import get_db
from app.adapters.outbound.gemini_adapter import GeminiAdapter
from app.adapters.outbound.postgres_adapter import PostgresVectorAdapter
from app.adapters.outbound.postgres_admin_adapter import PostgresAdminAdapter
from app.adapters.outbound.storage_factory import get_storage_adapter
from app.config import settings
from app.core.use_cases.admin_use_case import AdminUseCase, DatosInvalidos
from app.core.use_cases.ingestar_documento_use_case import EXTENSIONES, IngestarDocumentoUseCase
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/admin", tags=["Administración de Conocimiento"])
PROYECTO = Query(settings.PROYECTO_POR_DEFECTO, description="Código del proyecto")


def exigir_admin(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> None:
    """
    Cargar documentos cambia lo que el asistente le dice a los usuarios: solo con la clave de
    administración. Si ADMIN_API_KEY no está configurada, /admin queda cerrado (nunca abierto).
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="La administración está desactivada: configura ADMIN_API_KEY.")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Clave de administración inválida.")


@router.post("/ingestar-documento", dependencies=[Depends(exigir_admin)])
async def ingestar_documento(
    archivo: UploadFile = File(...),
    pantalla_codigo: Optional[str] = Form(None, description="Vacío = sirve en cualquier pantalla"),
    tipo: str = Form("manual", description="manual · glosario · pantalla · faq · guia"),
    proyecto_codigo: str = Form(settings.PROYECTO_POR_DEFECTO),
    db: AsyncSession = Depends(get_db),
):
    titulo = os.path.basename(archivo.filename or "").strip()
    extension = os.path.splitext(titulo)[1].lower()
    if extension not in EXTENSIONES:
        raise HTTPException(status_code=400, detail=f"Formato no soportado. Usa: {', '.join(sorted(EXTENSIONES))}.")

    # Archivo temporal seguro: el nombre lo pone el sistema, no el usuario (sin rutas tipo ../../)
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
        shutil.copyfileobj(archivo.file, tmp)
        ruta_temporal = tmp.name
    try:
        if os.path.getsize(ruta_temporal) > settings.MAX_MB_DOCUMENTO * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"El archivo supera {settings.MAX_MB_DOCUMENTO} MB.")
        use_case = IngestarDocumentoUseCase(get_storage_adapter(), PostgresVectorAdapter(db), GeminiAdapter())
        resultado = await use_case.ejecutar(ruta_temporal, titulo, pantalla_codigo or None, proyecto_codigo, tipo)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except HTTPException:
        raise
    except Exception:
        logger.exception("❌ Falló la carga de '%s'", titulo)
        raise HTTPException(status_code=500, detail="No se pudo cargar el documento. Revisa los registros del servidor.")
    finally:
        os.remove(ruta_temporal)

    mensajes = {"nuevo": "cargado", "actualizado": "actualizado (se reemplazó la versión anterior)",
                "sin_cambios": "ya estaba cargado y no cambió"}
    return {"status": "ok", "accion": resultado.accion, "documento_id": str(resultado.documento_id),
            "fragmentos": resultado.fragmentos, "mensaje": f"Documento '{titulo}' {mensajes[resultado.accion]}."}


# =============================================================================
# Consultas y mantenimiento (segunda ronda)
# =============================================================================
def _uc(db: AsyncSession) -> AdminUseCase:
    return AdminUseCase(PostgresAdminAdapter(db), PostgresVectorAdapter(db), GeminiAdapter(),
                        Path(settings.CARPETA_CONOCIMIENTO))


async def _proyecto(uc: AdminUseCase, codigo: str):
    try:
        return await uc.proyecto_id(codigo)
    except DatosInvalidos as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/proyectos", dependencies=[Depends(exigir_admin)])
async def listar_proyectos(db: AsyncSession = Depends(get_db)):
    """Los proyectos que usan el asistente, con cuántos documentos y pantallas tiene cada uno."""
    return await PostgresAdminAdapter(db).listar_proyectos()


class ProyectoCambios(BaseModel):
    """Solo se cambian los campos que se envían."""
    nombre: Optional[str] = Field(None, max_length=100)
    descripcion: Optional[str] = None
    personalidad: Optional[str] = Field(None, max_length=4000, description="Cómo habla el asistente en este proyecto")
    minutos_inactividad: Optional[int] = Field(None, ge=5, le=10080, description="Tras este tiempo sin mensajes, conversación nueva")
    limite_mensajes_dia: Optional[int] = Field(None, ge=0, le=1000, description="Preguntas por usuario al día (0 = sin límite)")
    url_validacion_token: Optional[str] = Field(None, max_length=500, description="GET con el token → datos del usuario")
    campo_usuario_id: Optional[str] = Field(None, max_length=50, description="Campo de esa respuesta con el id del usuario")
    activo: Optional[bool] = None


@router.put("/proyectos/{codigo}", dependencies=[Depends(exigir_admin)])
async def actualizar_proyecto(codigo: str, cambios: ProyectoCambios, db: AsyncSession = Depends(get_db)):
    """Personalidad, límite diario, minutos para una conversación nueva y verificación del token."""
    proyecto = await PostgresAdminAdapter(db).actualizar_proyecto(codigo, cambios.model_dump(exclude_unset=True))
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"No existe el proyecto '{codigo}'.")
    return proyecto


@router.get("/documentos", dependencies=[Depends(exigir_admin)])
async def listar_documentos(proyecto_codigo: str = PROYECTO, db: AsyncSession = Depends(get_db)):
    """Los documentos cargados en el RAG, del más reciente al más viejo."""
    uc = _uc(db)
    return await uc.admin.listar_documentos(await _proyecto(uc, proyecto_codigo))


@router.get("/documentos/{documento_id}/fragmentos", dependencies=[Depends(exigir_admin)])
async def ver_fragmentos(documento_id: UUID, db: AsyncSession = Depends(get_db)):
    """Cómo quedó partido un documento: sirve para revisar que cada fragmento tenga sentido solo."""
    fragmentos = await PostgresAdminAdapter(db).fragmentos_de(documento_id)
    if fragmentos is None:
        raise HTTPException(status_code=404, detail="No existe ese documento.")
    return fragmentos


@router.delete("/documentos/{documento_id}", dependencies=[Depends(exigir_admin)])
async def eliminar_documento(documento_id: UUID, db: AsyncSession = Depends(get_db)):
    """Retira un documento y sus fragmentos: el asistente deja de usarlo de inmediato.
    El archivo original se conserva en el almacenamiento (S3 o la carpeta local)."""
    eliminado = await PostgresAdminAdapter(db).eliminar_documento(documento_id)
    if not eliminado:
        raise HTTPException(status_code=404, detail="No existe ese documento.")
    return {"status": "ok", "mensaje": f"Se retiró '{eliminado['titulo']}' ({eliminado['fragmentos']} fragmentos).",
            "archivo_original": eliminado["ruta_archivo"]}


class BusquedaRequest(BaseModel):
    pregunta: str = Field(..., min_length=1, max_length=2000)
    pantalla_codigo: Optional[str] = None
    proyecto_codigo: str = settings.PROYECTO_POR_DEFECTO
    similitud_minima: Optional[float] = Field(None, ge=0, le=1, description="Vacío = la de la configuración")


@router.post("/buscar", dependencies=[Depends(exigir_admin)])
async def probar_busqueda(payload: BusquedaRequest, db: AsyncSession = Depends(get_db)):
    """
    Qué encontraría el chat para una pregunta, sin gastar en la respuesta del modelo: los
    fragmentos (con su similitud y si los encontró por significado o por palabras), la ficha de la
    pantalla y el mensaje completo que recibiría el modelo. Sirve para calibrar SIMILITUD_MINIMA.
    """
    try:
        return await _uc(db).probar_busqueda(
            payload.pregunta, payload.proyecto_codigo, payload.pantalla_codigo, settings.FRAGMENTOS_POR_RESPUESTA,
            payload.similitud_minima if payload.similitud_minima is not None else settings.SIMILITUD_MINIMA,
            settings.BONO_PANTALLA)
    except DatosInvalidos as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/pantallas", dependencies=[Depends(exigir_admin)])
async def listar_pantallas(proyecto_codigo: str = PROYECTO, db: AsyncSession = Depends(get_db)):
    """Las fichas de pantalla en la base (activas primero)."""
    uc = _uc(db)
    return await uc.admin.listar_pantallas(await _proyecto(uc, proyecto_codigo))


@router.post("/pantallas/sincronizar", dependencies=[Depends(exigir_admin)])
async def sincronizar_pantallas(proyecto_codigo: str = PROYECTO, db: AsyncSession = Depends(get_db)):
    """
    Deja la base igual a conocimiento/<proyecto>/pantallas.yaml: crea las nuevas, actualiza las que
    cambiaron y desactiva las que se quitaron del archivo. Si el archivo tiene un error, no cambia nada.
    """
    try:
        return await _uc(db).sincronizar_pantallas(proyecto_codigo)
    except DatosInvalidos as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/modelos", dependencies=[Depends(exigir_admin)])
async def listar_modelos(db: AsyncSession = Depends(get_db)):
    """Los modelos configurados (chat_default es el que usa el chat)."""
    return {"modelos": await PostgresAdminAdapter(db).listar_modelos(),
            "modelo_de_respaldo": settings.MODELO_CHAT_RESPALDO,
            "modelo_embedding": f"{settings.MODELO_EMBEDDING} ({settings.EMBEDDING_DIMENSIONES} dimensiones, en la configuración)"}


class ModeloRequest(BaseModel):
    nombre_modelo: str = Field(..., min_length=1, max_length=100, examples=["gemini-3.1-flash-lite"])
    proveedor: str = Field("google", max_length=50)
    parametros_extra: dict = Field(default_factory=dict)
    probar: bool = Field(True, description="Hacer una pregunta corta antes de guardar (recomendado)")


@router.put("/modelos/{codigo}", dependencies=[Depends(exigir_admin)])
async def cambiar_modelo(codigo: str, payload: ModeloRequest = Body(...), db: AsyncSession = Depends(get_db)):
    """Cambia el modelo de chat sin tocar el código. Con probar=true, si el modelo no responde, no se guarda."""
    try:
        return await _uc(db).cambiar_modelo(codigo, payload.nombre_modelo.strip(), payload.proveedor,
                                            payload.parametros_extra, payload.probar)
    except DatosInvalidos as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/consumo", dependencies=[Depends(exigir_admin)])
async def resumen_consumo(proyecto_codigo: str = PROYECTO,
                          dias: int = Query(30, ge=1, le=366, description="Últimos N días (en hora de Colombia)"),
                          db: AsyncSession = Depends(get_db)):
    """
    Cuánto se gasta en IA: llamadas, tokens y costo en dólares, en total, por día, por operación
    (chat, búsqueda, carga de documentos) y por modelo. Los vectores llevan tokens ESTIMADOS (Gemini
    no los informa). `modelos_sin_precio` lista los modelos a los que falta configurarles el precio.
    """
    uc = _uc(db)
    return await uc.admin.resumen_consumo(await _proyecto(uc, proyecto_codigo), dias, settings.ZONA_HORARIA)
