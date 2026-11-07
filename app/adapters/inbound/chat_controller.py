from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.inbound.autenticacion import usuario_que_pregunta
from app.adapters.outbound.database import get_db
from app.adapters.outbound.gemini_adapter import GeminiAdapter
from app.adapters.outbound.postgres_adapter import PostgresVectorAdapter
from app.config import settings
from app.core.use_cases.calificacion_use_case import CalificacionUseCase
from app.core.use_cases.chat_use_case import ChatUseCase, LimiteAlcanzado, ProyectoNoEncontrado
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/chat", tags=["Chat Asistente"])
AUTORIZACION = Header(None, alias="Authorization", description="Bearer <token de la aplicación>")


class PreguntaRequest(BaseModel):
    pregunta: str = Field(..., min_length=1, max_length=2000)
    pantalla_codigo: Optional[str] = Field(None, max_length=100)
    proyecto_codigo: str = Field(settings.PROYECTO_POR_DEFECTO, max_length=50)
    # Solo en desarrollo (AUTENTICACION_REQUERIDA=false); con token se ignora
    usuario_id: Optional[str] = Field(None, max_length=100)


class RespuestaResponse(BaseModel):
    respuesta: str
    mensaje_id: Optional[str] = None
    conversacion_id: Optional[str] = None


class CalificacionRequest(BaseModel):
    mensaje_id: UUID
    calificacion: int = Field(..., ge=1, le=5)
    comentario: Optional[str] = Field(None, max_length=1000)
    proyecto_codigo: str = Field(settings.PROYECTO_POR_DEFECTO, max_length=50)
    usuario_id: Optional[str] = Field(None, max_length=100)   # solo en desarrollo


class CalificacionResponse(BaseModel):
    status: str
    mensaje: str


async def _proyecto(repo: PostgresVectorAdapter, codigo: str) -> dict:
    proyecto = await repo.obtener_proyecto(codigo)
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"No existe el proyecto '{codigo}'.")
    return proyecto


@router.post("", response_model=RespuestaResponse)
async def procesar_pregunta(payload: PreguntaRequest, authorization: Optional[str] = AUTORIZACION,
                            db: AsyncSession = Depends(get_db)):
    repo = PostgresVectorAdapter(db)
    proyecto = await _proyecto(repo, payload.proyecto_codigo)
    usuario_id = await usuario_que_pregunta(proyecto, authorization, payload.usuario_id)
    try:
        resultado = await ChatUseCase(repo, GeminiAdapter()).responder_pregunta(
            pregunta=payload.pregunta.strip(), pantalla_codigo=payload.pantalla_codigo,
            usuario_id=usuario_id, proyecto_codigo=payload.proyecto_codigo,
        )
    except ProyectoNoEncontrado:
        raise HTTPException(status_code=404, detail=f"No existe el proyecto '{payload.proyecto_codigo}'.")
    except LimiteAlcanzado as limite:
        raise HTTPException(status_code=429, detail=f"Por hoy ya hiciste {limite.limite} preguntas, que es el máximo. "
                                                    "Mañana puedes seguir preguntándome.")
    except Exception:
        logger.exception("❌ No se pudo responder la pregunta")
        raise HTTPException(status_code=503, detail="No pude responder en este momento. Intenta de nuevo en un minuto.")
    return RespuestaResponse(**resultado)


@router.post("/calificar", response_model=CalificacionResponse)
async def calificar_respuesta(payload: CalificacionRequest, authorization: Optional[str] = AUTORIZACION,
                              db: AsyncSession = Depends(get_db)):
    repo = PostgresVectorAdapter(db)
    usuario_id = await usuario_que_pregunta(await _proyecto(repo, payload.proyecto_codigo), authorization, payload.usuario_id)
    guardada = await CalificacionUseCase(repo).registrar_calificacion(
        payload.mensaje_id, usuario_id, payload.calificacion, payload.comentario)
    if not guardada:
        raise HTTPException(status_code=404, detail="No encontramos esa respuesta para calificarla.")
    return CalificacionResponse(status="ok", mensaje="¡Muchas gracias por calificar la respuesta! Tu opinión nos ayuda a mejorar.")
