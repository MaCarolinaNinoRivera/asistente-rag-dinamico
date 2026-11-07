from typing import Optional

from app.config import settings
from app.core import prompt
from app.core.consumo import calcular_costo, estimar_tokens
from app.ports.llm_service import LLMServicePort
from app.ports.vector_repository import VectorRepositoryPort
from app.utils.logger import logger

class ProyectoNoEncontrado(Exception):
    pass

class LimiteAlcanzado(Exception):
    def __init__(self, limite: int):
        super().__init__(limite)
        self.limite = limite

class ChatUseCase:
    def __init__(self, vector_repo: VectorRepositoryPort, llm_service: LLMServicePort):
        self.vector_repo = vector_repo
        self.llm_service = llm_service

    async def responder_pregunta(self, pregunta: str, pantalla_codigo: Optional[str], usuario_id: str,
                                 proyecto_codigo: str) -> dict:
        proyecto = await self.vector_repo.obtener_proyecto(proyecto_codigo)
        if not proyecto:
            raise ProyectoNoEncontrado(proyecto_codigo)
        logger.info("💬 Pregunta en '%s' · pantalla '%s'", proyecto_codigo, pantalla_codigo or "general")

        limite = proyecto.get("limite_mensajes_dia") or 0
        if limite and await self.vector_repo.contar_preguntas_hoy(proyecto["id"], usuario_id, settings.ZONA_HORARIA) >= limite:
            raise LimiteAlcanzado(limite)

        conversacion_id = await self.vector_repo.obtener_o_crear_conversacion(
            proyecto["id"], usuario_id, pantalla_codigo, proyecto["minutos_inactividad"])
        historial = await self.vector_repo.obtener_historial(conversacion_id, prompt.MENSAJES_DE_HISTORIAL)
        pantalla = await self.vector_repo.obtener_pantalla(proyecto["id"], pantalla_codigo)

        vector = (await self.llm_service.generar_embeddings([pregunta], para_documento=False))[0]
        fragmentos = await self.vector_repo.buscar_similares(
            vector, pregunta, proyecto["id"], pantalla_codigo,
            limite=settings.FRAGMENTOS_POR_RESPUESTA,
            similitud_minima=settings.SIMILITUD_MINIMA,
            bono_pantalla=settings.BONO_PANTALLA,
        )

        respuesta = await self.llm_service.generar_respuesta(
            instrucciones=prompt.instrucciones(proyecto.get("personalidad")),
            mensaje=prompt.armar_mensaje(pregunta, pantalla, fragmentos, historial),
            nombre_modelo=await self.vector_repo.obtener_modelo_activo("chat_default"),
        )

        await self.vector_repo.guardar_mensaje(conversacion_id, "user", pregunta, pantalla_codigo)
        fuentes = [{"fragmento_id": str(f.id), "documento": (f.metadata or {}).get("titulo_documento"),
                    "similitud": f.similitud, "encontrado_por": (f.metadata or {}).get("encontrado_por")}
                   for f in fragmentos]
        mensaje_id = await self.vector_repo.guardar_mensaje(conversacion_id, "assistant", respuesta.texto,
                                                            pantalla_codigo, fuentes, respuesta)

        await self._registrar(proyecto["id"], usuario_id, "busqueda", settings.MODELO_EMBEDDING,
                              estimar_tokens([pregunta]), 0, True, None)
        await self._registrar(proyecto["id"], usuario_id, "chat", respuesta.modelo,
                              respuesta.tokens_entrada or 0, respuesta.tokens_salida or 0, False, respuesta.duracion_ms)
        return {"respuesta": respuesta.texto, "mensaje_id": str(mensaje_id), "conversacion_id": str(conversacion_id)}

    async def _registrar(self, proyecto_id, usuario_id, operacion, modelo, entrada, salida, estimados, duracion_ms):
        """Si el registro del consumo falla, la respuesta al usuario NO se pierde: solo queda un aviso."""
        try:
            costo = calcular_costo(entrada, salida, await self.vector_repo.precios_de(modelo))
            await self.vector_repo.registrar_consumo(proyecto_id, usuario_id, operacion, modelo, entrada, salida,
                                                     estimados, costo, duracion_ms)
        except Exception as error:
            logger.warning("⚠️ No se pudo registrar el consumo (%s): %s", operacion, error)
