import os
from typing import Optional


class AIService:
    """Unified AI service — routes between Ollama (local), Groq, OpenAI, and Anthropic."""

    SUPPORTED_PROVIDERS = ("ollama", "groq", "openai", "anthropic")

    def __init__(
        self,
        provider: str = "ollama",
        ollama_model: str = "llama3",
        ollama_url: str = "http://localhost:11434",
        groq_model: str = "llama-3.3-70b-versatile",
        groq_api_key: str = "",
        openai_model: str = "gpt-4o-mini",
        openai_api_key: str = "",
        anthropic_model: str = "claude-haiku-4-5-20251001",
        anthropic_api_key: str = "",
    ):
        if provider not in self.SUPPORTED_PROVIDERS:
            provider = "ollama"
        self.provider = provider
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.groq_model = groq_model
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        self.openai_model = openai_model
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self.anthropic_model = anthropic_model
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._groq_client = None
        self._openai_client = None
        self._anthropic_client = None

    # ── Lazy SDK clients ──────────────────────────────────────────────────────
    @property
    def groq_client(self):
        if self._groq_client is None:
            if not self.groq_api_key:
                raise ValueError("Groq API key not configured. Go to Settings to add it.")
            from groq import Groq
            self._groq_client = Groq(api_key=self.groq_api_key)
        return self._groq_client

    @property
    def openai_client(self):
        if self._openai_client is None:
            if not self.openai_api_key:
                raise ValueError("OpenAI API key not configured. Go to Settings to add it.")
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=self.openai_api_key)
        return self._openai_client

    @property
    def anthropic_client(self):
        if self._anthropic_client is None:
            if not self.anthropic_api_key:
                raise ValueError("Anthropic API key not configured. Go to Settings to add it.")
            from anthropic import Anthropic
            self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    # ── Public API ────────────────────────────────────────────────────────────
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def chat(self, messages: list) -> str:
        try:
            if self.provider == "ollama":
                return self._ollama_chat(messages)
            if self.provider == "groq":
                return self._groq_chat(messages)
            if self.provider == "openai":
                return self._openai_chat(messages)
            if self.provider == "anthropic":
                return self._anthropic_chat(messages)
            return f"[AI Error]: Unknown provider '{self.provider}'"
        except Exception as e:
            return f"[AI Error — {self.provider}]: {e}"

    # ── Provider implementations ──────────────────────────────────────────────
    def _ollama_chat(self, messages: list) -> str:
        from ollama import Client as _OllamaClient
        client = _OllamaClient(host=self.ollama_url)
        response = client.chat(
            model=self.ollama_model,
            messages=messages,
            options={"num_predict": 600, "temperature": 0.7},  # cap tokens → faster
        )
        # Handle both dict and object response styles across ollama versions
        if isinstance(response, dict):
            return response["message"]["content"]
        return response.message.content

    def _groq_chat(self, messages: list) -> str:
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content

    def _openai_chat(self, messages: list) -> str:
        response = self.openai_client.chat.completions.create(
            model=self.openai_model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )
        return response.choices[0].message.content

    def _anthropic_chat(self, messages: list) -> str:
        # Anthropic Messages API takes `system` separately from `messages`.
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        chat_msgs = [m for m in messages if m.get("role") != "system"]
        kwargs = dict(
            model=self.anthropic_model,
            messages=chat_msgs,
            temperature=0.7,
            max_tokens=2048,
        )
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        response = self.anthropic_client.messages.create(**kwargs)
        # response.content is a list of content blocks; join the text blocks.
        parts = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)

    # ── Health check ──────────────────────────────────────────────────────────
    def is_available(self) -> tuple[bool, str]:
        """Return (ok, message) for connection test."""
        try:
            if self.provider == "ollama":
                import requests
                r = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    try:
                        from ollama import Client as _OC
                        _OC(host=self.ollama_url).chat(
                            model=self.ollama_model,
                            messages=[{"role": "user", "content": "hi"}],
                        )
                    except Exception as e2:
                        return False, f"Ollama running but chat failed: {e2}"
                    return True, f"Ollama ready. Models: {', '.join(models[:5]) or 'none pulled'}"
                return False, f"Ollama responded with HTTP {r.status_code}"

            if self.provider == "groq" and not self.groq_api_key:
                return False, "Groq API key not set."
            if self.provider == "openai" and not self.openai_api_key:
                return False, "OpenAI API key not set."
            if self.provider == "anthropic" and not self.anthropic_api_key:
                return False, "Anthropic API key not set."

            result = self.generate("Say 'OK' only.")
            if result.startswith("[AI Error"):
                return False, result
            return True, f"{self.provider.title()} connected. Response: {result[:80]}"
        except Exception as e:
            return False, str(e)

    # ── Model discovery ───────────────────────────────────────────────────────
    def list_ollama_models(self) -> list[str]:
        try:
            import requests
            r = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        try:
            from ollama import Client as _OC
            data = _OC(host=self.ollama_url).list()
            return [m.model for m in data.models] if hasattr(data, "models") else []
        except Exception:
            pass
        return []

    # ── Display helpers ───────────────────────────────────────────────────────
    @property
    def model_name(self) -> str:
        return {
            "ollama": self.ollama_model,
            "groq": self.groq_model,
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
        }.get(self.provider, self.ollama_model)

    @property
    def provider_label(self) -> str:
        pretty = {
            "ollama": "Ollama",
            "groq": "Groq",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
        }.get(self.provider, self.provider)
        return f"{pretty} ({self.model_name})"
