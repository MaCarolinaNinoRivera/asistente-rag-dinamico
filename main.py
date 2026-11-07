from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.config import settings
from app.adapters.inbound.chat_controller import router as chat_router
from app.adapters.inbound.admin_controller import router as admin_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Microservicio independiente de Asistente RAG para Agro"
)

origenes = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Key"],
)

app.include_router(chat_router)
app.include_router(admin_router)

@app.get("/health", tags=["Salud"])
async def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
