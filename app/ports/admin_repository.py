from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID


class AdminRepositoryPort(ABC):
    """Lo que necesita la administración del conocimiento (separado del chat)."""

    @abstractmethod
    async def listar_proyectos(self) -> List[dict]: ...

    @abstractmethod
    async def actualizar_proyecto(self, codigo: str, cambios: dict) -> Optional[dict]:
        """Cambia solo los campos enviados. None si el proyecto no existe."""

    @abstractmethod
    async def listar_documentos(self, proyecto_id: UUID) -> List[dict]: ...

    @abstractmethod
    async def fragmentos_de(self, documento_id: UUID) -> Optional[List[dict]]:
        """None si el documento no existe."""

    @abstractmethod
    async def eliminar_documento(self, documento_id: UUID) -> Optional[dict]:
        """El documento eliminado (con su ruta_archivo) o None si no existía."""

    @abstractmethod
    async def listar_pantallas(self, proyecto_id: UUID) -> List[dict]: ...

    @abstractmethod
    async def sincronizar_pantallas(self, proyecto_id: UUID, pantallas: List[dict]) -> dict:
        """Crea, actualiza y desactiva para que la base quede igual al archivo. Devuelve los conteos."""

    @abstractmethod
    async def listar_modelos(self) -> List[dict]: ...

    @abstractmethod
    async def resumen_consumo(self, proyecto_id: UUID, dias: int, zona_horaria: str) -> dict:
        """Totales, por día, por operación y por modelo, de los últimos `dias` días."""

    @abstractmethod
    async def guardar_modelo(self, codigo: str, nombre_modelo: str, proveedor: str, parametros_extra: dict) -> dict: ...
