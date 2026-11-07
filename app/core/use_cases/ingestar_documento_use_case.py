import asyncio
import hashlib
import os
import re
from typing import List, Optional

from pypdf import PdfReader

from app.config import settings
from app.core.consumo import calcular_costo, estimar_tokens
from app.core.entities import FragmentoConocimiento, ResultadoIngesta
from app.ports.llm_service import LLMServicePort
from app.ports.storage_service import StorageServicePort
from app.ports.vector_repository import VectorRepositoryPort
from app.utils.logger import logger

EXTENSIONES = {".pdf", ".txt", ".md"}
TIPOS = {"manual", "glosario", "pantalla", "faq", "guia"}

def huella_archivo(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()

def extraer_texto(ruta: str) -> str:
    extension = os.path.splitext(ruta)[1].lower()
    if extension == ".pdf":
        paginas = [p.extract_text() or "" for p in PdfReader(ruta).pages]
        return "\n\n".join(p.strip() for p in paginas if p.strip())
    if extension in (".txt", ".md"):
        with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise ValueError(f"Formato no soportado: {extension}. Usa PDF, TXT o MD.")

def fragmentar(texto: str, tamano: int, solape: int) -> List[str]:
    """
    Fragmentos de ~`tamano` caracteres que respetan los párrafos; un párrafo enorme se parte por
    oraciones. Cada fragmento repite el final del anterior (`solape`) para no cortar una idea a la mitad.
    """
    texto = re.sub(r"[ \t]+", " ", texto.replace("\r", ""))
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    piezas: List[str] = []
    for p in parrafos:
        if len(p) <= tamano:
            piezas.append(p)
        else:
            piezas.extend(o.strip() for o in re.split(r"(?<=[.!?])\s+", p) if o.strip())

    fragmentos, actual = [], ""
    for pieza in piezas:
        while len(pieza) > tamano:
            fragmentos.append(((actual + "\n") if actual else "") + pieza[:tamano])
            actual, pieza = "", pieza[tamano - solape:]
        if actual and len(actual) + len(pieza) + 1 > tamano:
            fragmentos.append(actual)
            actual = actual[-solape:].split(" ", 1)[-1] if solape else ""
        actual = f"{actual}\n{pieza}" if actual else pieza
    if actual.strip():
        fragmentos.append(actual)
    return [f.strip() for f in fragmentos if len(f.strip()) >= 30]

def fragmentar_markdown(texto: str, tamano: int, solape: int) -> List[str]:
    """
    Markdown: cada título (#, ##, ###) con su texto es un fragmento propio. Así, en un glosario,
    "SIPSA" y "Merma" no quedan mezclados. Si una sección es muy larga, se parte, y cada parte
    repite el título para no perder de qué habla.
    """
    secciones, actual = [], []
    for linea in texto.replace("\r", "").split("\n"):
        if re.match(r"^#{1,6}\s+\S", linea) and any(l.strip() for l in actual):
            secciones.append("\n".join(actual).strip())
            actual = []
        actual.append(linea)
    if any(l.strip() for l in actual):
        secciones.append("\n".join(actual).strip())

    fragmentos = []
    for seccion in secciones:
        titulo = seccion.split("\n", 1)[0] if seccion.startswith("#") else ""
        if len(seccion) <= tamano:
            fragmentos.append(seccion)
            continue
        cuerpo = seccion.split("\n", 1)[1] if titulo and "\n" in seccion else seccion
        for parte in fragmentar(cuerpo, tamano - len(titulo) - 1, solape):
            fragmentos.append(f"{titulo}\n{parte}" if titulo else parte)
    return [f for f in fragmentos if len(re.sub(r"^#+\s*", "", f).strip()) >= 30]

class IngestarDocumentoUseCase:
    def __init__(self, storage_repo: StorageServicePort, vector_repo: VectorRepositoryPort, llm_service: LLMServicePort):
        self.storage_repo = storage_repo
        self.vector_repo = vector_repo
        self.llm_service = llm_service

    async def ejecutar(self, ruta_archivo_local: str, titulo_documento: str, pantalla_codigo: Optional[str],
                       proyecto_codigo: str, tipo: str = "manual") -> ResultadoIngesta:
        if tipo not in TIPOS:
            raise ValueError(f"Tipo de documento no válido: {tipo}. Usa uno de: {', '.join(sorted(TIPOS))}.")
        proyecto = await self.vector_repo.obtener_proyecto(proyecto_codigo)
        if not proyecto:
            raise ValueError(f"No existe el proyecto '{proyecto_codigo}'.")

        huella = await asyncio.to_thread(huella_archivo, ruta_archivo_local)
        documento_id, accion = await self.vector_repo.registrar_documento(
            proyecto["id"], titulo_documento, tipo, pantalla_codigo, huella)
        if accion == "sin_cambios":
            logger.info("⏭️ '%s' ya estaba cargado y no cambió", titulo_documento)
            return ResultadoIngesta(documento_id=documento_id, accion=accion, fragmentos=0)

        texto = await asyncio.to_thread(extraer_texto, ruta_archivo_local)
        partir = fragmentar_markdown if ruta_archivo_local.lower().endswith(".md") else fragmentar
        bloques = partir(texto, settings.TAMANO_FRAGMENTO, settings.SOLAPE_FRAGMENTO)
        if not bloques:
            raise ValueError("El documento no tiene texto que se pueda leer (¿es un PDF escaneado como imagen?).")

        vectores = await self.llm_service.generar_embeddings(bloques, para_documento=True)
        ruta = await self.storage_repo.subir_archivo(ruta_archivo_local, f"{documento_id}_{titulo_documento}")
        fragmentos = [
            FragmentoConocimiento(pantalla_codigo=pantalla_codigo, orden=i, contenido=b, vector=v,
                                  metadata={"titulo_documento": titulo_documento, "tipo": tipo})
            for i, (b, v) in enumerate(zip(bloques, vectores))
        ]
        n = await self.vector_repo.guardar_fragmentos(documento_id, proyecto["id"], fragmentos,
                                                      settings.MODELO_EMBEDDING, ruta)
        logger.info("✅ '%s' %s: %s fragmentos", titulo_documento, accion, n)
        try:
            tokens = estimar_tokens(bloques)
            costo = calcular_costo(tokens, 0, await self.vector_repo.precios_de(settings.MODELO_EMBEDDING))
            await self.vector_repo.registrar_consumo(proyecto["id"], None, "ingesta", settings.MODELO_EMBEDDING,
                                                     tokens, 0, True, costo, None)
        except Exception as error:
            logger.warning("⚠️ No se pudo registrar el consumo de la carga: %s", error)
        return ResultadoIngesta(documento_id=documento_id, accion=accion, fragmentos=n, ruta_archivo=ruta)
