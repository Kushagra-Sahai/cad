from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.medicine import DISCLAIMER, MedicineAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MediScan AI, a cautious medicine information assistant.
Use only the supplied retrieved context and lookup data.
Do not prescribe medication. Do not provide exact dosage amounts. Do not invent facts.
If the medicine is unknown or evidence is weak, leave unknown fields blank and explain uncertainty.
Return only valid JSON matching the required schema."""


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate_analysis(
        self,
        query: str,
        lookup: dict[str, Any],
        retrieved_context: str,
        confidence_score: float,
    ) -> MedicineAnalysis:
        prompt = self._build_prompt(query, lookup, retrieved_context, confidence_score)

        if self.settings.llm_provider == "ollama":
            try:
                content = await self._call_ollama(prompt)
                return self._parse_or_fallback(content, query, lookup, confidence_score)
            except Exception as exc:
                logger.warning("Ollama analysis failed, using deterministic fallback: %s", exc)

        return self._fallback_analysis(query, lookup, confidence_score)

    async def _call_ollama(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("message", {}).get("content", "{}")

    def _parse_or_fallback(
        self,
        content: str,
        query: str,
        lookup: dict[str, Any],
        confidence_score: float,
    ) -> MedicineAnalysis:
        try:
            data = _extract_json(content)
            data["confidence_score"] = _bounded_confidence(
                float(data.get("confidence_score") or confidence_score)
            )
            data["disclaimer"] = DISCLAIMER
            return MedicineAnalysis.model_validate(_sanitize_no_dosage(data))
        except (ValueError, TypeError, ValidationError) as exc:
            logger.warning("Could not parse LLM JSON, using fallback: %s", exc)
            return self._fallback_analysis(query, lookup, confidence_score)

    def _fallback_analysis(
        self,
        query: str,
        lookup: dict[str, Any],
        confidence_score: float,
    ) -> MedicineAnalysis:
        openfda = lookup.get("openfda", {})
        summary = openfda.get("label_summary", {})
        found = lookup.get("found", False)

        brand = lookup.get("brand_name") or (query if found else "")
        generic = lookup.get("generic_name") or ""
        drug_class = _first(summary.get("drug_class")) or openfda.get("drug_class", "")
        local_best = _best_local_match(lookup)
        if local_best:
            drug_class = drug_class or local_best.get("drug_class", "")

        if found:
            usage = (
                "Use this medicine only as directed on its approved label or by a qualified clinician. "
                "This summary avoids exact dosage instructions."
            )
            timing = (
                "Follow the product label or clinician guidance for timing. "
                "Ask a pharmacist or doctor if instructions are unclear."
            )
        else:
            usage = (
                "I could not reliably identify this medicine from trusted drug databases. "
                "Do not use an unknown medicine; ask a pharmacist or doctor to verify it."
            )
            timing = "Timing guidance is unavailable until the medicine is identified."

        alternatives = []
        if generic and brand and generic.lower() != brand.lower():
            alternatives.append(generic)

        indications = _safe_values(summary.get("indications")) or _safe_values(local_best.get("indications") if local_best else [])
        why_used = _safe_values(local_best.get("why_used") if local_best else []) or indications

        return MedicineAnalysis(
            brand_name=brand,
            generic_name=generic,
            drug_class=drug_class,
            indications=indications,
            why_used=why_used,
            usage_guidance=usage,
            timing_guidance=timing,
            side_effects=_safe_values(summary.get("side_effects")) or _safe_values(local_best.get("side_effects") if local_best else []),
            warnings_precautions=_safe_values(summary.get("warnings_precautions"))
            or _safe_values(local_best.get("warnings_precautions") if local_best else []),
            interactions_basic=_safe_values(summary.get("interactions_basic"))
            or _safe_values(local_best.get("interactions_basic") if local_best else []),
            alternatives_generic=alternatives,
            confidence_score=_bounded_confidence(confidence_score if found else min(confidence_score, 0.25)),
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _build_prompt(
        query: str,
        lookup: dict[str, Any],
        retrieved_context: str,
        confidence_score: float,
    ) -> str:
        compact_lookup = {
            "query": query,
            "found": lookup.get("found", False),
            "brand_name": lookup.get("brand_name", ""),
            "generic_name": lookup.get("generic_name", ""),
            "rxnorm": {
                "rxcui": lookup.get("rxnorm", {}).get("rxcui", ""),
                "display_name": lookup.get("rxnorm", {}).get("display_name", ""),
                "score": lookup.get("rxnorm", {}).get("score", 0),
            },
            "openfda": {
                "drug_class": lookup.get("openfda", {}).get("drug_class", ""),
                "label_summary": lookup.get("openfda", {}).get("label_summary", {}),
            },
            "local_dataset": {
                "found": lookup.get("local_dataset", {}).get("found", False),
                "matches": lookup.get("local_dataset", {}).get("matches", [])[:3],
            },
            "confidence_score": confidence_score,
        }
        return f"""
Required JSON schema:
{{
  "brand_name": "",
  "generic_name": "",
  "drug_class": "",
  "indications": [],
  "why_used": [],
  "usage_guidance": "",
  "timing_guidance": "",
  "side_effects": [],
  "warnings_precautions": [],
  "interactions_basic": [],
  "alternatives_generic": [],
  "confidence_score": 0.0,
  "disclaimer": "{DISCLAIMER}"
}}

User medicine query:
{query}

Lookup data:
{json.dumps(compact_lookup, ensure_ascii=True)}

Retrieved context:
{retrieved_context or "No trusted context was retrieved."}
"""


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("{"):
        return json.loads(content)
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found")
    return json.loads(match.group(0))


def _sanitize_no_dosage(data: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = _mask_dosage(value)
        elif isinstance(value, list):
            data[key] = [_mask_dosage(str(item)) for item in value]
    return data


def _mask_dosage(text: str) -> str:
    return re.sub(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu)\b", "[dose amount]", text, flags=re.I)


def _safe_values(values: object, limit: int = 5) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    safe = [_mask_dosage(str(value).strip()) for value in values if str(value).strip()]
    return safe[:limit]


def _first(values: object) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    if isinstance(values, str):
        return values
    return ""


def _best_local_match(lookup: dict[str, Any]) -> dict[str, Any]:
    matches = lookup.get("local_dataset", {}).get("matches") or []
    if not matches:
        return {}
    return max(matches, key=lambda item: float(item.get("match_score") or 0.0))


def _bounded_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)
