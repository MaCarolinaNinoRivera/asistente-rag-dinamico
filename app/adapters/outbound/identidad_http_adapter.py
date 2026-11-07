import hashlib
import time
from typing import Dict, Optional, Tuple

import httpx

from app.config import settings
from app.ports.identidad import IdentidadNoDisponible, IdentidadPort
from app.utils.logger import logger


class IdentidadHttpAdapter(IdentidadPort):
    """
    Verifica el token en el backend de la aplicación (GET url_validacion con el token) y lee el id
    del usuario de la respuesta. El asistente nunca conoce la clave con la que se firman los tokens.

    Una respuesta válida se recuerda SEGUNDOS_CACHE_TOKEN segundos, para no consultar en cada
    mensaje. Se guarda la huella del token, nunca el token.
    """

    def __init__(self):
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._cliente = httpx.AsyncClient(timeout=5.0)

    async def usuario_de(self, token: str, url_validacion: str, campo_usuario_id: str) -> Optional[str]:
        clave = hashlib.sha256(f"{url_validacion}|{token}".encode()).hexdigest()
        guardado = self._cache.get(clave)
        if guardado and guardado[0] > time.monotonic():
            return guardado[1]

        try:
            respuesta = await self._cliente.get(url_validacion, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as error:
            logger.warning("⚠️ No se pudo verificar el token en %s: %s", url_validacion, type(error).__name__)
            raise IdentidadNoDisponible(str(error)) from error

        if respuesta.status_code in (401, 403):
            self._cache.pop(clave, None)
            return None
        if respuesta.status_code != 200:
            logger.warning("⚠️ La verificación del token respondió %s", respuesta.status_code)
            raise IdentidadNoDisponible(f"Respuesta {respuesta.status_code}")

        try:
            usuario = str(respuesta.json()[campo_usuario_id] or "").strip()
        except Exception:
            logger.error("❌ La respuesta de %s no trae el campo '%s'", url_validacion, campo_usuario_id)
            raise IdentidadNoDisponible(f"Sin el campo {campo_usuario_id}")
        if not usuario:
            return None

        if len(self._cache) > 10_000:   # que la caché no crezca sin límite
            ahora = time.monotonic()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > ahora}
        self._cache[clave] = (time.monotonic() + settings.SEGUNDOS_CACHE_TOKEN, usuario)
        return usuario


# Una sola instancia por proceso, para que la caché sirva entre peticiones
identidad = IdentidadHttpAdapter()
