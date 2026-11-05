"""Backend catch-all lewat LiteLLM (pip install litellm), 100+ provider.

Dipakai untuk provider yang tidak OpenAI-compatible dan bukan Claude:
Azure OpenAI, Bedrock/Vertex untuk model non-Claude, Cohere, dll.
Nama model memakai format LiteLLM `<provider>/<model>`, mis.
`azure/<deployment>`, `bedrock/<model-id>`, `vertex_ai/<model>`.
Kredensial dibaca LiteLLM sendiri dari env standar tiap provider
(AZURE_API_KEY, AWS_*, dsb.); lihat dokumentasi LiteLLM.
"""

import os

from .base import Backend, LLMError, StructuredOutputUnsupported, register


class LiteLLMBackend(Backend):
    name = "litellm"

    def __init__(self, model, timeout=600):
        try:
            import litellm
        except ImportError as e:
            raise LLMError("litellm belum terinstall: pip install litellm") from e
        if not model or "/" not in model:
            raise LLMError("LAB_LLM_MODEL untuk litellm harus berformat <provider>/<model>, mis. azure/my-deployment")
        super().__init__(model)
        self.litellm = litellm
        self.timeout = timeout
        self.api_base = os.environ.get("LAB_LLM_BASE_URL")

    def _call(self, system, user, schema, structured):
        lt = self.litellm
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "timeout": self.timeout,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if structured:
            # Tanya LiteLLM dulu apakah model ini mendukung JSON schema; kalau
            # tidak, langsung pakai mode instruksi tanpa membuang satu request.
            try:
                supported = lt.supports_response_schema(model=self.model)
            except Exception:
                supported = True  # model tak dikenal LiteLLM: coba saja
            if not supported:
                raise StructuredOutputUnsupported()
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "evaluation", "schema": schema, "strict": True}}
        try:
            resp = lt.completion(**kwargs)
        except lt.exceptions.BadRequestError as e:
            if structured:
                raise StructuredOutputUnsupported(str(e)) from e
            raise LLMError(f"Request ditolak: {e}") from e
        except lt.exceptions.AuthenticationError as e:
            raise LLMError(f"Kredensial ditolak untuk {self.model}") from e
        except lt.exceptions.RateLimitError as e:
            raise LLMError(f"Rate limit: {e}") from e
        except lt.exceptions.APIConnectionError as e:
            raise LLMError(f"Tidak bisa terhubung: {e}") from e
        except lt.exceptions.APIError as e:
            raise LLMError(f"API error: {e}") from e

        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise LLMError("Output terpotong (length)")
        usage = getattr(resp, "usage", None)
        return choice.message.content or "", {
            "provider": self.name, "model": resp.model or self.model,
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
        }


@register("litellm", "Provider lain lewat LiteLLM (model: <provider>/<model>)", needs=["LAB_LLM_MODEL"])
def _litellm(model):
    return LiteLLMBackend(model)
