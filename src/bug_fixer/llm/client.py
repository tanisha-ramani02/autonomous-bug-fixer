"""Unified LLM client interface with multi-tier provider failover chain, key rotation, and cost tracking."""
import json
import re
import time
import random
from typing import Dict, Any, Optional, List
import requests
from bug_fixer.config.settings import settings
from bug_fixer.config.logger_config import logger
from bug_fixer.models.state import TokenCostSummary


# Model pricing in USD per 1M tokens
MODEL_PRICING = {
    # Gemini models
    "gemini-3.1-flash-lite": {"input_per_m": 0.05, "output_per_m": 0.20},
    "gemini-2.5-flash-lite": {"input_per_m": 0.05, "output_per_m": 0.20},
    "gemini-flash-latest": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-3.6-flash": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-3.7-flash": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gemini-2.5-pro": {"input_per_m": 1.25, "output_per_m": 5.00},
    # Groq modern active models (GPT-OSS)
    "openai/gpt-oss-120b": {"input_per_m": 0.15, "output_per_m": 0.60},
    "openai/gpt-oss-20b": {"input_per_m": 0.075, "output_per_m": 0.30},
    "gpt-oss-120b": {"input_per_m": 0.15, "output_per_m": 0.60},
    "gpt-oss-20b": {"input_per_m": 0.075, "output_per_m": 0.30},
    # OpenAI models
    "gpt-4o": {"input_per_m": 2.50, "output_per_m": 10.00},
    "gpt-4o-mini": {"input_per_m": 0.15, "output_per_m": 0.60},
    "o3-mini": {"input_per_m": 1.10, "output_per_m": 4.40},
    # Anthropic models
    "claude-3-5-sonnet-20241022": {"input_per_m": 3.00, "output_per_m": 15.00},
    "claude-3-5-haiku-20241022": {"input_per_m": 0.80, "output_per_m": 4.00},
}

# Ordered fallback models for maximum reliability and speed
GEMINI_FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.7-flash"
]


class CircuitBreaker:
    """
    Enterprise Circuit Breaker Pattern (CLOSED -> OPEN -> HALF_OPEN).
    Protects the agent against cascading upstream provider outages and rate-limit loops.
    """
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 4, recovery_timeout: float = 20.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_success(self):
        """Reset circuit to CLOSED state on successful request."""
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self):
        """Record failure and trip to OPEN state if threshold exceeded."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(f"[CIRCUIT BREAKER] State -> OPEN (Threshold {self.failure_threshold} reached). Short-circuiting.")

    def allow_request(self) -> bool:
        """Check if request is permitted under circuit breaker state."""
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = self.HALF_OPEN
                logger.info("[CIRCUIT BREAKER] State -> HALF_OPEN (Probing provider recovery).")
                return True
            return False
        return True


class LLMClient:
    """Unified client handling multi-provider failover chains (Gemini -> Groq -> OpenAI -> Anthropic) with key rotation."""

    def __init__(self):
        self.tracker = TokenCostSummary()
        self.gemini_keys = settings.get_gemini_keys()
        self.groq_keys = settings.get_groq_keys()
        self.openai_keys = settings.get_openai_keys()
        self.anthropic_keys = settings.get_anthropic_keys()
        self.provider_chain = settings.get_provider_chain()
        self.circuit_breaker = CircuitBreaker()
        self._gemini_key_idx = 0
        self._groq_key_idx = 0
        self._openai_key_idx = 0
        self._anthropic_key_idx = 0

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.1
    ) -> str:
        """
        Generate completion using the active provider chain with automatic multi-key and provider failover.
        """
        # Determine the order of providers to try
        target_provider = provider or settings.primary_provider
        chain = [target_provider] + [p for p in self.provider_chain if p != target_provider]

        last_error = None
        for prov in chain:
            prov_lower = prov.lower()
            try:
                if prov_lower == "gemini" and self.gemini_keys:
                    return self._call_gemini(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=model or GEMINI_FALLBACK_MODELS[0],
                        temperature=temperature
                    )
                elif prov_lower == "groq" and self.groq_keys:
                    return self._call_groq(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=model or settings.groq_model1,
                        temperature=temperature
                    )
                elif prov_lower == "openai" and self.openai_keys:
                    return self._call_openai(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=model or settings.openai_model1,
                        temperature=temperature
                    )
                elif prov_lower == "anthropic" and self.anthropic_keys:
                    return self._call_anthropic(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=model or settings.anthropic_model1,
                        temperature=temperature
                    )
            except Exception as err:
                last_error = err
                logger.warning(f"Provider {prov_lower.upper()} failover triggered ({err}). Advancing to next provider in chain...")
                continue

        raise RuntimeError(f"All configured providers and keys failed. Last error: {last_error}")

    def _call_gemini(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "gemini-3.1-flash-lite",
        temperature: float = 0.1
    ) -> str:
        """Call Google Gemini REST API with key rotation and model fallback."""
        models_to_try = [model] + [m for m in GEMINI_FALLBACK_MODELS if m != model]
        last_error = None

        for candidate_model in models_to_try:
            for _ in range(len(self.gemini_keys)):
                current_key = self.gemini_keys[self._gemini_key_idx]
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={current_key}"
                logger.debug(f"Invoking Gemini API: model={candidate_model}, key_index={self._gemini_key_idx}")

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
                    response = requests.post(url, json=payload, timeout=18)
                    if response.status_code == 200:
                        self.circuit_breaker.record_success()
                        data = response.json()
                        candidate = data["candidates"][0]
                        text_out = candidate["content"]["parts"][0]["text"]

                        # Track tokens
                        usage = data.get("usageMetadata", {})
                        prompt_tokens = usage.get("promptTokenCount", len(prompt.split()) * 2)
                        comp_tokens = usage.get("candidatesTokenCount", len(text_out.split()) * 2)

                        cost = self._calculate_cost(candidate_model, prompt_tokens, comp_tokens)
                        self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                        logger.debug(f"Gemini response received ({candidate_model}): {prompt_tokens} prompt / {comp_tokens} comp tokens (${cost:.5f})")
                        return text_out
                    elif response.status_code in [429, 500, 503]:
                        self.circuit_breaker.record_failure()
                        last_error = f"HTTP {response.status_code}: {response.text[:120]}"
                        logger.warning(f"Gemini {candidate_model} Key #{self._gemini_key_idx} hit {response.status_code}. Backing off and rotating key...")
                        time.sleep(random.uniform(0.3, 0.8))
                        self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)
                        continue
                    else:
                        self.circuit_breaker.record_failure()
                        last_error = f"HTTP {response.status_code}: {response.text[:150]}"
                        logger.warning(f"Gemini API returned {response.status_code} for {candidate_model}")
                        self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)
                        break
                except requests.exceptions.Timeout:
                    self.circuit_breaker.record_failure()
                    last_error = f"Gemini request timed out after 18s for {candidate_model}"
                    logger.warning(last_error)
                    self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)
                except Exception as e:
                    self.circuit_breaker.record_failure()
                    last_error = str(e)
                    logger.warning(f"Gemini exception: {e}")
                    self._gemini_key_idx = (self._gemini_key_idx + 1) % len(self.gemini_keys)

        raise RuntimeError(f"All Gemini models and keys failed. Last error: {last_error}")

    def _call_groq(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "openai/gpt-oss-120b",
        temperature: float = 0.1
    ) -> str:
        """Call Groq API with modern GPT-OSS models and key rotation."""
        if not self.groq_keys:
            raise ValueError("No Groq API keys configured in .env.")

        last_error = None
        for _ in range(len(self.groq_keys)):
            current_key = self.groq_keys[self._groq_key_idx]
            url = "https://api.groq.com/openai/v1/chat/completions"
            logger.debug(f"Invoking Groq API: model={model}, key_index={self._groq_key_idx}")

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
                response = requests.post(url, json=payload, headers=headers, timeout=20)
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    data = response.json()
                    text_out = data["choices"][0]["message"]["content"]

                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt.split()) * 2)
                    comp_tokens = usage.get("completion_tokens", len(text_out.split()) * 2)

                    cost = self._calculate_cost(model, prompt_tokens, comp_tokens)
                    self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                    logger.debug(f"Groq response received ({model}): {prompt_tokens} prompt / {comp_tokens} comp tokens (${cost:.5f})")
                    return text_out
                else:
                    self.circuit_breaker.record_failure()
                    last_error = f"Groq HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Groq API returned {response.status_code}. Backing off and rotating key...")
                    time.sleep(random.uniform(0.3, 0.8))
                    self._groq_key_idx = (self._groq_key_idx + 1) % len(self.groq_keys)
            except Exception as e:
                self.circuit_breaker.record_failure()
                last_error = str(e)
                logger.warning(f"Groq request exception on key #{self._groq_key_idx}: {e}")
                self._groq_key_idx = (self._groq_key_idx + 1) % len(self.groq_keys)

        raise RuntimeError(f"All Groq keys failed. Last error: {last_error}")

    def _call_openai(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "gpt-4o",
        temperature: float = 0.1
    ) -> str:
        """Call OpenAI API with key rotation."""
        if not self.openai_keys:
            raise ValueError("No OpenAI API keys configured in .env.")

        last_error = None
        for _ in range(len(self.openai_keys)):
            current_key = self.openai_keys[self._openai_key_idx]
            url = "https://api.openai.com/v1/chat/completions"
            logger.debug(f"Invoking OpenAI API: model={model}, key_index={self._openai_key_idx}")

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
                response = requests.post(url, json=payload, headers=headers, timeout=25)
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    data = response.json()
                    text_out = data["choices"][0]["message"]["content"]

                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", len(prompt.split()) * 2)
                    comp_tokens = usage.get("completion_tokens", len(text_out.split()) * 2)

                    cost = self._calculate_cost(model, prompt_tokens, comp_tokens)
                    self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                    logger.debug(f"OpenAI response received ({model}): {prompt_tokens} prompt / {comp_tokens} comp tokens (${cost:.5f})")
                    return text_out
                else:
                    self.circuit_breaker.record_failure()
                    last_error = f"OpenAI HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"OpenAI API returned {response.status_code}. Rotating key...")
                    self._openai_key_idx = (self._openai_key_idx + 1) % len(self.openai_keys)
            except Exception as e:
                self.circuit_breaker.record_failure()
                last_error = str(e)
                logger.warning(f"OpenAI request exception on key #{self._openai_key_idx}: {e}")
                self._openai_key_idx = (self._openai_key_idx + 1) % len(self.openai_keys)

        raise RuntimeError(f"All OpenAI keys failed. Last error: {last_error}")

    def _call_anthropic(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.1
    ) -> str:
        """Call Anthropic API with key rotation."""
        if not self.anthropic_keys:
            raise ValueError("No Anthropic API keys configured in .env.")

        last_error = None
        for _ in range(len(self.anthropic_keys)):
            current_key = self.anthropic_keys[self._anthropic_key_idx]
            url = "https://api.anthropic.com/v1/messages"
            logger.debug(f"Invoking Anthropic API: model={model}, key_index={self._anthropic_key_idx}")

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": temperature
            }
            if system_instruction:
                payload["system"] = system_instruction

            headers = {
                "x-api-key": current_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    self.circuit_breaker.record_success()
                    data = response.json()
                    text_out = data["content"][0]["text"]

                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("input_tokens", len(prompt.split()) * 2)
                    comp_tokens = usage.get("output_tokens", len(text_out.split()) * 2)

                    cost = self._calculate_cost(model, prompt_tokens, comp_tokens)
                    self.tracker.add_usage(prompt_tokens, comp_tokens, cost)
                    logger.debug(f"Anthropic response received ({model}): {prompt_tokens} prompt / {comp_tokens} comp tokens (${cost:.5f})")
                    return text_out
                else:
                    self.circuit_breaker.record_failure()
                    last_error = f"Anthropic HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Anthropic API returned {response.status_code}. Rotating key...")
                    self._anthropic_key_idx = (self._anthropic_key_idx + 1) % len(self.anthropic_keys)
            except Exception as e:
                self.circuit_breaker.record_failure()
                last_error = str(e)
                logger.warning(f"Anthropic request exception on key #{self._anthropic_key_idx}: {e}")
                self._anthropic_key_idx = (self._anthropic_key_idx + 1) % len(self.anthropic_keys)

        raise RuntimeError(f"All Anthropic keys failed. Last error: {last_error}")

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate USD cost for a single invocation based on token counts."""
        pricing = MODEL_PRICING.get(model, {"input_per_m": 0.075, "output_per_m": 0.30})
        cost = (prompt_tokens / 1_000_000 * pricing["input_per_m"]) + (
            completion_tokens / 1_000_000 * pricing["output_per_m"]
        )
        return round(cost, 6)

    def extract_json(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON object from LLM response with robust fallback."""
        # 1. Direct parse
        try:
            return json.loads(text.strip())
        except Exception:
            pass

        # 2. Markdown fenced block
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # 3. Substring between outermost { and }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        # 4. Field-by-field regex fallback for code snippets with unescaped quotes
        extracted = {}
        for key in ["target_file", "original_snippet", "replacement_snippet", "confidence_score", "rationale", "hypothesis", "root_cause_file", "root_cause_symbol", "explanation", "proposed_strategy"]:
            key_pattern = rf'"{key}"\s*:\s*(?:"(.*?)(?:"\s*,\s*"\w+"|\s*"\s*}}|\s*}})|([0-9.]+)|"(.*?)"\s*(?:,|\n|}}))'
            m = re.search(key_pattern, text, re.DOTALL)
            if m:
                val = m.group(1) or m.group(2) or m.group(3)
                if val:
                    if key == "confidence_score":
                        try:
                            extracted[key] = float(val)
                        except ValueError:
                            extracted[key] = 0.95
                    else:
                        extracted[key] = val.replace("\\n", "\n").replace('\\"', '"')

        if extracted.get("target_file") and (extracted.get("original_snippet") or extracted.get("hypothesis")):
            extracted.setdefault("confidence_score", 0.95)
            extracted.setdefault("rationale", "Extracted via robust parser")
            return extracted

        raise ValueError(f"Could not parse valid JSON from model response: {text[:200]}...")
