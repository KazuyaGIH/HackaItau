"""Endpoints P0 (ARCHITECTURE.md §19.9). Kernel: só /health implementado; o resto é S1.9."""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    s = get_settings()
    if s.llm_configured:
        llm_mode = "real"
    elif s.llm_fallback_enabled:
        llm_mode = "fallback"
    else:
        llm_mode = "unconfigured"
    return {"ok": True, "llm_mode": llm_mode, "demo_mode": s.demo_mode}
