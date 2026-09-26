from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import get_settings

app = FastAPI(title="Itaú-Native Agent Squads — MVP Crédito Agro", version="0.1.0")
app.include_router(router, prefix="/api")

_settings = get_settings()
if _settings.frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_settings.frontend_dist, html=True), name="frontend")
