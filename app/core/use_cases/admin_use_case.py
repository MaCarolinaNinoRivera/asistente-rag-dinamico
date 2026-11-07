import re
from pathlib import Path
from typing import List

import yaml

from app.core import prompt
from app.ports.admin_repository import AdminRepositoryPort
from app.ports.llm_service import LLMServicePort
from app.ports.vector_repository import VectorRepositoryPort


class DatosInvalidos(ValueError):
    pass


def leer_pantallas(ruta: Path) -> List[dict]:
    """Lee y valida pantallas.yaml. Si algo está mal, dice qué y dónde, y no se cambia nada."""
    if not ruta.is_file():
        raise DatosInvalidos(f"No existe el archivo {ruta}.")
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise DatosInvalidos(f"El archivo {ruta.name} no es un YAML válido: {error}")
    if not isinstance(datos, list) or not datos:
        raise DatosInvalidos(f"{ruta.name} debe ser una lista de pantallas.")
    pantallas, vistos, errores = [], set(), []
    for i, p in enumerate(datos, start=1):
        if not isinstance(p, dict):
            errores.append(f"elemento {i}: no es una pantalla")
            continue
        codigo = str(p.get("codigo") or "").strip()
        donde = f"pantalla {i} ({codigo or 'sin código'})"
        if not re.fullmatch(r"[a-z0-9_-]{1,100}", codigo):
            errores.append(f"{donde}: el código debe ser en minúsculas, sin espacios")
        elif codigo in vistos:
            errores.append(f"{donde}: el código está repetido")
        vistos.add(codigo)
        nombre, descripcion = str(p.get("nombre") or "").strip(), str(p.get("descripcion") or "").strip()
        if not nombre:
            errores.append(f"{donde}: falta el nombre")
        if not descripcion:
            errores.append(f"{donde}: falta la descripción")
        acciones = p.get("acciones") or []
        if not isinstance(acciones, list) or not all(isinstance(a, str) and a.strip() for a in acciones):
            errores.append(f"{donde}: las acciones deben ser una lista de textos")
            acciones = []
        pantallas.append({"codigo": codigo, "nombre": nombre, "descripcion": descripcion,
                          "acciones": [a.strip() for a in acciones]})
    if errores:
        raise DatosInvalidos("No se sincronizó nada. Corrige el archivo: " + "; ".join(errores))
    return pantallas


class AdminUseCase:
    def __init__(self, admin_repo: AdminRepositoryPort, vector_repo: VectorRepositoryPort, llm: LLMServicePort,
                 carpeta_conocimiento: Path):
        self.admin = admin_repo
        self.vector = vector_repo
        self.llm = llm
        self.carpeta = carpeta_conocimiento

    async def proyecto_id(self, codigo: str):
        proyecto = await self.vector.obtener_proyecto(codigo)
        if not proyecto:
            raise DatosInvalidos(f"No existe el proyecto '{codigo}'.")
        return proyecto["id"]

    async def sincronizar_pantallas(self, proyecto_codigo: str) -> dict:
        pantallas = leer_pantallas(self.carpeta / proyecto_codigo / "pantallas.yaml")
        resultado = await self.admin.sincronizar_pantallas(await self.proyecto_id(proyecto_codigo), pantallas)
        return {"archivo": f"conocimiento/{proyecto_codigo}/pantallas.yaml", **resultado}

    async def probar_busqueda(self, pregunta: str, proyecto_codigo: str, pantalla_codigo, limite: int,
                              similitud_minima: float, bono_pantalla: float) -> dict:
        """Lo que encontraría el chat para esta pregunta, sin llamar al modelo de respuesta."""
        proyecto = await self.vector.obtener_proyecto(proyecto_codigo)
        if not proyecto:
            raise DatosInvalidos(f"No existe el proyecto '{proyecto_codigo}'.")
        vector = (await self.llm.generar_embeddings([pregunta], para_documento=False))[0]
        fragmentos = await self.vector.buscar_similares(vector, pregunta, proyecto["id"], pantalla_codigo,
                                                        limite, similitud_minima, bono_pantalla)
        pantalla = await self.vector.obtener_pantalla(proyecto["id"], pantalla_codigo)
        return {
            "pantalla": pantalla["nombre"] if pantalla else None,
            "fragmentos": [{"documento": (f.metadata or {}).get("titulo_documento"), "similitud": f.similitud,
                            "encontrado_por": (f.metadata or {}).get("encontrado_por"),
                            "pantalla_codigo": f.pantalla_codigo, "contenido": f.contenido} for f in fragmentos],
            "mensaje_que_recibiria_el_modelo": prompt.armar_mensaje(pregunta, pantalla, fragmentos, []),
        }

    async def cambiar_modelo(self, codigo: str, nombre_modelo: str, proveedor: str, parametros_extra: dict,
                             probar: bool) -> dict:
        """Con probar=True, se hace una pregunta corta al modelo antes de guardarlo: así nunca queda
        activo un modelo que no existe o no responde."""
        if probar:
            try:
                r = await self.llm.generar_respuesta("Responde solo con la palabra: listo", "Prueba de conexión.", nombre_modelo)
            except Exception as error:
                raise DatosInvalidos(f"El modelo '{nombre_modelo}' no respondió y NO se guardó: {error}")
            if not r.texto:
                raise DatosInvalidos(f"El modelo '{nombre_modelo}' respondió vacío y NO se guardó.")
        return await self.admin.guardar_modelo(codigo, nombre_modelo, proveedor, parametros_extra)
