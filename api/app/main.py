from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import AppState
from app.core.settings import get_settings
from app.routers.chat import router as chat_router
from app.services.conversation_memory import ConversationMemory
from app.services.llm_client import LLMClient, LLMClientError
from app.services.normalizer import (
    NormalizationError,
    normalize_availability,
    normalize_services,
)
from app.services.sheet_loader import CSVSheetLoader
from app.bot import start_bot

logger = logging.getLogger("genbot")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(chat_router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/prices")
    async def prices(
        service: Optional[str] = None, region: Optional[str] = None
    ) -> dict[str, list[dict[str, str]]]:
        loader = CSVSheetLoader(settings.data_dir)
        raw_services = loader.load_services()

        service_filter = (service or "").strip().lower()
        region_filter = (region or "").strip().lower()

        results: list[dict[str, str]] = []
        for row in raw_services:
            row_service = str(row.get("service_name", "")).strip()
            row_region = str(row.get("region", "")).strip()

            if service_filter and row_service.lower() != service_filter:
                continue
            if region_filter and row_region.lower() != region_filter:
                continue

            results.append(
                {
                    "service": row_service,
                    "region": row_region,
                    "description": str(row.get("description", "")).strip(),
                    "price": str(row.get("price", "")).strip(),
                }
            )

        return {"prices": results}

    @app.exception_handler(NormalizationError)
    async def normalization_handler(
        request: Request, exc: NormalizationError
    ) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Data error"})

    @app.exception_handler(LLMClientError)
    async def llm_error_handler(request: Request, exc: LLMClientError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": "LLM provider error"})

    @app.on_event("startup")
    async def startup_event() -> None:
        loader = CSVSheetLoader(settings.data_dir)
        raw_services = loader.load_services()
        raw_availability = loader.load_availability()

        try:
            services = normalize_services(raw_services)
            availability = normalize_availability(raw_availability, services)
        except NormalizationError:
            logger.exception("Failed to normalize CSV data")
            raise

        memory = ConversationMemory(max_messages=settings.memory_max_messages)
        llm_client = LLMClient(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url,
            chat_path=settings.llm_chat_path,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            referer=settings.llm_referer,
            title=settings.llm_title,
        )

        app.state.app_state = AppState(
            services=services,
            availability=availability,
            memory=memory,
            llm_client=llm_client,
        )
        logger.info("Application initialized")
        asyncio.create_task(start_bot())

    return app


app = create_app()
