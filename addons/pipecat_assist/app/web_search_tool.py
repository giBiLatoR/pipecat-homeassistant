"""Optional web search tool exposed to assistant models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from openai import AsyncOpenAI
from pipecat.adapters.schemas.function_schema import FunctionSchema

if TYPE_CHECKING:
    from pipecat.services.llm_service import FunctionCallParams


WEB_SEARCH_TOOL_NAME = "web_search"


async def run_openai_web_search(api_key: str, model: str, query: str) -> str:
    """Run a short OpenAI Responses web search answer."""

    query = (query or "").strip()
    if not query:
        return "No search query was provided."

    client = AsyncOpenAI(api_key=api_key)
    response = await client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        tool_choice="required",
        input=(
            "Answer in at most 2 short sentences suitable for being read aloud, "
            "in the same language as the question. Do not include URLs, citations, "
            f"or markdown. Question: {query}"
        ),
    )
    return (getattr(response, "output_text", "") or "").strip() or "I could not find a useful web result."


def create_web_search_handler(api_key: str, model: str):
    """Return a Pipecat function-call handler for web search."""

    async def handler(params: "FunctionCallParams") -> None:
        query = str((params.arguments or {}).get("query", "")).strip()
        logger.info("web_search called: {!r} (model={})", query, model)
        try:
            answer = await run_openai_web_search(api_key, model, query)
        except Exception as err:
            logger.warning("web_search failed: {}", err)
            answer = "Web search is not available right now."
        await params.result_callback(answer)

    return handler


def web_search_schema(api_key: str, model: str) -> FunctionSchema:
    """Return the Pipecat function schema for web search."""

    return FunctionSchema(
        name=WEB_SEARCH_TOOL_NAME,
        description=(
            "Search the public internet for current, recent, factual, or external "
            "information such as news, weather, sports scores, opening hours, prices, "
            "travel information, or facts outside the assistant context. Do not use "
            "this for smart-home control; use Home Assistant tools for devices."
        ),
        properties={
            "query": {
                "type": "string",
                "description": "A clear natural-language search query in the user's language.",
            }
        },
        required=["query"],
        handler=create_web_search_handler(api_key, model),
    )
