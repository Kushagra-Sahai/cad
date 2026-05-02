from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


DISCLAIMER = "This is general medical information. Consult a qualified doctor before use."


class MedicineAnalysis(BaseModel):
    brand_name: str = ""
    generic_name: str = ""
    drug_class: str = ""
    indications: list[str] = Field(default_factory=list)
    why_used: list[str] = Field(default_factory=list)
    usage_guidance: str = ""
    timing_guidance: str = ""
    side_effects: list[str] = Field(default_factory=list)
    warnings_precautions: list[str] = Field(default_factory=list)
    interactions_basic: list[str] = Field(default_factory=list)
    alternatives_generic: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    disclaimer: str = DISCLAIMER

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "indications",
        "why_used",
        "side_effects",
        "warnings_precautions",
        "interactions_basic",
        "alternatives_generic",
        mode="before",
    )
    @classmethod
    def ensure_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @field_validator(
        "brand_name",
        "generic_name",
        "drug_class",
        "usage_guidance",
        "timing_guidance",
        "disclaimer",
        mode="before",
    )
    @classmethod
    def ensure_string(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class TextMedicineRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    include_audio: bool = False


class SpeechToTextResponse(BaseModel):
    transcript: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class HealthResponse(BaseModel):
    status: str
    app: str
    mongo: str
    llm_provider: str
