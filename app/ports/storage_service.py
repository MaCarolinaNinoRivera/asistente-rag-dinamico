from abc import ABC, abstractmethod


class StorageServicePort(ABC):

    @abstractmethod
    async def subir_archivo(self, ruta_local: str, nombre_remoto: str) -> str:
        """Guarda el original y devuelve su ubicación (s3://… o ruta local)."""

    @abstractmethod
    async def descargar_archivo(self, nombre_remoto: str, ruta_destino_local: str) -> bool:
        pass
