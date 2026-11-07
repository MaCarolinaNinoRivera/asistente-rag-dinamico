"""
Quién pregunta. El widget envía el token de la aplicación ("Authorization: Bearer …") y el
asistente lo verifica en el backend de esa aplicación (proyectos.url_validacion_token).

Sin token, solo en desarrollo (AUTENTICACION_REQUERIDA=false): se acepta el usuario_id del cuerpo.
"""

from typing import Optional

from fastapi import HTTPException

from app.adapters.outbound.identidad_http_adapter import identidad
from app.config import settings
from app.ports.identidad import IdentidadNoDisponible
from app.utils.logger import logger


def token_de(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


async def usuario_que_pregunta(proyecto: dict, authorization: Optional[str], usuario_del_cuerpo: Optional[str]) -> str:
    token = token_de(authorization)
    if token:
        url = proyecto.get("url_validacion_token")
        if not url:
            logger.error("❌ El proyecto no tiene url_validacion_token: no se puede verificar quién pregunta")
            raise HTTPException(status_code=503, detail="El asistente no está configurado para este proyecto.")
        try:
            usuario = await identidad.usuario_de(token, url, proyecto.get("campo_usuario_id") or "id")
        except IdentidadNoDisponible:
            raise HTTPException(status_code=503, detail="No pude verificar tu sesión. Intenta de nuevo en un momento.")
        if not usuario:
            raise HTTPException(status_code=401, detail="Tu sesión se cerró. Vuelve a iniciar sesión.")
        return usuario

    if settings.AUTENTICACION_REQUERIDA:
        raise HTTPException(status_code=401, detail="Inicia sesión para hablar con el asistente.")
    if usuario_del_cuerpo:
        return usuario_del_cuerpo   # solo desarrollo
    raise HTTPException(status_code=400, detail="Falta el usuario (en desarrollo, envía usuario_id).")
