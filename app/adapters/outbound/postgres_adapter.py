import json
import re
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entities import FragmentoConocimiento, RespuestaModelo
from app.ports.vector_repository import VectorRepositoryPort
from app.utils.logger import logger

CANDIDATOS_POR_FRAGMENTO = 5
RRF_K = 60

def _consulta_texto(texto: str) -> Optional[str]:
    """Palabras de la pregunta unidas con O (|): basta con que el fragmento tenga alguna."""
    palabras = [p for p in re.findall(r"[0-9a-záéíóúüñ]+", texto.lower()) if len(p) >= 3]
    return " | ".join(dict.fromkeys(palabras)) or None

def _vector(v: List[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"

class PostgresVectorAdapter(VectorRepositoryPort):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obtener_proyecto(self, codigo: str) -> Optional[dict]:
        fila = (await self.session.execute(text("""
            SELECT id, minutos_inactividad, personalidad, url_validacion_token, campo_usuario_id, limite_mensajes_dia
            FROM asistente.proyectos WHERE codigo = :codigo AND activo
        """), {"codigo": codigo})).mappings().first()
        return dict(fila) if fila else None

    async def contar_preguntas_hoy(self, proyecto_id: UUID, usuario_id: str, zona_horaria: str) -> int:
        return (await self.session.execute(text("""
            SELECT COUNT(*) FROM asistente.mensajes m
            JOIN asistente.conversaciones c ON c.id = m.conversacion_id
            WHERE c.proyecto_id = :p AND c.usuario_id = :u AND m.rol = 'user'
              AND m.creado_at >= (date_trunc('day', NOW() AT TIME ZONE :z) AT TIME ZONE :z)
        """), {"p": proyecto_id, "u": usuario_id, "z": zona_horaria})).scalar_one()

    async def obtener_pantalla(self, proyecto_id: UUID, codigo: Optional[str]) -> Optional[dict]:
        if not codigo:
            return None
        fila = (await self.session.execute(text("""
            SELECT nombre, descripcion, acciones FROM asistente.pantallas
            WHERE proyecto_id = :p AND codigo = :c AND activo
        """), {"p": proyecto_id, "c": codigo})).mappings().first()
        return dict(fila) if fila else None

    async def obtener_modelo_activo(self, codigo: str = "chat_default") -> Optional[str]:
        fila = (await self.session.execute(text("""
            SELECT nombre_modelo FROM asistente.configuracion_modelo
            WHERE codigo = :codigo AND esta_activo LIMIT 1
        """), {"codigo": codigo})).first()
        return fila.nombre_modelo if fila else None

    async def precios_de(self, nombre_modelo: str) -> Optional[dict]:
        fila = (await self.session.execute(text("""
            SELECT parametros_extra FROM asistente.configuracion_modelo
            WHERE nombre_modelo = :m ORDER BY esta_activo DESC, actualizado_at DESC LIMIT 1
        """), {"m": nombre_modelo})).first()
        return dict(fila.parametros_extra or {}) if fila else None

    async def registrar_consumo(self, proyecto_id: UUID, usuario_id: Optional[str], operacion: str, modelo: str,
                                tokens_entrada: int, tokens_salida: int, tokens_estimados: bool,
                                costo_usd: Optional[float], duracion_ms: Optional[int]) -> None:
        await self.session.execute(text("""
            INSERT INTO asistente.consumo (proyecto_id, usuario_id, operacion, modelo, tokens_entrada, tokens_salida,
                                           tokens_estimados, costo_usd, duracion_ms)
            VALUES (:p, :u, :op, :m, :te, :ts, :est, :costo, :ms)
        """), {"p": proyecto_id, "u": usuario_id, "op": operacion, "m": modelo, "te": tokens_entrada or 0,
               "ts": tokens_salida or 0, "est": tokens_estimados, "costo": costo_usd, "ms": duracion_ms})
        await self.session.commit()

    async def registrar_documento(self, proyecto_id: UUID, titulo: str, tipo: str, pantalla_codigo: Optional[str],
                                  huella: str) -> Tuple[UUID, str]:
        """
        - Misma huella en el proyecto: el archivo ya está cargado → 'sin_cambios'.
        - Mismo título con otra huella: es una nueva versión → se borran sus fragmentos → 'actualizado'.
        - Si no: documento nuevo.
        """
        igual = (await self.session.execute(text("""
            SELECT id FROM asistente.documentos WHERE proyecto_id = :p AND huella = :h
        """), {"p": proyecto_id, "h": huella})).first()
        if igual:
            return igual.id, "sin_cambios"

        anterior = (await self.session.execute(text("""
            SELECT id FROM asistente.documentos WHERE proyecto_id = :p AND titulo = :t
        """), {"p": proyecto_id, "t": titulo})).first()
        if anterior:
            await self.session.execute(text("DELETE FROM asistente.fragmentos WHERE documento_id = :d"), {"d": anterior.id})
            await self.session.execute(text("""
                UPDATE asistente.documentos
                SET huella = :h, tipo = :tipo, pantalla_codigo = :pant, fragmentos = 0, actualizado_at = NOW()
                WHERE id = :d
            """), {"h": huella, "tipo": tipo, "pant": pantalla_codigo, "d": anterior.id})
            return anterior.id, "actualizado"

        nuevo = (await self.session.execute(text("""
            INSERT INTO asistente.documentos (proyecto_id, titulo, tipo, pantalla_codigo, huella)
            VALUES (:p, :t, :tipo, :pant, :h) RETURNING id
        """), {"p": proyecto_id, "t": titulo, "tipo": tipo, "pant": pantalla_codigo, "h": huella})).first()
        return nuevo.id, "nuevo"

    async def guardar_fragmentos(self, documento_id: UUID, proyecto_id: UUID, fragmentos: List[FragmentoConocimiento],
                                 modelo_embedding: str, ruta_archivo: Optional[str]) -> int:
        """Inserta todos los fragmentos y confirma el documento en una sola transacción."""
        if fragmentos:
            await self.session.execute(text("""
                INSERT INTO asistente.fragmentos
                    (documento_id, proyecto_id, pantalla_codigo, orden, contenido, embedding, modelo_embedding, metadata)
                VALUES (:d, :p, :pant, :orden, :contenido, CAST(:v AS vector), :modelo, CAST(:meta AS jsonb))
            """), [
                {"d": documento_id, "p": proyecto_id, "pant": f.pantalla_codigo, "orden": f.orden,
                 "contenido": f.contenido, "v": _vector(f.vector), "modelo": modelo_embedding,
                 "meta": json.dumps(f.metadata or {}, ensure_ascii=False)}
                for f in fragmentos
            ])
        await self.session.execute(text("""
            UPDATE asistente.documentos SET fragmentos = :n, ruta_archivo = :r, actualizado_at = NOW() WHERE id = :d
        """), {"n": len(fragmentos), "r": ruta_archivo, "d": documento_id})
        await self.session.commit()
        return len(fragmentos)

    async def buscar_similares(self, vector_pregunta: List[float], texto_pregunta: str, proyecto_id: UUID,
                               pantalla_codigo: Optional[str], limite: int, similitud_minima: float,
                               bono_pantalla: float) -> List[FragmentoConocimiento]:
        """
        Búsqueda híbrida:
          1. Por significado: los candidatos más cercanos con el índice HNSW (ORDER BY solo por
             distancia: si el orden incluye otra cosa, PostgreSQL deja de usar el índice).
          2. Por palabras exactas: la búsqueda de texto de PostgreSQL ("SIPSA", "tocarreña", "pH").
          3. Se combinan con Reciprocal Rank Fusion: cada fragmento suma 1/(60 + posición) en cada
             lista. Un fragmento sirve si se parece lo suficiente O si tiene las palabras exactas.
          4. Pequeña ventaja para los de la pantalla actual.
        """
        v = _vector(vector_pregunta)
        candidatos = limite * CANDIDATOS_POR_FRAGMENTO
        columnas = """f.id, f.documento_id, f.pantalla_codigo, f.orden, f.contenido, f.metadata, d.titulo,
                      1 - (f.embedding <=> CAST(:v AS vector)) AS similitud"""
        por_vector = (await self.session.execute(text(f"""
            SELECT {columnas}
            FROM asistente.fragmentos f JOIN asistente.documentos d ON d.id = f.documento_id
            WHERE f.proyecto_id = :p
            ORDER BY f.embedding <=> CAST(:v AS vector)
            LIMIT :n
        """), {"v": v, "p": proyecto_id, "n": candidatos})).mappings().all()

        por_texto = []
        consulta = _consulta_texto(texto_pregunta)
        if consulta:
            por_texto = (await self.session.execute(text(f"""
                SELECT {columnas}
                FROM asistente.fragmentos f JOIN asistente.documentos d ON d.id = f.documento_id,
                     to_tsquery('spanish', :q) consulta
                WHERE f.proyecto_id = :p AND f.busqueda @@ consulta
                ORDER BY ts_rank_cd(f.busqueda, consulta) DESC
                LIMIT :n
            """), {"v": v, "q": consulta, "p": proyecto_id, "n": candidatos})).mappings().all()

        fusion: dict = {}
        for origen, lista in (("significado", por_vector), ("palabras", por_texto)):
            for posicion, fila in enumerate(lista):
                f = fusion.setdefault(fila["id"], {"fila": fila, "rrf": 0.0, "origen": set()})
                f["rrf"] += 1 / (RRF_K + posicion + 1)
                f["origen"].add(origen)

        def sirve(f) -> bool:
            return f["fila"]["similitud"] >= similitud_minima or "palabras" in f["origen"]

        def puntaje(f) -> float:
            en_pantalla = pantalla_codigo and f["fila"]["pantalla_codigo"] == pantalla_codigo
            return f["rrf"] + (bono_pantalla / 10 if en_pantalla else 0)   # el RRF es pequeño (≈0,016): el bono se escala

        utiles = sorted((f for f in fusion.values() if sirve(f)), key=puntaje, reverse=True)[:limite]
        logger.info("🔍 %s por significado + %s por palabras → %s útiles", len(por_vector), len(por_texto), len(utiles))
        return [
            FragmentoConocimiento(
                id=f["fila"]["id"], documento_id=f["fila"]["documento_id"], pantalla_codigo=f["fila"]["pantalla_codigo"],
                orden=f["fila"]["orden"], contenido=f["fila"]["contenido"],
                metadata={**(f["fila"]["metadata"] or {}), "titulo_documento": f["fila"]["titulo"],
                          "encontrado_por": sorted(f["origen"])},
                similitud=round(float(f["fila"]["similitud"]), 4),
            )
            for f in utiles
        ]

    async def obtener_o_crear_conversacion(self, proyecto_id: UUID, usuario_id: str, pantalla_codigo: Optional[str],
                                           minutos_inactividad: int) -> UUID:
        """La conversación activa del usuario; si lleva más de `minutos_inactividad` sin mensajes, una nueva."""
        fila = (await self.session.execute(text("""
            SELECT id FROM asistente.conversaciones
            WHERE proyecto_id = :p AND usuario_id = :u
              AND actualizado_at > NOW() - make_interval(mins => :minutos)
            ORDER BY actualizado_at DESC
            LIMIT 1
        """), {"p": proyecto_id, "u": usuario_id, "minutos": minutos_inactividad})).first()
        if fila:
            return fila.id
        nueva = (await self.session.execute(text("""
            INSERT INTO asistente.conversaciones (proyecto_id, usuario_id, pantalla_inicial, titulo)
            VALUES (:p, :u, :pant, :titulo) RETURNING id
        """), {"p": proyecto_id, "u": usuario_id, "pant": pantalla_codigo,
               "titulo": f"Chat desde {pantalla_codigo or 'general'}"})).first()
        await self.session.commit()
        logger.info("🆕 Conversación nueva para el usuario %s", usuario_id)
        return nueva.id

    async def obtener_historial(self, conversacion_id: UUID, limite: int) -> List[dict]:
        filas = (await self.session.execute(text("""
            SELECT rol, contenido FROM (
                SELECT rol, contenido, creado_at FROM asistente.mensajes
                WHERE conversacion_id = :c ORDER BY creado_at DESC LIMIT :n
            ) ultimos ORDER BY creado_at
        """), {"c": conversacion_id, "n": limite})).mappings().all()
        return [dict(f) for f in filas]

    async def guardar_mensaje(self, conversacion_id: UUID, rol: str, contenido: str, pantalla_codigo: Optional[str] = None,
                              fuentes: Optional[list] = None, respuesta: Optional[RespuestaModelo] = None) -> UUID:
        fila = (await self.session.execute(text("""
            INSERT INTO asistente.mensajes
                (conversacion_id, rol, contenido, pantalla_codigo, fuentes_utilizadas,
                 modelo, tokens_entrada, tokens_salida, duracion_ms)
            VALUES (:c, :rol, :contenido, :pant, CAST(:fuentes AS jsonb), :modelo, :te, :ts, :ms)
            RETURNING id
        """), {"c": conversacion_id, "rol": rol, "contenido": contenido, "pant": pantalla_codigo,
               "fuentes": json.dumps(fuentes, ensure_ascii=False, default=str) if fuentes is not None else None,
               "modelo": respuesta.modelo if respuesta else None,
               "te": respuesta.tokens_entrada if respuesta else None,
               "ts": respuesta.tokens_salida if respuesta else None,
               "ms": respuesta.duracion_ms if respuesta else None})).first()
        await self.session.execute(text("UPDATE asistente.conversaciones SET actualizado_at = NOW() WHERE id = :c"),
                                   {"c": conversacion_id})
        await self.session.commit()
        return fila.id

    async def guardar_calificacion(self, mensaje_id: UUID, usuario_id: str, calificacion: int,
                                   comentario: Optional[str] = None) -> bool:
        """
        Solo se puede calificar una respuesta del asistente, en una conversación del mismo usuario.
        Si ya la calificó, se actualiza (una calificación por mensaje).
        """
        fila = (await self.session.execute(text("""
            INSERT INTO asistente.calificaciones (mensaje_id, usuario_id, calificacion, comentario)
            SELECT m.id, CAST(:u AS VARCHAR), CAST(:cal AS INT), CAST(:com AS TEXT)
            FROM asistente.mensajes m
            JOIN asistente.conversaciones c ON c.id = m.conversacion_id
            WHERE m.id = :m AND m.rol = 'assistant' AND c.usuario_id = CAST(:u AS VARCHAR)
            ON CONFLICT (mensaje_id) DO UPDATE
                SET calificacion = EXCLUDED.calificacion, comentario = EXCLUDED.comentario, creado_at = NOW()
            RETURNING id
        """), {"m": mensaje_id, "u": usuario_id, "cal": calificacion, "com": comentario})).first()
        await self.session.commit()
        if fila:
            logger.info("⭐ Calificación %s guardada para el mensaje %s", calificacion, mensaje_id)
        return fila is not None
