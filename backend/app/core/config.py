from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MediScan AI"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    mongo_uri: str = Field(default="mongodb://localhost:27017/mediscan", alias="MONGO_URI")
    mongo_db_name: str = Field(default="mediscan", alias="MONGO_DB_NAME")

    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    openfda_base_url: str = Field(default="https://api.fda.gov", alias="OPENFDA_BASE_URL")
    rxnorm_base_url: str = Field(
        default="https://rxnav.nlm.nih.gov",
        alias="RXNORM_BASE_URL",
    )
    drug_cache_ttl_days: int = Field(default=30, alias="DRUG_CACHE_TTL_DAYS")
    medicine_dataset_path: str | None = Field(default=None, alias="MEDICINE_DATASET_PATH")
    medicine_dataset_dir: str | None = Field(default="/app/data", alias="MEDICINE_DATASET_DIR")
    medicine_dataset_glob: str = Field(
        default="*.csv,*.xlsx,*.xls,*.parquet,*.pq,*.json,*.jsonl",
        alias="MEDICINE_DATASET_GLOB",
    )
    enable_kaggle_dataset: bool = Field(default=False, alias="ENABLE_KAGGLE_DATASET")
    kaggle_dataset_ref: str = Field(
        default="shudhanshusingh/az-medicine-dataset-of-india",
        alias="KAGGLE_DATASET_REF",
    )
    kaggle_dataset_file: str | None = Field(default=None, alias="KAGGLE_DATASET_FILE")
    medicine_dataset_min_score: int = Field(default=82, alias="MEDICINE_DATASET_MIN_SCORE")

    llm_provider: Literal["ollama", "none"] = Field(
        default="ollama",
        alias="LLM_PROVIDER",
    )
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")

    watson_tts_api_key: str | None = Field(default=None, alias="WATSON_TTS_API_KEY")
    watson_tts_url: str | None = Field(default=None, alias="WATSON_TTS_URL")
    watson_tts_voice: str = Field(
        default="en-US_AllisonV3Voice",
        alias="WATSON_TTS_VOICE",
    )
    watson_stt_api_key: str | None = Field(default=None, alias="WATSON_STT_API_KEY")
    watson_stt_url: str | None = Field(default=None, alias="WATSON_STT_URL")
    watson_stt_model: str = Field(
        default="en-US_BroadbandModel",
        alias="WATSON_STT_MODEL",
    )

    tesseract_cmd: str | None = Field(default=None, alias="TESSERACT_CMD")

    vector_backend: Literal["faiss"] = Field(default="faiss", alias="VECTOR_BACKEND")
    rate_limit_requests: int = Field(default=90, alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(
        default=60,
        alias="RATE_LIMIT_WINDOW_SECONDS",
    )
    http_timeout_seconds: float = Field(default=12.0, alias="HTTP_TIMEOUT_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
