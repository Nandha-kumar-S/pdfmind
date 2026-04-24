import json
import os
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

class LLMService:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_version: Optional[str] = None,
        temperature: float = 0.0,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER") or "azure_openai").lower().strip()
        self.temperature = temperature

        # Backward compatibility: older configs might pass provider='openai' but use Azure env vars.
        if self.provider == "openai":
            self.provider = "azure_openai"

        self.model = model or self._default_model_for_provider(self.provider)
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION") or "2025-01-01-preview"

        self._client = self._build_client()

    def _build_client(self):
        if self.provider == "azure_openai":
            resolved_api_key = os.getenv("AZURE_OPENAI_API_KEY")
            resolved_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

            if not resolved_api_key:
                raise ValueError("AZURE_OPENAI_API_KEY is required for provider='azure_openai'")
            if not resolved_endpoint:
                raise ValueError("AZURE_OPENAI_ENDPOINT is required for provider='azure_openai'")

            return AzureChatOpenAI(
                azure_deployment=self.model,
                api_version=self.api_version,
                api_key=resolved_api_key,
                azure_endpoint=resolved_endpoint,
                temperature=self.temperature,
            )

        if self.provider == "gemini":
            # Gemini API (not Vertex AI)
            # Requires: GOOGLE_API_KEY
            resolved_api_key = os.getenv("GOOGLE_API_KEY")
            if not resolved_api_key:
                raise ValueError("GOOGLE_API_KEY is required for provider='gemini'")

            return ChatGoogleGenerativeAI(
                model=self.model,
                temperature=self.temperature,
                google_api_key=resolved_api_key,
            )

        raise ValueError(f"Unsupported provider: {self.provider}")

    @staticmethod
    def _default_model_for_provider(provider: str) -> str:
        if provider == "gemini":
            return os.getenv("GOOGLE_GEMINI_MODEL") or "gemini-1.5-flash"
        return os.getenv("AZURE_OPENAI_MODEL") or "o3-mini"

    def infer_text(self, prompt: str) -> str:
        resp = self._client.invoke(
            [
                SystemMessage(content="You are a precise assistant."),
                HumanMessage(content=prompt),
            ]
        )
        return (getattr(resp, "content", "") or "").strip()

    def infer_json(self, prompt: str) -> Any:
        resp = self._client.invoke(
            [
                SystemMessage(
                    content=(
                        "Return ONLY valid JSON. Do not include markdown code fences or any other text."
                    )
                ),
                HumanMessage(content=prompt),
            ]
        )
        raw = (getattr(resp, "content", "") or "").strip()
        raw = self._strip_code_fences(raw)
        try:
            parsed = json.loads(raw)
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"LLM JSON decode error: {e}")
            logger.error(f"Failed to parse raw response: {raw}")
            return {"toc": []}

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
                return "\n".join(lines[1:-1]).strip()
        return text