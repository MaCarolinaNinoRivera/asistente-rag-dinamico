from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class FragmentoConocimiento(BaseModel):
    id: Optional[UUID] = None
    documento_id: Optional[UUID] = None
    pantalla_codigo: Optional[str] = None
    orden: int = 0
    contenido: str
    vector: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    similitud: Optional[float] = None


class ResultadoIngesta(BaseModel):
    documento_id: UUID
    accion: str                 # 'nuevo' · 'actualizado' · 'sin_cambios'
    fragmentos: int
    ruta_archivo: Optional[str] = None


class RespuestaModelo(BaseModel):
    texto: str
    modelo: str
    tokens_entrada: Optional[int] = None
    tokens_salida: Optional[int] = None
    duracion_ms: Optional[int] = None
