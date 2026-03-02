from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_app_state, get_conversation_memory, get_llm_client
from app.models.schemas import ChatRequest, ChatResponse
from app.services.intent_processor import ServiceSelectionError, build_prompt

router = APIRouter(prefix="", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    app_state=Depends(get_app_state),
    memory=Depends(get_conversation_memory),
    llm_client=Depends(get_llm_client),
) -> ChatResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    try:
        intent_result = await build_prompt(
            payload.message,
            services=app_state.services,
            availability=app_state.availability,
            llm_client=llm_client,
            memory=memory,
            user_id=payload.user_id,
        )
    except ServiceSelectionError as exc:
        raise HTTPException(status_code=422, detail=exc.detail)

    if intent_result.status == "ambiguous":
        memory.add_message(payload.user_id, "user", payload.message)
        memory.add_message(
            payload.user_id,
            "assistant",
            intent_result.response or "",
        )
        return ChatResponse(
            response=intent_result.response or "",
            intent=intent_result.intent,
            service_name=None,
            status=intent_result.status,
            message=intent_result.message,
            options=intent_result.options,
        )

    history = memory.get_history(payload.user_id)

    try:
        response_text = await llm_client.generate(
            prompt=intent_result.prompt,
            history=history,
        )
    except Exception:
        raise HTTPException(status_code=502, detail="LLM provider error")

    memory.add_message(payload.user_id, "user", payload.message)
    memory.add_message(payload.user_id, "assistant", response_text)

    return ChatResponse(
        response=response_text,
        intent=intent_result.intent,
        service_name=intent_result.service_name,
    )
