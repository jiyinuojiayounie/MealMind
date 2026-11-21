from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEALMIND_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.1-flash-lite", validation_alias="GEMINI_MODEL")

    gemini_diagnostics: bool = False

    service_name: str = Field(default="mealmind-api", min_length=1)
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [
            AnyHttpUrl("http://localhost:5173"),
            AnyHttpUrl("http://127.0.0.1:5173"),
        ],
    )

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        for origin in origins:
            if (
                origin.path not in (None, "/")
                or origin.username is not None
                or origin.password is not None
                or origin.query is not None
                or origin.fragment is not None
                or "*" in str(origin)
            ):
                raise ValueError("CORS entries must be explicit HTTP or HTTPS origins")
        return origins
