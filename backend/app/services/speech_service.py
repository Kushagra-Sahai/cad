from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from app.core.config import Settings


class SpeechServiceUnavailable(RuntimeError):
    pass


@dataclass
class TranscriptResult:
    transcript: str
    confidence: float


class SpeechService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def speech_to_text(self, audio_bytes: bytes, content_type: str | None) -> TranscriptResult:
        if not self.settings.watson_stt_api_key or not self.settings.watson_stt_url:
            raise SpeechServiceUnavailable("Watson Speech-to-Text is not configured.")

        return await asyncio.to_thread(self._speech_to_text_sync, audio_bytes, content_type)

    async def text_to_speech(self, text: str) -> bytes:
        if not self.settings.watson_tts_api_key or not self.settings.watson_tts_url:
            raise SpeechServiceUnavailable("Watson Text-to-Speech is not configured.")

        text = text.strip()
        if not text:
            raise ValueError("Text is required for speech synthesis.")
        return await asyncio.to_thread(self._text_to_speech_sync, text[:4500])

    def _speech_to_text_sync(self, audio_bytes: bytes, content_type: str | None) -> TranscriptResult:
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
        from ibm_watson import SpeechToTextV1

        authenticator = IAMAuthenticator(self.settings.watson_stt_api_key)
        service = SpeechToTextV1(authenticator=authenticator)
        service.set_service_url(self.settings.watson_stt_url)
        result = service.recognize(
            audio=io.BytesIO(audio_bytes),
            content_type=content_type or "audio/webm",
            model=self.settings.watson_stt_model,
        ).get_result()

        alternatives = []
        for item in result.get("results", []):
            alternatives.extend(item.get("alternatives", []))
        if not alternatives:
            return TranscriptResult(transcript="", confidence=0.0)

        best = max(alternatives, key=lambda alt: alt.get("confidence", 0.0))
        return TranscriptResult(
            transcript=str(best.get("transcript", "")).strip(),
            confidence=float(best.get("confidence", 0.0)),
        )

    def _text_to_speech_sync(self, text: str) -> bytes:
        from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
        from ibm_watson import TextToSpeechV1

        authenticator = IAMAuthenticator(self.settings.watson_tts_api_key)
        service = TextToSpeechV1(authenticator=authenticator)
        service.set_service_url(self.settings.watson_tts_url)
        response = service.synthesize(
            text=text,
            voice=self.settings.watson_tts_voice,
            accept="audio/mp3",
        ).get_result()
        return response.content
