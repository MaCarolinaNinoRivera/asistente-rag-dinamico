from app.ports.vector_repository import VectorRepositoryPort
from app.utils.logger import logger

class DiagnosticoUseCase:
    """
    Caso de uso encargado exclusivamente de verificar la conectividad
    con la base de datos a través del puerto del repositorio.
    """
    def __init__(self, vector_repo: VectorRepositoryPort):
        self.vector_repo = vector_repo

    async def ejecutar(self) -> dict:
        logger.info("🔍 [CORE] Ejecutando caso de uso de diagnóstico de conectividad a la BD...")
        try:
            resultado = await self.vector_repo.probar_conexion()
            logger.info("✅ [CORE] Diagnóstico de base de datos exitoso.")
            return resultado
        except Exception as e:
            logger.error(f"❌ [CORE] Error crítico en DiagnosticoUseCase: {type(e).__name__} - {e}")
            raise e
