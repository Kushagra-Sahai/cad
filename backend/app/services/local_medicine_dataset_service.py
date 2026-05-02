from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process

from app.core.config import Settings
from app.services.drug_lookup_service import normalize_drug_name

logger = logging.getLogger(__name__)

NAME_COLUMNS = ("name", "medicine_name", "drug_name", "brand_name", "product_name", "generic_name")
COMPOSITION_COLUMNS = (
    "short_composition1",
    "short_composition2",
    "composition",
    "salt_composition",
    "generic_name",
    "generic_name_calpol",
    "active_ingredient",
    "active_ingredients",
)
MANUFACTURER_COLUMNS = ("manufacturer_name", "manufacturer", "company", "marketer")
TYPE_COLUMNS = ("type", "dosage_form", "form")
PRICE_COLUMNS = ("price", "price_rs", "price_inr", "mrp")
DISCONTINUED_COLUMNS = ("is_discontinued", "discontinued")
INDICATION_COLUMNS = ("uses", "use", "indication", "indications", "purpose")
SIDE_EFFECT_COLUMNS = ("side_effects", "side_effect", "adverse_effects", "adverse_reactions")
WARNING_COLUMNS = (
    "warnings_precautions",
    "warnings",
    "precautions",
    "contraindications",
    "contraindication",
    "interaction_warnings_precautions",
)
INTERACTION_COLUMNS = (
    "interactions_basic",
    "drug_interactions",
    "interaction_warnings_precautions",
)
DRUG_CLASS_COLUMNS = ("drug_class", "therapeutic_class", "category", "group_name", "classification")
UNIT_SIZE_COLUMNS = ("unit_size", "pack_size_label", "pack_size", "package_size")
DATASET_SUFFIXES = {".csv", ".parquet", ".pq", ".xlsx", ".xls", ".json", ".jsonl"}


@dataclass(frozen=True)
class DatasetMedicineRecord:
    brand_name: str
    generic_name: str
    manufacturer_name: str = ""
    medicine_type: str = ""
    price: str = ""
    is_discontinued: str = ""
    drug_class: str = ""
    indications: list[str] | None = None
    why_used: list[str] | None = None
    side_effects: list[str] | None = None
    warnings_precautions: list[str] | None = None
    interactions_basic: list[str] | None = None
    unit_size: str = ""
    source: str = "Local medicine dataset"

    def as_dict(self, score: float) -> dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "generic_name": self.generic_name,
            "manufacturer_name": self.manufacturer_name,
            "medicine_type": self.medicine_type,
            "price": self.price,
            "is_discontinued": self.is_discontinued,
            "drug_class": self.drug_class,
            "indications": self.indications or [],
            "why_used": self.why_used or self.indications or [],
            "side_effects": self.side_effects or [],
            "warnings_precautions": self.warnings_precautions or [],
            "interactions_basic": self.interactions_basic or [],
            "unit_size": self.unit_size,
            "source": self.source,
            "match_score": round(score, 2),
        }


class LocalMedicineDatasetService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._loaded = False
        self._records: list[DatasetMedicineRecord] = []
        self._search_terms: list[str] = []
        self._brand_index: dict[str, list[int]] = {}

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        self._load_once()
        normalized = normalize_drug_name(query)
        if not normalized or not self._records:
            return {
                "found": False,
                "matches": [],
                "source": "local_dataset",
                "records_loaded": len(self._records),
                "files_loaded": [],
            }

        matches = process.extract(
            normalized,
            self._search_terms,
            scorer=fuzz.token_set_ratio,
            limit=max(limit * 5, 25),
        )

        output: list[dict[str, Any]] = []
        seen_groups: set[str] = set()
        for _, score, index in matches:
            if score < self.settings.medicine_dataset_min_score:
                continue
            record = self._records[index]
            group_key = normalize_drug_name(record.brand_name) or f"record:{index}"
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)

            group_indexes = self._brand_index.get(group_key, [index])
            group_records = [self._records[group_index] for group_index in group_indexes]
            output.append(_merge_record_group(group_records, score / 100).as_dict(score / 100))
            if len(output) >= limit:
                break

        return {
            "found": bool(output),
            "matches": output,
            "source": "local_dataset",
            "records_loaded": len(self._records),
            "files_loaded": sorted({record.source for record in self._records}),
        }

    def _load_once(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        paths = self._resolve_dataset_paths()
        if not paths:
            logger.info("No local medicine dataset configured.")
            return

        records: list[DatasetMedicineRecord] = []
        failures: list[str] = []
        for path in paths:
            try:
                dataframe = _read_tabular_file(path)
                records.extend(_records_from_dataframe(dataframe, source=path.name))
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
                logger.warning("Could not load medicine dataset from %s: %s", path, exc)

        if failures:
            logger.info("Skipped %s dataset file(s): %s", len(failures), "; ".join(failures[:5]))

        self._records = _deduplicate_records(records)
        self._search_terms = [
            normalize_drug_name(f"{record.brand_name} {record.generic_name}")
            for record in self._records
        ]
        self._brand_index = _build_brand_index(self._records)
        logger.info(
            "Loaded %s medicine dataset records from %s file(s)",
            len(self._records),
            len(paths),
        )

    def _resolve_dataset_paths(self) -> list[Path]:
        paths: list[Path] = []

        if self.settings.medicine_dataset_path:
            path = _resolve_local_path(Path(self.settings.medicine_dataset_path))
            if path.exists() and path.is_file():
                paths.append(path)
            elif path.exists() and path.is_dir():
                paths.extend(_tabular_files_from_directory(path, self.settings.medicine_dataset_glob))
            else:
                logger.warning("MEDICINE_DATASET_PATH does not exist: %s", path)

        if self.settings.medicine_dataset_dir:
            directory = _resolve_local_path(Path(self.settings.medicine_dataset_dir))
            if directory.exists() and directory.is_dir():
                paths.extend(_tabular_files_from_directory(directory, self.settings.medicine_dataset_glob))

        if self.settings.enable_kaggle_dataset:
            kaggle_path = self._resolve_kaggle_dataset_path()
            if kaggle_path:
                paths.append(kaggle_path)

        deduped: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                deduped.append(path)
        return deduped

    def _resolve_kaggle_dataset_path(self) -> Path | None:
        try:
            import kagglehub

            dataset_dir = Path(kagglehub.dataset_download(self.settings.kaggle_dataset_ref))
            if self.settings.kaggle_dataset_file:
                chosen = dataset_dir / self.settings.kaggle_dataset_file
                if chosen.exists():
                    return chosen
                logger.warning("KAGGLE_DATASET_FILE does not exist in download: %s", chosen)
            return _largest_tabular_file(dataset_dir)
        except Exception as exc:
            logger.warning("Kaggle dataset download failed: %s", exc)
            return None


def _read_tabular_file(path: Path):
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix in {".json", ".jsonl"}:
        return pd.json_normalize(_read_json_records(path))
    raise ValueError(f"Unsupported dataset file type: {suffix}")


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        records: list[Any] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                text = line.strip()
                if text:
                    records.append(json.loads(text))
    else:
        with path.open("r", encoding="utf-8") as file:
            records = _records_from_json_payload(json.load(file))

    normalized_records: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, dict):
            normalized_records.append(record)
        else:
            normalized_records.append({"value": record})
    return normalized_records


def _records_from_json_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("records", "data", "items", "medicines", "medicine", "products", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        if payload and all(isinstance(value, dict) for value in payload.values()):
            return list(payload.values())
        return [payload]
    raise ValueError("JSON dataset must contain an object, list, or JSONL records.")


def _records_from_dataframe(dataframe, source: str) -> list[DatasetMedicineRecord]:
    dataframe = dataframe.copy()
    dataframe.columns = [_canonical_column_name(column) for column in dataframe.columns]

    name_col = _first_existing_column(dataframe, NAME_COLUMNS)
    if not name_col:
        name_col = _first_column_with_prefix(dataframe, ("generic_name", "medicine", "drug", "product"))
    if not name_col:
        raise ValueError(f"No medicine name column found. Columns: {list(dataframe.columns)}")

    composition_cols = [column for column in COMPOSITION_COLUMNS if column in dataframe.columns and column != name_col]
    if not composition_cols:
        composition_cols = [
            column
            for column in dataframe.columns
            if column != name_col and any(column.startswith(prefix) for prefix in ("generic_name", "composition", "salt"))
        ]

    manufacturer_col = _first_existing_column(dataframe, MANUFACTURER_COLUMNS)
    type_col = _first_existing_column(dataframe, TYPE_COLUMNS)
    price_col = _first_existing_column(dataframe, PRICE_COLUMNS)
    discontinued_col = _first_existing_column(dataframe, DISCONTINUED_COLUMNS)
    indication_col = _first_existing_column(dataframe, INDICATION_COLUMNS)
    side_effect_col = _first_existing_column(dataframe, SIDE_EFFECT_COLUMNS)
    warning_cols = _existing_columns(dataframe, WARNING_COLUMNS)
    interaction_cols = _existing_columns(dataframe, INTERACTION_COLUMNS)
    drug_class_col = _first_existing_column(dataframe, DRUG_CLASS_COLUMNS)
    unit_size_col = _first_existing_column(dataframe, UNIT_SIZE_COLUMNS)

    records: list[DatasetMedicineRecord] = []
    for row in dataframe.to_dict("records"):
        brand = _clean_value(row.get(name_col))
        if not brand:
            continue

        generic_parts = [_clean_composition(row.get(column)) for column in composition_cols]
        generic = ", ".join(part for part in generic_parts if part)
        if not generic and name_col.startswith("generic_name"):
            generic = _clean_composition(brand)

        indications = _split_text_items(row.get(indication_col)) if indication_col else []
        side_effects = _split_text_items(row.get(side_effect_col)) if side_effect_col else []
        indication_like_side_effects = [item for item in side_effects if _looks_like_indication(item)]
        if indication_like_side_effects:
            indications = _unique_text_items([*indications, *indication_like_side_effects])
            side_effects = [item for item in side_effects if item not in indication_like_side_effects]

        records.append(
            DatasetMedicineRecord(
                brand_name=brand,
                generic_name=generic,
                manufacturer_name=_clean_value(row.get(manufacturer_col)) if manufacturer_col else "",
                medicine_type=_clean_value(row.get(type_col)) if type_col else "",
                price=_clean_value(row.get(price_col)) if price_col else "",
                is_discontinued=_clean_value(row.get(discontinued_col)) if discontinued_col else "",
                drug_class=_clean_value(row.get(drug_class_col)) if drug_class_col else "",
                indications=indications,
                why_used=indications,
                side_effects=side_effects,
                warnings_precautions=_warning_like_items(_split_row_columns(row, warning_cols)),
                interactions_basic=_split_row_columns(row, interaction_cols),
                unit_size=_clean_value(row.get(unit_size_col)) if unit_size_col else "",
                source=source,
            )
        )
    return records


def _first_existing_column(dataframe, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in dataframe.columns:
            return candidate
    return None


def _existing_columns(dataframe, candidates: tuple[str, ...]) -> list[str]:
    return [candidate for candidate in candidates if candidate in dataframe.columns]


def _first_column_with_prefix(dataframe, prefixes: tuple[str, ...]) -> str | None:
    for column in dataframe.columns:
        if any(column.startswith(prefix) for prefix in prefixes):
            return column
    return None


def _canonical_column_name(value: object) -> str:
    text = str(value).strip().lower()
    text = text.replace("₹", "rs")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _clean_value(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "<na>"}:
        return ""
    return text


def _split_text_items(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_split_text_items(item))
        return _unique_text_items(items)

    text = _clean_value(value)
    if not text:
        return []
    chunks = re.split(r"\s*[|;,\n]\s*", text)
    if len(chunks) == 1:
        chunks = re.split(r"\s{2,}", text)
    return _unique_text_items(_clean_composition(chunk) for chunk in chunks if _clean_composition(chunk))


def _split_row_columns(row: dict[str, Any], columns: list[str]) -> list[str]:
    items: list[str] = []
    for column in columns:
        items.extend(_split_text_items(row.get(column)))
    return _unique_text_items(items)


def _warning_like_items(values: list[str]) -> list[str]:
    warning_terms = (
        "avoid",
        "contraindicat",
        "allerg",
        "hypersensitiv",
        "pregnan",
        "do not",
        "not use",
        "severe",
        "risk",
        "monitor",
        "caution",
        "discontinue",
        "renal",
        "hepatic",
        "liver",
        "kidney",
    )
    return [
        value
        for value in values
        if len(value.split()) > 3 or any(term in value.lower() for term in warning_terms)
    ]


def _looks_like_indication(value: str) -> bool:
    text = value.lower()
    indication_terms = (
        "acne",
        "adhd",
        "allerg",
        "angina",
        "anxiety",
        "asthma",
        "bacterial",
        "cancer",
        "copd",
        "depression",
        "diabetes",
        "disease",
        "disorder",
        "epilepsy",
        "fungal",
        "glaucoma",
        "heart failure",
        "hiv",
        "hypertension",
        "infection",
        "inflammation",
        "migraine",
        "parkinson",
        "psoriasis",
        "seizure",
        "syndrome",
        "virus",
    )
    if len(text.split()) < 2 and text not in {"acne", "asthma", "copd", "glaucoma", "migraine", "psoriasis"}:
        return False
    return any(term in text for term in indication_terms)


def _clean_composition(value: object) -> str:
    text = _clean_value(value)
    if not text:
        return ""
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu|%)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,+-")
    return text


def _composition_parts(value: str) -> list[str]:
    text = _clean_composition(value)
    if not text:
        return []
    parts = re.split(r"\s*(?:,|\+|/|&|\band\b)\s*", text, flags=re.I)
    return _unique_text_items(part for part in parts if part)


def _tabular_files_from_directory(directory: Path, glob_patterns: str) -> list[Path]:
    paths: list[Path] = []
    for pattern in [item.strip() for item in glob_patterns.split(",") if item.strip()]:
        paths.extend(
            path
            for path in directory.glob(pattern)
            if path.is_file() and path.suffix.lower() in DATASET_SUFFIXES
        )
    return sorted(paths, key=lambda path: path.name.lower())


def _resolve_local_path(path: Path) -> Path:
    if path.exists():
        return path

    path_text = path.as_posix()
    if path_text == "/app/data" or path_text.startswith("/app/data/"):
        backend_root = Path(__file__).resolve().parents[2]
        relative = path_text.removeprefix("/app/data").lstrip("/")
        local_path = backend_root / "data" / relative
        if local_path.exists():
            return local_path

    return path


def _deduplicate_records(records: list[DatasetMedicineRecord]) -> list[DatasetMedicineRecord]:
    deduped: list[DatasetMedicineRecord] = []
    seen: set[str] = set()
    for record in records:
        key = "|".join(
            [
                normalize_drug_name(record.brand_name),
                normalize_drug_name(record.generic_name),
                record.manufacturer_name.lower(),
                record.source.lower(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _build_brand_index(records: list[DatasetMedicineRecord]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for position, record in enumerate(records):
        key = normalize_drug_name(record.brand_name)
        if key:
            index.setdefault(key, []).append(position)
    return index


def _merge_record_group(records: list[DatasetMedicineRecord], score: float) -> DatasetMedicineRecord:
    if not records:
        return DatasetMedicineRecord(brand_name="", generic_name="")

    primary = max(records, key=_record_richness_score)
    return DatasetMedicineRecord(
        brand_name=primary.brand_name,
        generic_name=_merge_composition_field(record.generic_name for record in records),
        manufacturer_name=_merge_text_field(record.manufacturer_name for record in records),
        medicine_type=_merge_text_field(record.medicine_type for record in records),
        price=primary.price or _first_text(record.price for record in records),
        is_discontinued=primary.is_discontinued or _first_text(record.is_discontinued for record in records),
        drug_class=_merge_text_field(record.drug_class for record in records),
        indications=_merge_list_field(record.indications for record in records),
        why_used=_merge_list_field((record.why_used or record.indications) for record in records),
        side_effects=_merge_list_field(record.side_effects for record in records),
        warnings_precautions=_merge_list_field(record.warnings_precautions for record in records),
        interactions_basic=_merge_list_field(record.interactions_basic for record in records),
        unit_size=primary.unit_size or _first_text(record.unit_size for record in records),
        source=_merge_text_field(record.source for record in records),
    )


def _record_richness_score(record: DatasetMedicineRecord) -> int:
    text_fields = [
        record.generic_name,
        record.manufacturer_name,
        record.medicine_type,
        record.price,
        record.is_discontinued,
        record.drug_class,
        record.unit_size,
    ]
    return (
        sum(1 for value in text_fields if value)
        + len(record.indications or []) * 2
        + len(record.why_used or [])
        + len(record.side_effects or []) * 2
        + len(record.warnings_precautions or []) * 2
        + len(record.interactions_basic or []) * 2
    )


def _merge_text_field(values: Any) -> str:
    return ", ".join(_unique_text_items(value for value in values if _clean_value(value)))


def _merge_composition_field(values: Any) -> str:
    parts: list[str] = []
    for value in values:
        parts.extend(_composition_parts(_clean_value(value)))
    return ", ".join(_unique_text_items(parts))


def _first_text(values: Any) -> str:
    for value in values:
        cleaned = _clean_value(value)
        if cleaned:
            return cleaned
    return ""


def _merge_list_field(values: Any) -> list[str]:
    items: list[str] = []
    for value in values:
        if value:
            items.extend(value)
    return _unique_text_items(items)


def _unique_text_items(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_value(value)
        if not cleaned:
            continue
        key = normalize_drug_name(cleaned) or cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _largest_tabular_file(directory: Path) -> Path | None:
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in DATASET_SUFFIXES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)
