from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.entities import RespuestaModelo


class LLMServicePort(ABC):

    @abstractmethod
    async def generar_embeddings(self, textos: List[str], para_documento: bool) -> List[List[float]]:
        """Un vector por texto. para_documento=True al cargar fragmentos; False para la pregunta."""

    @abstractmethod
    async def generar_respuesta(self, instrucciones: str, mensaje: str,
                                nombre_modelo: Optional[str] = None) -> RespuestaModelo:
        """Llama al modelo con sus instrucciones (personalidad y reglas) y el mensaje ya armado."""
