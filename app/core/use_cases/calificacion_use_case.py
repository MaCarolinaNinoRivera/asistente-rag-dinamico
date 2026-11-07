from typing import Optional
from uuid import UUID

from app.ports.vector_repository import VectorRepositoryPort


class CalificacionUseCase:
    def __init__(self, vector_repo: VectorRepositoryPort):
        self.vector_repo = vector_repo

    async def registrar_calificacion(self, mensaje_id: UUID, usuario_id: str, calificacion: int,
                                     comentario: Optional[str] = None) -> bool:
        """False si el mensaje no existe, no es del asistente o no es de este usuario."""
        return await self.vector_repo.guardar_calificacion(mensaje_id, usuario_id, calificacion, comentario)
