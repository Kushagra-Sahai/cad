from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import UploadFile
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.schemas.medicine import MedicineAnalysis
from app.services.drug_lookup_service import DrugLookupService, candidate_similarity
from app.services.llm_service import LLMService
from app.services.ocr_service import OCRService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class AnalysisEngine:
    def __init__(self, settings: Settings, db: AsyncIOMotorDatabase | None) -> None:
        self.settings = settings
        self.db = db
        self.ocr_service = OCRService(settings)
        self.drug_lookup_service = DrugLookupService(settings, db)
        self.rag_service = RAGService()
        self.llm_service = LLMService(settings)

    async def analyze_text(self, query: str, source: str = "text") -> MedicineAnalysis:
        lookup = await self.drug_lookup_service.lookup_medicine(query)
        confidence = self._confidence_score(query, lookup)
        context = await self.rag_service.retrieve_context(query, lookup)
        analysis = await self.llm_service.generate_analysis(query, lookup, context, confidence)
        await self._log_query(query=query, source=source, analysis=analysis, lookup=lookup)
        return analysis

    async def analyze_image(self, file: UploadFile) -> MedicineAnalysis:
        ocr_result = await self.ocr_service.extract_medicine_candidates(file)
        if not ocr_result.candidates:
            analysis = MedicineAnalysis(
                usage_guidance=(
                    "No readable medicine name was detected in the image. "
                    "Try a clearer photo of the front label or package name."
                ),
                timing_guidance="Timing guidance is unavailable until the medicine is identified.",
                confidence_score=0.0,
            )
            await self._log_query(
                query=ocr_result.cleaned_text,
                source="image",
                analysis=analysis,
                lookup={"found": False, "ocr_raw_text": ocr_result.raw_text},
            )
            return analysis

        best: MedicineAnalysis | None = None
        for candidate in ocr_result.candidates[:3]:
            result = await self.analyze_text(candidate, source="image")
            if best is None or result.confidence_score > best.confidence_score:
                best = result
            if result.confidence_score >= 0.72:
                break

        return best or MedicineAnalysis(confidence_score=0.0)

    def _confidence_score(self, query: str, lookup: dict[str, Any]) -> float:
        if not lookup.get("found"):
            return 0.1

        score = 0.25
        rxnorm = lookup.get("rxnorm", {})
        openfda = lookup.get("openfda", {})

        if rxnorm.get("found"):
            score += min(float(rxnorm.get("score", 0)) / 100, 1.0) * 0.35
        if openfda.get("found"):
            score += 0.28
        if lookup.get("local_dataset", {}).get("found"):
            best_match = max(
                lookup["local_dataset"].get("matches", []),
                key=lambda item: float(item.get("match_score") or 0.0),
                default={},
            )
            score += float(best_match.get("match_score") or 0.0) * 0.18

        identity = lookup.get("brand_name") or lookup.get("generic_name") or rxnorm.get("display_name", "")
        if identity:
            score += candidate_similarity(query, identity) * 0.12

        return round(min(score, 0.96), 2)

    async def _log_query(
        self,
        query: str,
        source: str,
        analysis: MedicineAnalysis,
        lookup: dict[str, Any],
    ) -> None:
        if self.db is None:
            return
        try:
            await self.db.queries.insert_one(
                {
                    "query": query,
                    "source": source,
                    "analysis": analysis.model_dump(),
                    "found": lookup.get("found", False),
                    "created_at": datetime.now(timezone.utc),
                }
            )
        except Exception as exc:
            logger.warning("Failed to write query log: %s", exc)
