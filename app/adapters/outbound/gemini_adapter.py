import math
import time
from typing import List, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.core.entities import RespuestaModelo
from app.ports.llm_service import LLMServicePort
from app.utils.logger import logger

LOTE_EMBEDDINGS = 50   # textos por llamada al calcular vectores

def _normalizar(vector: List[float]) -> List[float]:
    """Con menos de 3.072 dimensiones, Google recomienda normalizar el vector (largo 1)."""
    largo = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / largo for x in vector]


class GeminiAdapter(LLMServicePort):
    """
    Todas las llamadas son asíncronas (client.aio): mientras Gemini responde a un usuario,
    el servidor sigue atendiendo a los demás.
    """

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.modelo_embedding = settings.MODELO_EMBEDDING
        self.dimensiones = settings.EMBEDDING_DIMENSIONES

    async def generar_embeddings(self, textos: List[str], para_documento: bool) -> List[List[float]]:
        """
        Un vector por texto, en lotes. El tipo de tarea mejora la búsqueda: los fragmentos se
        calculan como DOCUMENTO y la pregunta como CONSULTA.
        """
        tarea = "RETRIEVAL_DOCUMENT" if para_documento else "RETRIEVAL_QUERY"
        vectores: List[List[float]] = []
        for inicio in range(0, len(textos), LOTE_EMBEDDINGS):
            lote = textos[inicio:inicio + LOTE_EMBEDDINGS]
            try:
                respuesta = await self.client.aio.models.embed_content(
                    model=self.modelo_embedding,
                    contents=lote,
                    config=types.EmbedContentConfig(output_dimensionality=self.dimensiones, task_type=tarea),
                )
            except Exception as error:
                logger.error("❌ Error calculando vectores con %s: %s", self.modelo_embedding, error)
                raise
            vectores.extend(_normalizar(e.values) for e in respuesta.embeddings)
        logger.info("🧠 %s vector(es) de %s dimensiones (%s)", len(vectores), self.dimensiones, tarea)
        return vectores

    async def generar_respuesta(self, instrucciones: str, mensaje: str,
                                nombre_modelo: Optional[str] = None) -> RespuestaModelo:
        """Solo llama al modelo: el prompt lo arma el núcleo (app/core/prompt.py)."""
        modelo = nombre_modelo or settings.MODELO_CHAT_RESPALDO
        inicio = time.perf_counter()
        try:
            respuesta = await self.client.aio.models.generate_content(
                model=modelo,
                contents=mensaje,
                config=types.GenerateContentConfig(system_instruction=instrucciones),
            )
        except Exception as error:
            logger.error("❌ Error generando la respuesta con %s: %s", modelo, error)
            raise
        uso = getattr(respuesta, "usage_metadata", None)
        resultado = RespuestaModelo(
            texto=(respuesta.text or "").strip(),
            modelo=modelo,
            tokens_entrada=getattr(uso, "prompt_token_count", None),
            tokens_salida=getattr(uso, "candidates_token_count", None),
            duracion_ms=int((time.perf_counter() - inicio) * 1000),
        )
        # El texto completo solo en DEBUG: son conversaciones privadas
        logger.debug("Respuesta de Gemini: %s", resultado.texto)
        logger.info("✅ Respuesta de %s en %s ms (%s → %s tokens)", modelo, resultado.duracion_ms,
                    resultado.tokens_entrada, resultado.tokens_salida)
        return resultado
