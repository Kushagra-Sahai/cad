import json
from types import SimpleNamespace

from app.services.local_medicine_dataset_service import LocalMedicineDatasetService


def _settings_for(directory):
    return SimpleNamespace(
        medicine_dataset_path=None,
        medicine_dataset_dir=str(directory),
        medicine_dataset_glob="*.csv,*.json,*.jsonl",
        enable_kaggle_dataset=False,
        kaggle_dataset_ref="",
        kaggle_dataset_file=None,
        medicine_dataset_min_score=82,
    )


def test_duplicate_medicine_records_merge_local_details(tmp_path):
    first = tmp_path / "first.csv"
    first.write_text(
        "name,short_composition1,uses,side_effects,manufacturer_name\n"
        "Testmed 500 Tablet,Foo 500mg,Infection,\"Nausea,Headache\",Maker A\n",
        encoding="utf-8",
    )

    second = tmp_path / "second.csv"
    second.write_text(
        "Medicine Name,Composition,Uses,Side_effects,Manufacturer,Contraindications,Interaction warnings & Precautions\n"
        "Testmed 500 Tablet,Foo 500mg,Respiratory infection,\"Headache,Dizziness\",Maker B,"
        "Severe allergy,\"Avoid with Testblocker; monitor hydration\"\n",
        encoding="utf-8",
    )

    result = LocalMedicineDatasetService(_settings_for(tmp_path)).search("Testmed 500")

    assert result["found"] is True
    assert result["records_loaded"] == 2
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match["brand_name"] == "Testmed 500 Tablet"
    assert match["generic_name"] == "Foo"
    assert match["indications"] == ["Infection", "Respiratory infection"]
    assert match["why_used"] == ["Infection", "Respiratory infection"]
    assert match["side_effects"] == ["Nausea", "Headache", "Dizziness"]
    assert match["warnings_precautions"] == ["Severe allergy", "Avoid with Testblocker", "monitor hydration"]
    assert match["interactions_basic"] == ["Avoid with Testblocker", "monitor hydration"]
    assert "first.csv" in match["source"]
    assert "second.csv" in match["source"]


def test_json_dataset_file_loads_from_data_directory(tmp_path):
    payload = [
        {
            "brand_name": "Jsonmed Syrup",
            "generic_name": "Bar 10mg",
            "side_effects": ["Rash", "Fatigue"],
        }
    ]
    (tmp_path / "medicines.json").write_text(json.dumps(payload), encoding="utf-8")

    result = LocalMedicineDatasetService(_settings_for(tmp_path)).search("Jsonmed")

    assert result["found"] is True
    assert result["records_loaded"] == 1
    assert result["matches"][0]["generic_name"] == "Bar"
    assert result["matches"][0]["side_effects"] == ["Rash", "Fatigue"]


def test_condition_like_values_in_side_effect_column_enrich_why_used(tmp_path):
    dataset = tmp_path / "deepseek.csv"
    dataset.write_text(
        "Generic Name,Drug Class,Indications,Dosage Form,Strength,Route of Administration,Side Effects\n"
        "Acyclovir,Antiviral,Herpes simplex virus infections,Tablet,400 mg,Oral,Varicella zoster virus infections\n",
        encoding="utf-8",
    )

    result = LocalMedicineDatasetService(_settings_for(tmp_path)).search("Acyclovir")

    match = result["matches"][0]
    assert match["why_used"] == [
        "Herpes simplex virus infections",
        "Varicella zoster virus infections",
    ]
    assert match["side_effects"] == []
