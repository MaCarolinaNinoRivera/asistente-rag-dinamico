import json
from typing import List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ports.admin_repository import AdminRepositoryPort

class PostgresAdminAdapter(AdminRepositoryPort):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _filas(self, sql: str, **params) -> List[dict]:
        return [dict(f) for f in (await self.session.execute(text(sql), params)).mappings().all()]

    async def listar_proyectos(self) -> List[dict]:
        return await self._filas("""
            SELECT p.codigo, p.nombre, p.descripcion, p.activo, p.minutos_inactividad, p.limite_mensajes_dia,
                   p.url_validacion_token,
                   p.personalidad IS NOT NULL AS personalidad_propia,
                   (SELECT COUNT(*) FROM asistente.documentos d WHERE d.proyecto_id = p.id) AS documentos,
                   (SELECT COUNT(*) FROM asistente.pantallas s WHERE s.proyecto_id = p.id AND s.activo) AS pantallas
            FROM asistente.proyectos p ORDER BY p.codigo
        """)

    CAMPOS_PROYECTO = ("nombre", "descripcion", "personalidad", "minutos_inactividad", "limite_mensajes_dia",
                       "url_validacion_token", "campo_usuario_id", "activo")

    async def actualizar_proyecto(self, codigo: str, cambios: dict) -> Optional[dict]:
        campos = {k: v for k, v in cambios.items() if k in self.CAMPOS_PROYECTO}
        if campos:
            asignaciones = ", ".join(f"{k} = :{k}" for k in campos)
            await self.session.execute(text(f"UPDATE asistente.proyectos SET {asignaciones} WHERE codigo = :codigo"),
                                       {**campos, "codigo": codigo})
            await self.session.commit()
        fila = (await self.session.execute(text("""
            SELECT codigo, nombre, descripcion, personalidad, minutos_inactividad, limite_mensajes_dia,
                   url_validacion_token, campo_usuario_id, activo
            FROM asistente.proyectos WHERE codigo = :codigo
        """), {"codigo": codigo})).mappings().first()
        return dict(fila) if fila else None

    async def listar_documentos(self, proyecto_id: UUID) -> List[dict]:
        return await self._filas("""
            SELECT id, titulo, tipo, pantalla_codigo, fragmentos, ruta_archivo, creado_at, actualizado_at
            FROM asistente.documentos WHERE proyecto_id = :p ORDER BY actualizado_at DESC
        """, p=proyecto_id)

    async def fragmentos_de(self, documento_id: UUID) -> Optional[List[dict]]:
        existe = (await self.session.execute(text("SELECT 1 FROM asistente.documentos WHERE id = :d"),
                                             {"d": documento_id})).first()
        if not existe:
            return None
        return await self._filas("""
            SELECT orden, pantalla_codigo, LENGTH(contenido) AS caracteres, contenido, modelo_embedding
            FROM asistente.fragmentos WHERE documento_id = :d ORDER BY orden
        """, d=documento_id)

    async def eliminar_documento(self, documento_id: UUID) -> Optional[dict]:
        fila = (await self.session.execute(text("""
            DELETE FROM asistente.documentos WHERE id = :d RETURNING titulo, fragmentos, ruta_archivo
        """), {"d": documento_id})).mappings().first()
        await self.session.commit()
        return dict(fila) if fila else None

    async def listar_pantallas(self, proyecto_id: UUID) -> List[dict]:
        return await self._filas("""
            SELECT codigo, nombre, descripcion, acciones, activo, actualizado_at
            FROM asistente.pantallas WHERE proyecto_id = :p ORDER BY activo DESC, codigo
        """, p=proyecto_id)

    async def sincronizar_pantallas(self, proyecto_id: UUID, pantallas: List[dict]) -> dict:
        """Todo en una transacción: o queda igual al archivo, o no cambia nada."""
        actuales = {f["codigo"]: f for f in await self._filas("""
            SELECT codigo, nombre, descripcion, acciones, activo FROM asistente.pantallas WHERE proyecto_id = :p
        """, p=proyecto_id)}
        conteo = {"creadas": 0, "actualizadas": 0, "sin_cambios": 0, "desactivadas": 0}
        for p in pantallas:
            anterior = actuales.get(p["codigo"])
            igual = anterior and anterior["activo"] and all(anterior[k] == p[k] for k in ("nombre", "descripcion", "acciones"))
            if igual:
                conteo["sin_cambios"] += 1
                continue
            await self.session.execute(text("""
                INSERT INTO asistente.pantallas (proyecto_id, codigo, nombre, descripcion, acciones, activo)
                VALUES (:pr, :c, :n, :d, :a, TRUE)
                ON CONFLICT (proyecto_id, codigo) DO UPDATE
                SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion, acciones = EXCLUDED.acciones,
                    activo = TRUE, actualizado_at = NOW()
            """), {"pr": proyecto_id, "c": p["codigo"], "n": p["nombre"], "d": p["descripcion"], "a": p["acciones"]})
            conteo["actualizadas" if anterior else "creadas"] += 1
        quitadas = [c for c, f in actuales.items() if f["activo"] and c not in {p["codigo"] for p in pantallas}]
        if quitadas:
            await self.session.execute(text("""
                UPDATE asistente.pantallas SET activo = FALSE, actualizado_at = NOW()
                WHERE proyecto_id = :p AND codigo = ANY(:c)
            """), {"p": proyecto_id, "c": quitadas})
        conteo["desactivadas"] = len(quitadas)
        conteo["codigos_desactivados"] = quitadas
        await self.session.commit()
        return conteo

    async def resumen_consumo(self, proyecto_id: UUID, dias: int, zona_horaria: str) -> dict:
        base = """FROM asistente.consumo
                  WHERE proyecto_id = :p AND creado_at >= (date_trunc('day', NOW() AT TIME ZONE :z) AT TIME ZONE :z)
                                                          - make_interval(days => :d - 1)"""
        columnas = """COUNT(*) AS llamadas, COALESCE(SUM(tokens_entrada), 0) AS tokens_entrada,
                      COALESCE(SUM(tokens_salida), 0) AS tokens_salida, ROUND(COALESCE(SUM(costo_usd), 0), 6) AS costo_usd,
                      COUNT(*) FILTER (WHERE costo_usd IS NULL) AS sin_precio"""
        params = {"p": proyecto_id, "z": zona_horaria, "d": dias}
        total = (await self._filas(f"SELECT {columnas}, COUNT(DISTINCT usuario_id) AS usuarios {base}", **params))[0]
        por_dia = await self._filas(f"""SELECT (creado_at AT TIME ZONE :z)::date AS fecha, {columnas} {base}
                                        GROUP BY 1 ORDER BY 1""", **params)
        por_operacion = await self._filas(f"SELECT operacion, {columnas} {base} GROUP BY 1 ORDER BY costo_usd DESC, llamadas DESC", **params)
        por_modelo = await self._filas(f"SELECT modelo, {columnas} {base} GROUP BY 1 ORDER BY costo_usd DESC, llamadas DESC", **params)
        preguntas = (await self._filas(f"SELECT COUNT(*) AS n {base} AND operacion = 'chat'", **params))[0]["n"]
        return {
            "dias": dias,
            "total": {**total, "preguntas": preguntas,
                      "costo_por_pregunta_usd": round(float(total["costo_usd"]) / preguntas, 6) if preguntas else None},
            "por_dia": por_dia, "por_operacion": por_operacion, "por_modelo": por_modelo,
            "modelos_sin_precio": [m["modelo"] for m in por_modelo if m["sin_precio"]],
        }

    async def listar_modelos(self) -> List[dict]:
        return await self._filas("""
            SELECT codigo, nombre, proveedor, nombre_modelo, parametros_extra, esta_activo, actualizado_at
            FROM asistente.configuracion_modelo ORDER BY codigo
        """)

    async def guardar_modelo(self, codigo: str, nombre_modelo: str, proveedor: str, parametros_extra: dict) -> dict:
        fila = (await self.session.execute(text("""
            INSERT INTO asistente.configuracion_modelo (nombre, codigo, proveedor, nombre_modelo, parametros_extra)
            VALUES (:codigo, :codigo, :prov, :modelo, CAST(:params AS jsonb))
            ON CONFLICT (codigo) DO UPDATE
            SET nombre_modelo = EXCLUDED.nombre_modelo, proveedor = EXCLUDED.proveedor,
                parametros_extra = EXCLUDED.parametros_extra, esta_activo = TRUE, actualizado_at = NOW()
            RETURNING codigo, nombre_modelo, proveedor, parametros_extra, esta_activo, actualizado_at
        """), {"codigo": codigo, "prov": proveedor, "modelo": nombre_modelo,
               "params": json.dumps(parametros_extra or {})})).mappings().first()
        await self.session.commit()
        return dict(fila)
