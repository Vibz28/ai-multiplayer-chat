from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

import yaml
from langchain_core.load import load as lc_load
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence
from langsmith import Client as LangSmithClient

from app.config import Settings

logger = logging.getLogger(__name__)


class PromptLoadError(RuntimeError):
    """Raised when a prompt cannot be loaded or coerced into a chat template."""


def _coerce_chat_prompt_template(candidate: Any) -> ChatPromptTemplate:
    if isinstance(candidate, ChatPromptTemplate):
        return candidate

    if isinstance(candidate, RunnableSequence):
        sequence_steps = [candidate.first, *candidate.middle, candidate.last]
        for step in sequence_steps:
            if isinstance(step, ChatPromptTemplate):
                return step

    raise PromptLoadError(
        f"Unsupported prompt object type: {type(candidate)!r}. Expected ChatPromptTemplate-compatible object."
    )


def _resolve_manifest_path(settings: Settings) -> Path:
    manifest_path = Path(settings.agent_prompt_manifest_path)
    if manifest_path.is_absolute():
        return manifest_path
    service_root = Path(__file__).resolve().parents[1]
    return service_root / manifest_path


def load_local_prompt_template(settings: Settings) -> ChatPromptTemplate:
    manifest_path = _resolve_manifest_path(settings)
    if not manifest_path.exists():
        raise PromptLoadError(f"Prompt manifest not found: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest_payload = yaml.safe_load(handle)

    if not isinstance(manifest_payload, dict):
        raise PromptLoadError(f"Prompt manifest at {manifest_path} must deserialize to a mapping")

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The function `load` is in beta.*")
        loaded = lc_load(manifest_payload)
    return _coerce_chat_prompt_template(loaded)


def load_prompt_from_hub(prompt_identifier: str) -> ChatPromptTemplate:
    client = LangSmithClient()
    pulled = client.pull_prompt(prompt_identifier, include_model=False)
    return _coerce_chat_prompt_template(pulled)


def build_fallback_prompt_template(settings: Settings) -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", settings.agent_system_prompt_fallback),
            ("human", "{user_message}"),
        ]
    )


def load_agent_prompt_template(settings: Settings) -> ChatPromptTemplate:
    prompt_identifier = (settings.agent_prompt_hub_identifier or "").strip()
    if prompt_identifier:
        try:
            logger.info("Loading agent prompt from LangSmith Hub: %s", prompt_identifier)
            return load_prompt_from_hub(prompt_identifier)
        except Exception as exc:
            logger.warning(
                "Failed to load prompt from LangSmith Hub (%s); falling back to local manifest. Error: %s",
                prompt_identifier,
                exc,
            )

    try:
        return load_local_prompt_template(settings)
    except Exception as exc:
        logger.warning("Failed to load local prompt manifest; using fallback prompt. Error: %s", exc)
        return build_fallback_prompt_template(settings)
