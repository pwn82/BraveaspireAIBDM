import os
import time
from typing import Optional


class AIService:
    """Unified AI service — switches between Ollama (local) and Groq (cloud)."""

    def __init__(
        self,
        provider: str = "ollama",
        ollama_model: str = "llama3",
        ollama_url: str = "http://localhost:11434",
        groq_model: str = "llama3-70b-8192",
        groq_api_key: str = "",
    ):
        self.provider = provider
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url
        self.groq_model = groq_model
        self.groq_api_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
        self._groq_client = None

    @property
    def groq_client(self):
        if self._groq_client is None:
            if not self.groq_api_key:
                raise ValueError("Groq API key not configured. Go to Settings to add it.")
            from groq import Groq
            self._groq_client = Groq(api_key=self.groq_api_key)
        return self._groq_client

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def chat(self, messages: list) -> str:
        start = time.time()
        try:
            if self.provider == "ollama":
                result = self._ollama_chat(messages)
            else:
                result = self._groq_chat(messages)
            return result
        except Exception as e:
            return f"[AI Error — {self.provider}]: {e}"

    def _ollama_chat(self, messages: list) -> str:
        from ollama import Client as _OllamaClient
        client   = _OllamaClient(host=self.ollama_url)
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

    def is_available(self) -> tuple[bool, str]:
        """Return (ok, message) for connection test."""
        try:
            if self.provider == "ollama":
                import requests
                r = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    # Quick smoke-test: actually call the model
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
            else:
                if not self.groq_api_key:
                    return False, "Groq API key not set."
                result = self.generate("Say 'OK' only.")
                if result.startswith("[AI Error"):
                    return False, result
                return True, f"Groq connected. Response: {result[:80]}"
        except Exception as e:
            return False, str(e)

    def list_ollama_models(self) -> list[str]:
        try:
            import requests
            r = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        # Fallback via ollama Client
        try:
            from ollama import Client as _OC
            data = _OC(host=self.ollama_url).list()
            return [m.model for m in data.models] if hasattr(data, "models") else []
        except Exception:
            pass
        return []

    @property
    def model_name(self) -> str:
        return self.ollama_model if self.provider == "ollama" else self.groq_model

    @property
    def provider_label(self) -> str:
        return f"Ollama ({self.ollama_model})" if self.provider == "ollama" else f"Groq ({self.groq_model})"
