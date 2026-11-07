from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from app.core.entities import FragmentoConocimiento, RespuestaModelo

class VectorRepositoryPort(ABC):
    @abstractmethod
    async def obtener_proyecto(self, codigo: str) -> Optional[dict]:
        """{id, minutos_inactividad, personalidad, url_validacion_token, campo_usuario_id,
        limite_mensajes_dia} del proyecto activo, o None."""

    @abstractmethod
    async def contar_preguntas_hoy(self, proyecto_id: UUID, usuario_id: str, zona_horaria: str) -> int:
        """Preguntas que hizo el usuario hoy (en la zona horaria dada)."""

    @abstractmethod
    async def obtener_pantalla(self, proyecto_id: UUID, codigo: Optional[str]) -> Optional[dict]:
        """{nombre, descripcion, acciones} de la pantalla activa, o None."""

    @abstractmethod
    async def obtener_modelo_activo(self, codigo: str = "chat_default") -> Optional[str]:
        pass

    @abstractmethod
    async def precios_de(self, nombre_modelo: str) -> Optional[dict]:
        """Los precios configurados del modelo (parametros_extra), o None."""

    @abstractmethod
    async def registrar_consumo(self, proyecto_id: UUID, usuario_id: Optional[str], operacion: str, modelo: str,
                                tokens_entrada: int, tokens_salida: int, tokens_estimados: bool,
                                costo_usd: Optional[float], duracion_ms: Optional[int]) -> None:
        pass

    @abstractmethod
    async def registrar_documento(self, proyecto_id: UUID, titulo: str, tipo: str, pantalla_codigo: Optional[str],
                                  huella: str) -> Tuple[UUID, str]:
        """(documento_id, 'nuevo' | 'actualizado' | 'sin_cambios'). 'actualizado' borra los fragmentos anteriores."""

    @abstractmethod
    async def guardar_fragmentos(self, documento_id: UUID, proyecto_id: UUID, fragmentos: List[FragmentoConocimiento],
                                 modelo_embedding: str, ruta_archivo: Optional[str]) -> int:
        pass

    @abstractmethod
    async def buscar_similares(self, vector_pregunta: List[float], texto_pregunta: str, proyecto_id: UUID,
                               pantalla_codigo: Optional[str], limite: int, similitud_minima: float,
                               bono_pantalla: float) -> List[FragmentoConocimiento]:
        """Búsqueda híbrida: por significado (vectores) y por palabras exactas, combinadas."""

    @abstractmethod
    async def obtener_o_crear_conversacion(self, proyecto_id: UUID, usuario_id: str, pantalla_codigo: Optional[str],
                                           minutos_inactividad: int) -> UUID:
        pass

    @abstractmethod
    async def obtener_historial(self, conversacion_id: UUID, limite: int) -> List[dict]:
        """Los últimos `limite` mensajes ({rol, contenido}), del más viejo al más nuevo."""

    @abstractmethod
    async def guardar_mensaje(self, conversacion_id: UUID, rol: str, contenido: str, pantalla_codigo: Optional[str] = None,
                              fuentes: Optional[list] = None, respuesta: Optional[RespuestaModelo] = None) -> UUID:
        pass

    @abstractmethod
    async def guardar_calificacion(self, mensaje_id: UUID, usuario_id: str, calificacion: int,
                                   comentario: Optional[str] = None) -> bool:
        """False si el mensaje no existe, no es del asistente o no es de ese usuario."""
