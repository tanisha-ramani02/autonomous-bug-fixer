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

    # Gemini Keys
    google_api_key1: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY1")
    google_api_key2: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY2")
    google_api_key3: Optional[str] = Field(default=None, validation_alias="GOOGLE_API_KEY3")

    # Groq Keys
    groq_api_key1: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY1")
    groq_api_key2: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY2")
    groq_api_key3: Optional[str] = Field(default=None, validation_alias="GROQ_API_KEY3")

    # Model Names
    gemini_model1: str = Field(default="gemini-flash-latest", validation_alias="GEMINI_MODEL1")
    gemini_model2: str = Field(default="gemini-2.5-flash", validation_alias="GEMINI_MODEL2")

    groq_model1: str = Field(default="llama-3.3-70b-versatile", validation_alias="GROQ_MODEL1")
    groq_model2: str = Field(default="llama-3.1-8b-instant", validation_alias="GROQ_MODEL2")

    # Primary Provider & Execution Limits
    primary_provider: str = Field(default="gemini", validation_alias="PRIMARY_PROVIDER")
    max_attempts_per_bug: int = Field(default=3, validation_alias="MAX_ATTEMPTS_PER_BUG")
    max_cost_budget_usd: float = Field(default=5.00, validation_alias="MAX_COST_BUDGET_USD")
    subprocess_timeout_seconds: int = Field(default=30, validation_alias="SUBPROCESS_TIMEOUT_SECONDS")
    auto_git_rollback: bool = Field(default=True, validation_alias="AUTO_GIT_ROLLBACK")

    def get_gemini_keys(self) -> List[str]:
        """Return all non-empty Gemini keys."""
        keys = []
        for k in [self.google_api_key1, self.google_api_key2, self.google_api_key3]:
            if k and k.strip():
                keys.append(k.strip())
        return keys

    def get_groq_keys(self) -> List[str]:
        """Return all non-empty Groq keys."""
        keys = []
        for k in [self.groq_api_key1, self.groq_api_key2, self.groq_api_key3]:
            if k and k.strip():
                keys.append(k.strip())
        return keys


# Global settings instance
settings = Settings()
