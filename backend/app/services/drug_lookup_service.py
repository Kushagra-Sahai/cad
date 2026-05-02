from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase
from rapidfuzz import fuzz

from app.core.config import Settings

logger = logging.getLogger(__name__)
CACHE_VERSION = 5

FORM_AND_PACKAGING_WORDS = {
    "tablet",
    "tablets",
    "tab",
    "tabs",
    "capsule",
    "capsules",
    "cap",
    "caps",
    "syrup",
    "injection",
    "cream",
    "ointment",
    "drops",
    "solution",
    "suspension",
    "gel",
    "spray",
    "patch",
    "strip",
    "bottle",
    "pack",
    "medicine",
}


class DrugLookupService:
    def __init__(self, settings: Settings, db: AsyncIOMotorDatabase | None) -> None:
        self.settings = settings
        self.db = db
        self.timeout = httpx.Timeout(settings.http_timeout_seconds)
        from app.services.local_medicine_dataset_service import LocalMedicineDatasetService

        self.local_dataset_service = LocalMedicineDatasetService(settings)

    async def lookup_medicine(self, query: str) -> dict[str, Any]:
        normalized = normalize_drug_name(query)
        if not normalized:
            return self._empty_result(query, normalized)

        cached = await self._get_cached(normalized)
        if cached and cached.get("cache_version") == CACHE_VERSION:
            cached["from_cache"] = True
            return cached

        local_dataset = self.local_dataset_service.search(query)
        rxnorm = await self._lookup_rxnorm(normalized)
        terms = self._build_search_terms(query, normalized, rxnorm, local_dataset)
        openfda = await self._lookup_openfda(terms)
        local_best = _best_local_dataset_match(local_dataset)

        brand_name = self._first_non_empty(
            local_best.get("brand_name"),
            openfda.get("brand_name"),
            rxnorm.get("brand_name"),
            rxnorm.get("display_name"),
        )
        generic_name = self._first_non_empty(
            local_best.get("generic_name"),
            openfda.get("generic_name"),
            rxnorm.get("generic_name"),
            rxnorm.get("ingredient_name"),
        )

        result = {
            "cache_version": CACHE_VERSION,
            "query": query,
            "normalized_name": normalized,
            "found": bool(rxnorm.get("found") or openfda.get("found") or local_dataset.get("found")),
            "brand_name": brand_name,
            "generic_name": generic_name,
            "local_dataset": local_dataset,
            "rxnorm": rxnorm,
            "openfda": openfda,
            "from_cache": False,
            "source_urls": {
                "rxnorm": self.settings.rxnorm_base_url,
                "openfda": self.settings.openfda_base_url,
                "kaggle_dataset": "https://www.kaggle.com/datasets/shudhanshusingh/az-medicine-dataset-of-india",
            },
        }
        await self._cache_result(normalized, result)
        return result

    async def _get_cached(self, normalized: str) -> dict[str, Any] | None:
        if self.db is None:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.drug_cache_ttl_days)
        doc = await self.db.medicine_cache.find_one(
            {"normalized_name": normalized, "updated_at": {"$gte": cutoff}},
            {"_id": False},
        )
        if not doc:
            return None
        return doc.get("payload")

    async def _cache_result(self, normalized: str, payload: dict[str, Any]) -> None:
        if self.db is None:
            return
        await self.db.medicine_cache.update_one(
            {"normalized_name": normalized},
            {
                "$set": {
                    "normalized_name": normalized,
                    "payload": payload,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def _lookup_rxnorm(self, normalized: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                approximate = await client.get(
                    f"{self.settings.rxnorm_base_url}/REST/approximateTerm.json",
                    params={"term": normalized, "maxEntries": 5},
                )
                approximate.raise_for_status()
                candidates = _parse_rxnorm_candidates(approximate.json())
                if not candidates:
                    return {"found": False, "candidates": []}

                best = candidates[0]
                related = await client.get(
                    f"{self.settings.rxnorm_base_url}/REST/rxcui/{best['rxcui']}/allrelated.json",
                )
                related.raise_for_status()
                related_concepts = _parse_related_concepts(related.json())

                generic = _best_related_name(related_concepts, {"IN", "MIN", "PIN"})
                brand = _best_related_name(related_concepts, {"BN", "SBD", "SBDC"})

                return {
                    "found": True,
                    "rxcui": best.get("rxcui", ""),
                    "display_name": best.get("name", ""),
                    "score": best.get("score", 0),
                    "generic_name": generic,
                    "brand_name": brand,
                    "ingredient_name": generic,
                    "candidates": candidates,
                    "related_concepts": related_concepts[:25],
                }
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.warning("RxNorm lookup failed: %s", exc)
        except Exception as exc:
            logger.warning("RxNorm lookup failed: %s", exc)
        return {"found": False, "candidates": []}

    async def _lookup_openfda(self, terms: list[str]) -> dict[str, Any]:
        labels: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for term in terms[:6]:
                for field in ("openfda.brand_name", "openfda.generic_name", "openfda.substance_name"):
                    query = f'{field}:"{_escape_openfda_term(term)}"'
                    try:
                        response = await client.get(
                            f"{self.settings.openfda_base_url}/drug/label.json",
                            params={"search": query, "limit": 3},
                        )
                        if response.status_code == 404:
                            continue
                        response.raise_for_status()
                        for label in response.json().get("results", []):
                            label_id = label.get("id") or str(hash(str(label.get("openfda", {}))))
                            if label_id not in seen_ids:
                                seen_ids.add(label_id)
                                labels.append(label)
                    except Exception as exc:
                        logger.debug("OpenFDA query failed for %s: %s", query, exc)

                if labels:
                    break

        if not labels:
            return {"found": False, "labels": [], "label_summary": {}}

        summary = _summarize_openfda_labels(labels)
        openfda = labels[0].get("openfda", {})
        return {
            "found": True,
            "brand_name": _first_openfda_value(openfda, "brand_name"),
            "generic_name": _first_openfda_value(openfda, "generic_name"),
            "manufacturer_name": _first_openfda_value(openfda, "manufacturer_name"),
            "substance_name": _first_openfda_value(openfda, "substance_name"),
            "drug_class": _first_openfda_value(openfda, "pharm_class_epc")
            or _first_openfda_value(openfda, "pharm_class_cs")
            or _first_openfda_value(openfda, "pharm_class_moa"),
            "labels": labels[:3],
            "label_summary": summary,
        }

    def _build_search_terms(
        self,
        query: str,
        normalized: str,
        rxnorm: dict[str, Any],
        local_dataset: dict[str, Any],
    ) -> list[str]:
        terms = [
            query.strip(),
            normalized,
            rxnorm.get("brand_name", ""),
            rxnorm.get("generic_name", ""),
            rxnorm.get("display_name", ""),
        ]
        terms.extend(candidate.get("name", "") for candidate in rxnorm.get("candidates", [])[:3])
        for match in local_dataset.get("matches", [])[:3]:
            terms.extend(
                [
                    match.get("brand_name", ""),
                    match.get("generic_name", ""),
                ]
            )
        cleaned: list[str] = []
        seen: set[str] = set()
        for term in terms:
            value = normalize_drug_name(term)
            if value and value not in seen:
                seen.add(value)
                cleaned.append(value)
        return cleaned

    @staticmethod
    def _first_non_empty(*values: object) -> str:
        for value in values:
            if isinstance(value, list) and value:
                return str(value[0]).strip()
            if value:
                return str(value).strip()
        return ""

    @staticmethod
    def _empty_result(query: str, normalized: str) -> dict[str, Any]:
        return {
            "query": query,
            "normalized_name": normalized,
            "found": False,
            "brand_name": "",
            "generic_name": "",
            "local_dataset": {"found": False, "matches": [], "source": "local_dataset"},
            "rxnorm": {"found": False, "candidates": []},
            "openfda": {"found": False, "labels": [], "label_summary": {}},
            "from_cache": False,
            "source_urls": {},
        }


def normalize_drug_name(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu|%)\b", " ", value, flags=re.I)
    value = re.sub(r"[^a-z0-9\s\-+]", " ", value)
    tokens = [token for token in value.split() if token not in FORM_AND_PACKAGING_WORDS]
    return re.sub(r"\s+", " ", " ".join(tokens)).strip()


def _parse_rxnorm_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for item in payload.get("approximateGroup", {}).get("candidate", []):
        candidates.append(
            {
                "rxcui": item.get("rxcui", ""),
                "name": item.get("name", ""),
                "score": int(item.get("score") or 0),
                "rank": int(item.get("rank") or 0),
            }
        )
    candidates.sort(key=lambda item: (item["score"], -item["rank"]), reverse=True)
    return candidates


def _best_local_dataset_match(local_dataset: dict[str, Any]) -> dict[str, Any]:
    matches = local_dataset.get("matches") or []
    if not matches:
        return {}
    return max(matches, key=lambda item: float(item.get("match_score") or 0.0))


def _parse_related_concepts(payload: dict[str, Any]) -> list[dict[str, str]]:
    concepts: list[dict[str, str]] = []
    groups = payload.get("allRelatedGroup", {}).get("conceptGroup", [])
    for group in groups:
        tty = group.get("tty", "")
        for concept in group.get("conceptProperties", []) or []:
            concepts.append(
                {
                    "rxcui": concept.get("rxcui", ""),
                    "name": concept.get("name", ""),
                    "tty": concept.get("tty", tty),
                    "synonym": concept.get("synonym", ""),
                }
            )
    return concepts


def _best_related_name(concepts: list[dict[str, str]], tty_values: set[str]) -> str:
    for concept in concepts:
        if concept.get("tty") in tty_values and concept.get("name"):
            return concept["name"]
    return ""


def _escape_openfda_term(value: str) -> str:
    return value.replace('"', "").strip()


def _first_openfda_value(openfda: dict[str, Any], key: str) -> str:
    values = openfda.get(key) or []
    if isinstance(values, list) and values:
        return str(values[0]).strip()
    if isinstance(values, str):
        return values.strip()
    return ""


def _summarize_openfda_labels(labels: list[dict[str, Any]]) -> dict[str, list[str]]:
    fields = {
        "indications": ["indications_and_usage", "purpose"],
        "usage_guidance": ["spl_product_data_elements"],
        "side_effects": ["adverse_reactions"],
        "warnings_precautions": [
            "boxed_warning",
            "warnings",
            "warnings_and_cautions",
            "do_not_use",
            "ask_doctor",
            "ask_doctor_or_pharmacist",
        ],
        "interactions_basic": ["drug_interactions"],
        "drug_class": [],
    }
    summary: dict[str, list[str]] = {key: [] for key in fields}
    for label in labels:
        for output_key, source_fields in fields.items():
            for source_field in source_fields:
                for text in _as_text_list(label.get(source_field)):
                    simplified = simplify_medical_text(text)
                    if simplified and simplified not in summary[output_key]:
                        summary[output_key].append(simplified)

        openfda = label.get("openfda", {})
        for class_key in ("pharm_class_epc", "pharm_class_cs", "pharm_class_moa"):
            class_name = _first_openfda_value(openfda, class_key)
            if class_name and class_name not in summary["drug_class"]:
                summary["drug_class"].append(class_name)

    return {key: values[:6] for key, values in summary.items()}


def _as_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def simplify_medical_text(text: str, max_chars: int = 420) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu)\b", "[dose amount]", text, flags=re.I)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = " ".join(sentences[:2]).strip() if sentences else text
    if len(selected) > max_chars:
        selected = selected[: max_chars - 1].rsplit(" ", 1)[0] + "."
    return selected


def candidate_similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize_drug_name(a), normalize_drug_name(b)) / 100
