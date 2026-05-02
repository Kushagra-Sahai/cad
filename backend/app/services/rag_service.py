from __future__ import annotations

import hashlib
import logging
import math
from typing import Any

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

try:
    from langchain_core.embeddings import Embeddings
except Exception:  # pragma: no cover - used only if LangChain is absent.
    class Embeddings:  # type: ignore[no-redef]
        pass


class HashEmbeddings(Embeddings):
    """Deterministic local embeddings for FAISS when external embeddings are absent."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token.lower() for token in text.split() if token.strip()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class RAGService:
    def __init__(self) -> None:
        self.embeddings = HashEmbeddings()

    async def retrieve_context(self, query: str, lookup: dict[str, Any], top_k: int = 6) -> str:
        documents = self._build_documents(lookup)
        if not documents:
            return ""

        try:
            from langchain_community.vectorstores import FAISS

            vectorstore = FAISS.from_texts(
                [doc["text"] for doc in documents],
                embedding=self.embeddings,
                metadatas=[doc["metadata"] for doc in documents],
            )
            matches = vectorstore.similarity_search(query, k=min(top_k, len(documents)))
            return "\n\n".join(
                f"[{doc.metadata.get('section', 'source')}] {doc.page_content}"
                for doc in matches
            )
        except Exception as exc:
            logger.debug("FAISS retrieval unavailable, using lexical retrieval: %s", exc)
            return self._lexical_retrieve(query, documents, top_k)

    def _build_documents(self, lookup: dict[str, Any]) -> list[dict[str, Any]]:
        documents: list[dict[str, Any]] = []
        openfda = lookup.get("openfda", {})
        summary = openfda.get("label_summary", {})

        for section, values in summary.items():
            for value in values or []:
                documents.append(
                    {
                        "text": value,
                        "metadata": {
                            "section": section,
                            "source": "OpenFDA drug label",
                        },
                    }
                )

        rxnorm = lookup.get("rxnorm", {})
        for candidate in rxnorm.get("candidates", [])[:5]:
            name = candidate.get("name")
            rxcui = candidate.get("rxcui")
            if name:
                documents.append(
                    {
                        "text": f"RxNorm concept {name} with RxCUI {rxcui}.",
                        "metadata": {"section": "identity", "source": "RxNorm"},
                    }
                )

        if lookup.get("brand_name") or lookup.get("generic_name"):
            documents.append(
                {
                    "text": (
                        f"Identified brand name: {lookup.get('brand_name') or 'unknown'}. "
                        f"Identified generic name: {lookup.get('generic_name') or 'unknown'}."
                    ),
                    "metadata": {"section": "identity", "source": "Drug lookup"},
                }
            )

        for match in lookup.get("local_dataset", {}).get("matches", [])[:5]:
            documents.append(
                {
                    "text": (
                        f"Indian medicine dataset match: brand {match.get('brand_name') or 'unknown'}, "
                        f"composition {match.get('generic_name') or 'unknown'}, "
                        f"manufacturer {match.get('manufacturer_name') or 'unknown'}, "
                        f"type {match.get('medicine_type') or 'unknown'}, "
                        f"class {match.get('drug_class') or 'unknown'}, "
                        f"uses {'; '.join(match.get('indications') or []) or 'unknown'}, "
                        f"why used {'; '.join(match.get('why_used') or match.get('indications') or []) or 'unknown'}, "
                        f"side effects {'; '.join(match.get('side_effects') or []) or 'unknown'}, "
                        f"warnings {'; '.join(match.get('warnings_precautions') or []) or 'unknown'}, "
                        f"interactions {'; '.join(match.get('interactions_basic') or []) or 'unknown'}."
                    ),
                    "metadata": {
                        "section": "local_dataset",
                        "source": match.get("source", "Kaggle medicine dataset"),
                    },
                }
            )
        return documents

    @staticmethod
    def _lexical_retrieve(query: str, documents: list[dict[str, Any]], top_k: int) -> str:
        scored = [
            (fuzz.token_set_ratio(query, doc["text"]), doc)
            for doc in documents
        ]
        scored.sort(reverse=True, key=lambda item: item[0])
        return "\n\n".join(
            f"[{doc['metadata'].get('section', 'source')}] {doc['text']}"
            for _, doc in scored[:top_k]
        )
