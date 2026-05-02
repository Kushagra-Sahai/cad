from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.core.database import mongo_state
from app.schemas.medicine import HealthResponse, MedicineAnalysis, SpeechToTextResponse, TextMedicineRequest
from app.services.analysis_engine import AnalysisEngine
from app.services.speech_service import SpeechService, SpeechServiceUnavailable

router = APIRouter()


def get_analysis_engine(request: Request) -> AnalysisEngine:
    return request.app.state.analysis_engine


def get_speech_service(request: Request) -> SpeechService:
    return request.app.state.speech_service


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    mongo_status = "connected" if mongo_state.db is not None else "unavailable"
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        mongo=mongo_status,
        llm_provider=settings.llm_provider,
    )


@router.post("/search-medicine", response_model=MedicineAnalysis)
async def search_medicine(payload: TextMedicineRequest, request: Request) -> MedicineAnalysis:
    engine = get_analysis_engine(request)
    return await engine.analyze_text(payload.query, source="text")


@router.post("/analyze-image", response_model=MedicineAnalysis)
async def analyze_image(request: Request, file: UploadFile = File(...)) -> MedicineAnalysis:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    engine = get_analysis_engine(request)
    return await engine.analyze_image(file)


@router.post("/speech-to-text", response_model=SpeechToTextResponse)
async def speech_to_text(request: Request, file: UploadFile = File(...)) -> SpeechToTextResponse:
    speech = get_speech_service(request)
    audio = await file.read()
    try:
        transcript = await speech.speech_to_text(audio, file.content_type)
    except SpeechServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SpeechToTextResponse(transcript=transcript.transcript, confidence=transcript.confidence)


@router.get("/text-to-speech")
async def text_to_speech(
    request: Request,
    text: str = Query(..., min_length=1, max_length=4500),
) -> StreamingResponse:
    speech = get_speech_service(request)
    try:
        audio = await speech.text_to_speech(text)
    except SpeechServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return StreamingResponse(
        io.BytesIO(audio),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="mediscan-response.mp3"'},
    )
