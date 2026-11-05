"""Backend Claude lewat SDK resmi `anthropic` (pip install anthropic).

Tiga platform, satu kelas; yang beda hanya cara membuat client:
  anthropic          API Anthropic langsung (ANTHROPIC_API_KEY atau `ant auth login`)
  anthropic-bedrock  Claude di Amazon Bedrock (kredensial AWS biasa + AWS_REGION)
  anthropic-vertex   Claude di Google Vertex AI (gcloud ADC + ANTHROPIC_VERTEX_PROJECT_ID)
"""

import os

from .base import Backend, LLMError, StructuredOutputUnsupported, register

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicBackend(Backend):
    def __init__(self, model, platform="anthropic"):
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("SDK anthropic belum terinstall: pip install anthropic") from e
        self.sdk = anthropic
        self.platform = platform
        self.name = platform
        self.effort = os.environ.get("LAB_LLM_EFFORT") or "high"

        if platform == "anthropic":
            self.client = anthropic.Anthropic()
            default = DEFAULT_MODEL
        elif platform == "anthropic-bedrock":
            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
            if not region:
                raise LLMError("Set AWS_REGION untuk anthropic-bedrock")
            self.client = anthropic.AnthropicBedrockMantle(aws_region=region)
            default = "anthropic." + DEFAULT_MODEL  # ID model Bedrock pakai prefix anthropic.
        elif platform == "anthropic-vertex":
            project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not project:
                raise LLMError("Set ANTHROPIC_VERTEX_PROJECT_ID untuk anthropic-vertex")
            self.client = anthropic.AnthropicVertex(
                project_id=project, region=os.environ.get("CLOUD_ML_REGION") or "global")
            default = DEFAULT_MODEL
        else:
            raise LLMError(f"Platform Anthropic tidak dikenal: {platform}")
        super().__init__(model or default)

    def _request(self, system, user, schema, structured):
        kwargs = {
            "model": self.model,
            "max_tokens": 16000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort},
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if structured:
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}
        if self.platform == "anthropic":
            # Fitur API langsung: fallback server-side kalau model menolak
            # (refusal), dan prompt caching untuk run berulang (--repeat).
            # Di Bedrock/Vertex fallback server-side tidak tersedia.
            kwargs["cache_control"] = {"type": "ephemeral"}
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        return self.client.messages.create(**kwargs)

    def _call(self, system, user, schema, structured):
        a = self.sdk
        try:
            resp = self._request(system, user, schema, structured)
        except a.BadRequestError as e:
            if structured and ("output_config" in e.message or "format" in e.message):
                raise StructuredOutputUnsupported() from e
            raise LLMError(f"Request ditolak (400): {e.message}") from e
        except a.AuthenticationError as e:
            raise LLMError(f"Kredensial {self.platform} tidak valid") from e
        except a.PermissionDeniedError as e:
            raise LLMError(f"Akses ditolak: {e.message}") from e
        except a.NotFoundError as e:
            raise LLMError(f"Model tidak ditemukan: {self.model}") from e
        except a.RateLimitError as e:
            raise LLMError(f"Rate limit: {e.message}") from e
        except a.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"Tidak bisa terhubung ke {self.platform}: {e}") from e
        except TypeError as e:
            # SDK melempar TypeError (bukan AuthenticationError) kalau sama sekali
            # tidak ada kredensial: tanpa ANTHROPIC_API_KEY maupun login.
            if "authentication" in str(e).lower():
                raise LLMError(f"Kredensial {self.platform} belum diset (ANTHROPIC_API_KEY atau login)") from e
            raise

        if resp.stop_reason == "refusal":
            cat = resp.stop_details.category if resp.stop_details else None
            raise LLMError(f"Model menolak permintaan (kategori: {cat})")
        if resp.stop_reason == "max_tokens":
            raise LLMError("Output terpotong (max_tokens)")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Respons tanpa blok teks")
        u = resp.usage
        return text, {
            "provider": self.platform, "model": resp.model, "effort": self.effort,
            "request_id": resp._request_id,
            "usage": {
                "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
                "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
            },
        }


@register("anthropic", "Claude via API Anthropic (default)", needs=["ANTHROPIC_API_KEY"])
def _anthropic(model):
    return AnthropicBackend(model, "anthropic")


@register("anthropic-bedrock", "Claude di Amazon Bedrock", needs=["AWS_REGION"])
def _bedrock(model):
    return AnthropicBackend(model, "anthropic-bedrock")


@register("anthropic-vertex", "Claude di Google Vertex AI", needs=["ANTHROPIC_VERTEX_PROJECT_ID"])
def _vertex(model):
    return AnthropicBackend(model, "anthropic-vertex")
