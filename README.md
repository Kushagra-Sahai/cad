# MediScan AI

MediScan AI is a full-stack medicine analysis app built with FastAPI, React, Tesseract OCR, OpenFDA, RxNorm, LangChain + FAISS, IBM Watson Speech-to-Text/Text-to-Speech, MongoDB, Docker, and Ollama as the free local LLM runtime.

It accepts text, image, and voice input, then returns a strict structured medicine response:

```json
{
  "brand_name": "",
  "generic_name": "",
  "drug_class": "",
  "indications": [],
  "usage_guidance": "",
  "timing_guidance": "",
  "side_effects": [],
  "warnings_precautions": [],
  "interactions_basic": [],
  "alternatives_generic": [],
  "confidence_score": 0.0,
  "disclaimer": "This is general medical information. Consult a qualified doctor before use."
}
```

## Safety

MediScan AI provides general medicine information only. It does not prescribe medicines, does not provide exact dosage instructions, and keeps the required disclaimer in every analysis result.

## Project Structure

```text
frontend/
  src/components/
    ChatBox.jsx
    ImageUploader.jsx
    VoiceRecorder.jsx
    MedicineCard.jsx
backend/
  app/
    api/
    core/
    schemas/
    services/
      ocr_service.py
      drug_lookup_service.py
      rag_service.py
      llm_service.py
      speech_service.py
      analysis_engine.py
    main.py
docker/
.env.example
docker-compose.yml
README.md
```

## Quick Start

1. Create your environment file:

```bash
cp .env.example .env
```

2. Add IBM Watson credentials to `.env` if you want voice transcription and audio playback.

3. Start the stack:

```bash
docker-compose up --build
```

The app will be available at:

- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

## Ollama Model

The Compose stack starts Ollama, but model files are not bundled. Pull a local model once:

```bash
docker-compose exec ollama ollama pull llama3.1
```

Ollama runs locally and does not require a paid LLM API key. Without a running Ollama model, the backend still returns a safe deterministic structured response using retrieved OpenFDA/RxNorm data.

## Local Medicine Datasets

MediScan AI loads every supported tabular dataset in `backend/data` as an additional lookup source for brand names, generic compositions, uses, side effects, manufacturers, prices, and classes.

Supported file types:

```text
.csv, .xlsx, .xls, .parquet, .pq, .json, .jsonl
```

When the same medicine appears in multiple files, MediScan merges the local records into one richer match. Uses and side effects are combined across datasets, so different side-effect lists are preserved instead of only the first file winning.

The Kaggle `shudhanshusingh/az-medicine-dataset-of-india` dataset can be downloaded into the same folder:

```bash
docker compose run --rm backend python scripts/download_kaggle_dataset.py --output /app/data/medicine_dataset.csv
docker compose up --build
```

The backend reads:

```env
MEDICINE_DATASET_PATH=/app/data/medicine_dataset.csv
MEDICINE_DATASET_DIR=/app/data
MEDICINE_DATASET_GLOB=*.csv,*.xlsx,*.xls,*.parquet,*.pq,*.json,*.jsonl
ENABLE_KAGGLE_DATASET=false
KAGGLE_DATASET_REF=shudhanshusingh/az-medicine-dataset-of-india
KAGGLE_DATASET_FILE=
MEDICINE_DATASET_MIN_SCORE=82
```

If `MEDICINE_DATASET_DIR` is present, all matching files in that directory are loaded. If `MEDICINE_DATASET_PATH` is also present, that file is included too. If you set `ENABLE_KAGGLE_DATASET=true`, the backend can also download from Kaggle at runtime, but local file mode is more predictable for Docker and production.

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

- `GET /api/v1/health`
- `POST /api/v1/search-medicine`
- `POST /api/v1/analyze-image`
- `POST /api/v1/speech-to-text`
- `GET /api/v1/text-to-speech`

## Environment Variables

See `.env.example` for all supported variables. Secrets are never hardcoded, and `.env` is ignored by Git.
