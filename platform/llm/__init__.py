"""Lapisan LLM yang tidak terikat provider. Lihat README.md di direktori ini.

    from llm import get_backend, LLMError
    backend = get_backend("openai", model="...")
    data, meta = backend.complete_json(system, user, schema)
"""

from .base import Backend, LLMError, StructuredOutputUnsupported, get_backend, list_providers, register

# Import modul backend supaya decorator @register di dalamnya berjalan dan
# provider-nya masuk ke REGISTRY. Urutan = urutan di `evaluate.py providers`.
from . import anthropic_backend, openai_compat, litellm_backend  # noqa: E402,F401

__all__ = ["Backend", "LLMError", "StructuredOutputUnsupported", "get_backend", "list_providers", "register"]
