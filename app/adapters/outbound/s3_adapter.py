import asyncio

import boto3

from app.adapters.outbound.storage_local_adapter import nombre_seguro
from app.config import settings
from app.ports.storage_service import StorageServicePort


class S3CloudAdapter(StorageServicePort):
    """
    Desplegado en AWS, el permiso lo da el ROL DE IAM del contenedor: no se configuran claves.
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY solo se usan si están definidas (pruebas fuera de AWS).
    boto3 no es asíncrono: cada operación corre en un hilo aparte para no frenar al servidor.
    """

    def __init__(self):
        kwargs = {"region_name": settings.AWS_S3_REGION}
        if settings.AWS_S3_ENDPOINT:
            kwargs["endpoint_url"] = settings.AWS_S3_ENDPOINT
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
        self.s3_client = boto3.client("s3", **kwargs)
        self.bucket_name = settings.AWS_S3_BUCKET
        self.prefijo = settings.AWS_S3_PREFIJO

    def _clave(self, nombre_remoto: str) -> str:
        return f"{self.prefijo}{nombre_seguro(nombre_remoto)}"

    async def subir_archivo(self, ruta_local: str, nombre_remoto: str) -> str:
        clave = self._clave(nombre_remoto)
        await asyncio.to_thread(self.s3_client.upload_file, ruta_local, self.bucket_name, clave)
        return f"s3://{self.bucket_name}/{clave}"

    async def descargar_archivo(self, nombre_remoto: str, ruta_destino_local: str) -> bool:
        await asyncio.to_thread(self.s3_client.download_file, self.bucket_name, self._clave(nombre_remoto), ruta_destino_local)
        return True
