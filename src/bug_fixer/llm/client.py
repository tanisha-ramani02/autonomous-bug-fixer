"""Unified LLM client interface with multi-key rotation and token/cost tracking."""
import json
import re
from typing import Dict, Any, Optional, List
import requests
from bug_fixer.config.settings import settings
from bug_fixer.config.logger_config import logger
from bug_fixer.models.state import TokenCostSummary


# Model pricing in USD per 1M tokens
MODEL_PRICING = {
    # Gemini models
    "gemini-flash-latest": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-2.5-flash": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-3.6-flash": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-3.7-flash": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-2.5-pro": {"input_per_m": 1.25, "output_per_m": 5.00},
    # Groq models
    "llama-3.3-70b-versatile": {"input_per_m": 0.59, "output_per_m": 0.79},
    "llama-3.1-8b-instant": {"input_per_m": 0.05, "output_per_m": 0.08},
    "mixtral-8x7b-32768": {"input_per_m": 0.24, "output_per_m": 0.24},
}


class LLMClient:
    """Unified client handling Gemini and Groq API requests with failover key rotation."""

    def __init__(self):
        self.tracker = TokenCostSummary()
        self.gemini_keys = settings.get_gemini_keys()
        self.groq_keys = settings.get_groq_keys()
        self._gemini_key_idx = 0
        self._groq_key_idx = 0

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """
        Generate completion using the active provider, with automatic key rotation on errors.
        """
        provider = provider or settings.primary_provider
        
        # If Gemini is chosen or Groq keys are not configured
        if provider.lower() == "gemini" or (not self.groq_keys and self.gemini_keys):
            return self._call_gemini(
                prompt=prompt,
                system_instruction=system_instruction,
                model=model or settings.gemini_model1,
                temperature=temperature
            )
        elif provider.lower() == "groq" and self.groq_keys:
            return self._call_groq(
                prompt=prompt,
                system_instruction=system_instruction,
                model=model or settings.groq_model1,
                temperature=temperature
            )
        else:
            # Fallback to whatever key is available
            if self.gemini_keys:
                return self._call_gemini(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=model or settings.gemini_model1,
                    temperature=temperature
                )
            elif self.groq_keys:
                return self._call_groq(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=model or settings.groq_model1,
                    temperature=temperature
                )
            else:
                raise ValueError("No API keys found. Please set GOOGLE_API_KEY1 or GROQ_API_KEY1 in .env")

    def _call_gemini(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "gemini-flash-latest",
        temperature: float = 0.2
    ) -> str:
        """Call Google Gemini REST API with key rotation."""
        if not self.gemini_keys:
            raise ValueError("No Gemini API keys configured.")

        last_error = None
        for attempt in range(len(self.gemini_keys)):
            current_key = self.gemini_keys[self._gemini_key_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={current_key}"
            logger.debug(f"Calling Gemini API (model={model}, key_index={self._gemini_key_idx})")
            
            payload = {
                "contents": [
                    {"parts": [{"text": prompt}]}
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 4096
                }
            }
            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            try:
                response = requests.post(url, json=payload, timeout=45)
                if response.status_code == 200:
                    data = response.json()
                    candidate = data["candidates"][0]
                    text_out = candidate["content"]["parts"][0]["text"]
                    
                    # Track tokens
                    usage = data.get("usageMetadata", {})
                    prompt_tokens = usage.get("promptTokenCount", len(prompt.split()) * 2)
                    comp_tokens = usage.get("candidatesTokenCount", len(text_out.split()) * 2)
                    
                    cost = self._calculate_cost(model, prompt_tokens, comp_tokens)
                    self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                    logger.debug(f"Gemini response received: {prompt_tokens} prompt tokens, {comp_tokens} completion tokens, cost=${cost:.5f}")
                    return text_out
                else:
                    last_error = f"Gemini HTTP {response.status_code}: {response.text}"
                    logger.warning(f"Gemini API call failed with status {response.status_code}. Rotating key... (error: {response.text[:200]})")
                    self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Gemini request exception: {e}. Rotating key...")
                self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)

        raise RuntimeError(f"All Gemini keys failed. Last error: {last_error}")

    def _call_groq(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2
    ) -> str:
        """Call Groq API with key rotation."""
        if not self.groq_keys:
            raise ValueError("No Groq API keys configured.")

        last_error = None
        for _ in range(len(self.groq_keys)):
            current_key = self.groq_keys[self._groq_key_idx]
            url = "https://api.groq.com/openai/v1/chat/completions"
            
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096
            }
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json"
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=45)
                if response.status_code == 200:
                    data = response.json()
                    text_out = data["choices"][0]["message"]["content"]
                    
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt.split()) * 2)
                    comp_tokens = usage.get("completion_tokens", len(text_out.split()) * 2)
                    
                    cost = self._calculate_cost(model, prompt_tokens, comp_tokens)
                    self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                    return text_out
                else:
                    last_error = f"Groq HTTP {response.status_code}: {response.text}"
                    self._groq_key_idx = (self._groq_key_idx + 1) % len(self.groq_keys)
            except Exception as e:
                last_error = str(e)
                self._groq_key_idx = (self._groq_key_idx + 1) % len(self.groq_keys)

        raise RuntimeError(f"All Groq keys failed. Last error: {last_error}")

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate USD cost for a single invocation based on token counts."""
        pricing = MODEL_PRICING.get(model, {"input_per_m": 0.10, "output_per_m": 0.40})
        cost = (prompt_tokens / 1_000_000 * pricing["input_per_m"]) + (
            completion_tokens / 1_000_000 * pricing["output_per_m"]
        )
        return round(cost, 6)

    def extract_json(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from LLM response with robust fallback."""
        # Try direct parse
        try:
            return json.loads(text.strip())
        except Exception:
            pass

        # Try markdown ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Try finding first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        raise ValueError(f"Could not parse valid JSON from model response: {text[:200]}...")
