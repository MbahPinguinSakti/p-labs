"""Test lapisan LLM tanpa jaringan dan tanpa API key.

Jalankan dari root project:
    python3 -m unittest discover -s platform/tests -v

Server tiruan (MockServer) berjalan di localhost dan meniru dua format:
  POST /v1/chat/completions   (OpenAI-compatible, juga dipakai LiteLLM)
  POST /v1/messages           (Anthropic, untuk SDK `anthropic`)
Setiap test mengisi antrean respons, lalu memeriksa request yang diterima.
Test untuk SDK anthropic / litellm dilewati kalau paketnya belum terinstall.
"""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

PLATFORM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLATFORM))

import llm  # noqa: E402
from llm.base import REGISTRY, Backend, LLMError, parse_json_text, register, schema_errors  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def have(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


class MockServer:
    """HTTP server kecil: kembalikan respons dari antrean, catat semua request."""

    def __init__(self):
        self.queue, self.requests = [], []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, payload = owner.queue.pop(0)
                # str = body mentah (mis. SSE), selain itu di-encode JSON.
                raw = isinstance(payload, str)
                data = payload.encode() if raw else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream" if raw else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def openai_reply(content, finish="stop"):
    return {"model": "mock-model", "choices": [{"finish_reason": finish,
            "message": {"role": "assistant", "content": content}}], "usage": {"total_tokens": 3}}


def anthropic_reply(text, stop="end_turn"):
    return {"id": "msg_mock", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


class TestParseJson(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(parse_json_text('{"ok": true}'), {"ok": True})

    def test_fenced(self):
        self.assertEqual(parse_json_text('```json\n{"ok": true}\n```'), {"ok": True})

    def test_surrounded_by_text(self):
        self.assertEqual(parse_json_text('Berikut hasilnya: {"ok": false} semoga membantu'), {"ok": False})

    def test_invalid(self):
        with self.assertRaises(LLMError):
            parse_json_text("bukan json")


class TestSchemaErrors(unittest.TestCase):
    S = {"type": "object", "required": ["a", "xs"], "additionalProperties": False,
         "properties": {"a": {"type": "integer"},
                        "b": {"type": "string", "enum": ["x", "y"]},
                        "xs": {"type": "array", "items": {"type": "object", "required": ["id"],
                                                          "properties": {"id": {"type": "string"}}}}}}

    def test_valid(self):
        self.assertEqual(schema_errors({"a": 1, "b": "x", "xs": [{"id": "E1"}]}, self.S), [])

    def test_errors_have_paths(self):
        errs = schema_errors({"a": True, "b": "z", "xs": [{}], "c": 1}, self.S)
        self.assertIn("$.a: harus integer, dapat bool", errs)  # bool bukan integer
        self.assertTrue(any(e.startswith("$.b:") for e in errs))
        self.assertIn("$.xs[0].id: wajib ada", errs)
        self.assertIn("$.c: field tidak dikenal", errs)

    def test_missing_required(self):
        self.assertEqual(schema_errors({}, self.S), ["$.a: wajib ada", "$.xs: wajib ada"])


class TestOpenAICompatible(unittest.TestCase):
    def setUp(self):
        self.srv = MockServer()
        env = {"LAB_LLM_BASE_URL": self.srv.url + "/v1", "LAB_LLM_API_KEY": "test-key"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.backend = llm.get_backend("openai-compatible", "mock-model")

    def tearDown(self):
        self.env.stop()
        self.srv.close()

    def test_structured_output(self):
        self.srv.queue.append((200, openai_reply('{"ok": true}')))
        data, meta = self.backend.complete_json("sys", "user", SCHEMA)
        self.assertEqual(data, {"ok": True})
        self.assertTrue(meta["structured_output"])
        req = self.srv.requests[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(req["body"]["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertIs(req["body"]["stream"], False)

    def test_schema_ignored_then_repaired(self):
        # Server menerima json_schema tapi mengabaikannya (kasus 9Router):
        # jawaban pertama salah bentuk, retry mode instruksi memperbaikinya.
        self.srv.queue += [(200, openai_reply('{"oke": "ya"}')),
                           (200, openai_reply('{"ok": true}'))]
        data, meta = self.backend.complete_json("sys", "user", SCHEMA)
        self.assertEqual(data, {"ok": True})
        self.assertTrue(meta["schema_retry"])
        self.assertFalse(meta["structured_output"])
        second = self.srv.requests[1]["body"]
        self.assertNotIn("response_format", second)
        self.assertIn("$.ok: wajib ada", second["messages"][1]["content"])

    def test_schema_still_wrong_after_repair(self):
        self.srv.queue += [(200, openai_reply('{"oke": 1}')), (200, openai_reply('{"ok": "ya"}'))]
        with self.assertRaisesRegex(LLMError, "setelah 1x perbaikan"):
            self.backend.complete_json("sys", "user", SCHEMA)

    def test_non_json_body(self):
        self.srv.queue.append((200, 'data: {"choices": []}\n\n'))
        with self.assertRaisesRegex(LLMError, "bukan JSON"):
            self.backend.complete_json("sys", "user", SCHEMA)

    def test_fallback_to_instruction_mode(self):
        # Request pertama (json_schema) ditolak 400, request kedua tanpa response_format.
        self.srv.queue += [(400, {"error": "json_schema not supported"}),
                           (200, openai_reply('```json\n{"ok": true}\n```'))]
        data, meta = self.backend.complete_json("sys", "user", SCHEMA)
        self.assertEqual(data, {"ok": True})
        self.assertFalse(meta["structured_output"])
        second = self.srv.requests[1]["body"]
        self.assertNotIn("response_format", second)
        self.assertIn("JSON Schema", second["messages"][1]["content"])

    def test_auth_error(self):
        self.srv.queue.append((401, {"error": "bad key"}))
        with self.assertRaisesRegex(LLMError, "ditolak"):
            self.backend.complete_json("sys", "user", SCHEMA)

    def test_truncated(self):
        self.srv.queue.append((200, openai_reply('{"ok"', finish="length")))
        with self.assertRaisesRegex(LLMError, "terpotong"):
            self.backend.complete_json("sys", "user", SCHEMA)


class TestPresets(unittest.TestCase):
    def test_preset_needs_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(LLMError, "OPENAI_API_KEY"):
                llm.get_backend("openai", "some-model")

    def test_local_preset_needs_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            b = llm.get_backend("ollama", "some-model")
            self.assertEqual(b.base_url, "http://localhost:11434/v1")
            self.assertIsNone(b.api_key)

    def test_preset_default_model(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LAB_LLM_MODEL", None)
            self.assertEqual(llm.get_backend("9router").model, "ag/claude-sonnet-4-6")
            self.assertEqual(llm.get_backend("9router", "x/y").model, "x/y")
        with self.assertRaises(LLMError):
            llm.get_backend("ollama")  # tanpa default: model wajib

    def test_unknown_provider(self):
        with self.assertRaisesRegex(LLMError, "tidak dikenal"):
            llm.get_backend("nope", "x")


class TestRegistry(unittest.TestCase):
    """Contoh paling kecil sebuah backend baru: cukup subclass + @register."""

    def test_custom_backend(self):
        class EchoBackend(Backend):
            name = "echo"

            def _call(self, system, user, schema, structured):
                return '{"ok": true}', {"provider": self.name, "model": self.model}

        register("echo-test", "backend uji")(lambda model: EchoBackend(model or "echo-1"))
        try:
            data, meta = llm.get_backend("echo-test").complete_json("s", "u", SCHEMA)
            self.assertEqual(data, {"ok": True})
            self.assertEqual(meta["model"], "echo-1")
        finally:
            REGISTRY.pop("echo-test")


@unittest.skipUnless(have("anthropic"), "pip install anthropic")
class TestAnthropic(unittest.TestCase):
    def setUp(self):
        self.srv = MockServer()
        # SDK membaca ANTHROPIC_BASE_URL: arahkan ke server tiruan.
        self.env = mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": self.srv.url,
                                                "ANTHROPIC_API_KEY": "test-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.srv.close()

    def test_structured_output(self):
        self.srv.queue.append((200, anthropic_reply('{"ok": true}')))
        data, meta = llm.get_backend("anthropic").complete_json("sys", "user", SCHEMA)
        self.assertEqual(data, {"ok": True})
        body = self.srv.requests[0]["body"]
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["output_config"]["format"]["schema"], SCHEMA)
        self.assertEqual(body["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", self.srv.requests[0]["headers"].get("anthropic-beta", ""))

    def test_refusal(self):
        self.srv.queue.append((200, {**anthropic_reply(""), "stop_reason": "refusal",
                                     "stop_details": {"type": "refusal", "category": None, "explanation": None}}))
        with self.assertRaisesRegex(LLMError, "menolak"):
            llm.get_backend("anthropic").complete_json("sys", "user", SCHEMA)

    def test_structured_rejected_falls_back(self):
        err = {"type": "error", "error": {"type": "invalid_request_error",
               "message": "output_config.format: not supported"}}
        self.srv.queue += [(400, err), (200, anthropic_reply('{"ok": false}'))]
        data, meta = llm.get_backend("anthropic").complete_json("sys", "user", SCHEMA)
        self.assertEqual(data, {"ok": False})
        self.assertFalse(meta["structured_output"])
        self.assertNotIn("format", self.srv.requests[1]["body"]["output_config"])


@unittest.skipUnless(have("litellm"), "pip install litellm")
class TestLiteLLM(unittest.TestCase):
    def test_against_openai_shaped_mock(self):
        srv = MockServer()
        try:
            srv.queue.append((200, openai_reply('{"ok": true}')))
            with mock.patch.dict(os.environ, {"LAB_LLM_BASE_URL": srv.url + "/v1", "OPENAI_API_KEY": "test-key"}):
                data, meta = llm.get_backend("litellm", "openai/mock-model").complete_json("s", "u", SCHEMA)
            self.assertEqual(data, {"ok": True})
            self.assertEqual(srv.requests[0]["path"], "/v1/chat/completions")
        finally:
            srv.close()

    def test_model_format(self):
        with self.assertRaisesRegex(LLMError, "<provider>/<model>"):
            llm.get_backend("litellm", "tanpa-slash")


if __name__ == "__main__":
    unittest.main()
