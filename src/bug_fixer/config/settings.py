"""Configuration and Settings for Autonomous Bug Fixer Agent."""
import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Provider Chain Order (e.g. "gemini,groq,openai,anthropic")
    provider_chain: str = Field(default="gemini,groq,openai,anthropic", validation_alias="PROVIDER_CHAIN")
    primary_provider: str = Field(default="gemini", validation_alias="PRIMARY_PROVIDER")

    # Gemini Keys (Supports individual keys, comma-separated lists, and standard aliases)
    gemini_api_keys: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEYS")
    google_api_key1: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY1")
    google_api_key2: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY2")
    google_api_key3: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY3")
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")

    # Groq Keys
    groq_api_keys: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEYS")
    groq_api_key1: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY1")
    groq_api_key2: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY2")
    groq_api_key3: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY3")
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY")

    # OpenAI Keys
    openai_api_keys: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEYS")
    openai_api_key: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_api_key1: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY1")

    # Anthropic Keys
    anthropic_api_keys: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEYS")
    anthropic_api_key: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_api_key1: Optional[str] = Field(default=None, validation_alias="ANTHROPIC_API_KEY1")

    # Model Selection
    gemini_model1: str = Field(default="gemini-flash-latest", validation_alias="GEMINI_MODEL1")
    gemini_model2: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL2")

    groq_model1: str = Field(default="openai/gpt-oss-120b", validation_alias="GROQ_MODEL1")
    groq_model2: str = Field(default="openai/gpt-oss-20b", validation_alias="GROQ_MODEL2")

    openai_model1: str = Field(default="gpt-4o", validation_alias="OPENAI_MODEL1")
    openai_model2: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL2")

    anthropic_model1: str = Field(default="claude-3-5-sonnet-20241022", validation_alias="ANTHROPIC_MODEL1")
    anthropic_model2: str = Field(default="claude-3-5-haiku-20241022", validation_alias="ANTHROPIC_MODEL2")

    # Safety & Execution Limits
    max_attempts_per_bug: int = Field(default=3, validation_alias="MAX_ATTEMPTS_PER_BUG")
    max_cost_budget_usd: float = Field(default=5.00, validation_alias="MAX_COST_BUDGET_USD")
    subprocess_timeout_seconds: int = Field(default=30, validation_alias="SUBPROCESS_TIMEOUT_SECONDS")
    auto_git_rollback: bool = Field(default=True, validation_alias="AUTO_GIT_ROLLBACK")

    def get_provider_chain(self) -> List[str]:
        """Return the ordered list of providers to try."""
        return [p.strip().lower() for p in self.provider_chain.split(",") if p.strip()]

    def get_gemini_keys(self) -> List[str]:
        """Return all non-empty Gemini keys in sequence."""
        keys = []
        if self.gemini_api_keys:
            keys.extend([k.strip() for k in self.gemini_api_keys.split(",") if k.strip()])
        for k in [self.google_api_key1, self.gemini_api_key, self.google_api_key2, self.google_api_key3]:
            if k and k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        return keys

    def get_groq_keys(self) -> List[str]:
        """Return all non-empty Groq keys in sequence."""
        keys = []
        if self.groq_api_keys:
            keys.extend([k.strip() for k in self.groq_api_keys.split(",") if k.strip()])
        for k in [self.groq_api_key1, self.groq_api_key, self.groq_api_key2, self.groq_api_key3]:
            if k and k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        return keys

    def get_openai_keys(self) -> List[str]:
        """Return all non-empty OpenAI keys in sequence."""
        keys = []
        if self.openai_api_keys:
            keys.extend([k.strip() for k in self.openai_api_keys.split(",") if k.strip()])
        for k in [self.openai_api_key, self.openai_api_key1]:
            if k and k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        return keys

    def get_anthropic_keys(self) -> List[str]:
        """Return all non-empty Anthropic keys in sequence."""
        keys = []
        if self.anthropic_api_keys:
            keys.extend([k.strip() for k in self.anthropic_api_keys.split(",") if k.strip()])
        for k in [self.anthropic_api_key, self.anthropic_api_key1]:
            if k and k.strip() and k.strip() not in keys:
                keys.append(k.strip())
        return keys


# Global settings instance
settings = Settings()
