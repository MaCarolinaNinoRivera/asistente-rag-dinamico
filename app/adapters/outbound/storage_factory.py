from app.config import settings
from app.ports.storage_service import StorageServicePort
from app.utils.logger import logger


def get_storage_adapter() -> StorageServicePort:
    if settings.STORAGE_TYPE.lower() == "s3":
        from app.adapters.outbound.s3_adapter import S3CloudAdapter   # boto3 solo si se usa S3
        logger.info("☁️ Almacenamiento: AWS S3 (%s)", settings.AWS_S3_BUCKET)
        return S3CloudAdapter()
    from app.adapters.outbound.storage_local_adapter import FileSystemStorageAdapter
    logger.info("📁 Almacenamiento: carpeta local")
    return FileSystemStorageAdapter()
