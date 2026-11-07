import asyncio
import os
import re
import shutil

from app.ports.storage_service import StorageServicePort


def nombre_seguro(nombre: str) -> str:
    """Solo el nombre del archivo, sin carpetas ni caracteres raros: evita escribir fuera de la carpeta."""
    base = os.path.basename(nombre or "").strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:150] or "archivo"


class FileSystemStorageAdapter(StorageServicePort):
    def __init__(self, directorio_base: str = "./storage_local"):
        self.directorio_base = os.path.abspath(directorio_base)
        os.makedirs(self.directorio_base, exist_ok=True)

    def _ruta(self, nombre_remoto: str) -> str:
        return os.path.join(self.directorio_base, nombre_seguro(nombre_remoto))

    async def subir_archivo(self, ruta_local: str, nombre_remoto: str) -> str:
        destino = self._ruta(nombre_remoto)
        await asyncio.to_thread(shutil.copyfile, ruta_local, destino)
        return destino

    async def descargar_archivo(self, nombre_remoto: str, ruta_destino_local: str) -> bool:
        origen = self._ruta(nombre_remoto)
        if not os.path.exists(origen):
            return False
        await asyncio.to_thread(shutil.copyfile, origen, ruta_destino_local)
        return True
