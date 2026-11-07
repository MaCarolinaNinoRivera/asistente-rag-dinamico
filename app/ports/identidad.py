from abc import ABC, abstractmethod
from typing import Optional


class IdentidadNoDisponible(Exception):
    """El servicio que verifica los tokens no respondió (caído, sin red…)."""


class IdentidadPort(ABC):

    @abstractmethod
    async def usuario_de(self, token: str, url_validacion: str, campo_usuario_id: str) -> Optional[str]:
        """El id del usuario dueño del token, o None si el token no es válido (vencido, cerrado, falso)."""
