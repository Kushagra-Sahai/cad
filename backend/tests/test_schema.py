from app.schemas.medicine import DISCLAIMER, MedicineAnalysis
from app.services.drug_lookup_service import normalize_drug_name


def test_medicine_analysis_strict_shape_defaults():
    analysis = MedicineAnalysis()
    assert analysis.model_dump() == {
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
        "disclaimer": DISCLAIMER,
    }


def test_normalize_drug_name_removes_dosage_and_form_words():
    assert normalize_drug_name("Paracetamol 500 mg Tablets") == "paracetamol"
