from __future__ import annotations

import re
import time
import json
import io
import wave
import logging
import threading
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

from local_tts.audio import PREVIEW_SECONDS, PREVIEW_TEXT, PauseSettings, fit_wav_duration
from local_tts.operator_ui import OPERATOR_UI
from local_tts.service import TTSService, VoiceNotReadyError

logger = logging.getLogger("local_tts.api")

SAFE_SEGMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

class PauseRequest(BaseModel):
    space: float = Field(default=0.0, ge=0, le=10)
    comma: float = Field(default=0.25, ge=0, le=10)
    period: float = Field(default=0.45, ge=0, le=10)
    question: float = Field(default=0.55, ge=0, le=10)
    colon: float = Field(default=0.30, ge=0, le=10)
    ellipsis: float = Field(default=0.65, ge=0, le=10)
    newline: float = Field(default=0.50, ge=0, le=10)
    break_time: float = Field(default=1.0, ge=0, le=10)

    def to_domain(self) -> PauseSettings:
        return PauseSettings(**self.model_dump())


class GenerateRequest(BaseModel):
    segment_id: str
    speaker_id: str = Field(min_length=1, max_length=128)
    voice_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=10_000)
    speed: float = Field(default=1.0, gt=0, le=3)
    pause_settings: PauseRequest | None = None


class BatchRequest(BaseModel):
    items: list[GenerateRequest] = Field(min_length=1, max_length=100)
    output_name: str | None = Field(default=None, max_length=128)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(service: TTSService, output_dir: Path) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.service = service
        app.state.output_dir = output_dir
        yield

    app = FastAPI(title="Local_TTS", lifespan=lifespan)
    app.state.service = service
    app.state.output_dir = output_dir
    output_lock = threading.Lock()

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def operator_ui():
        return OPERATOR_UI

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return _error(422, "INVALID_TEXT", "Invalid request fields")

    @app.get("/api/health")
    def health(request: Request):
        state = request.app.state.service.health()
        return {"status": state.status, "voices": sum(v.status.value == "READY" for v in service.list_voices())}

    @app.get("/api/voices")
    def voices(request: Request):
        return {"voices": [voice.as_dict() for voice in request.app.state.service.list_voices()]}

    @app.get("/api/voices/{voice_id}")
    def voice(voice_id: str, request: Request):
        item = request.app.state.service.registry.get(voice_id)
        return item.as_dict() if item else _error(404, "VOICE_NOT_FOUND", "voice_id is unknown")

    @app.post("/api/voices/{voice_id}/preview")
    def preview_voice(voice_id: str, request: Request):
        service = request.app.state.service
        voice = service.registry.get(voice_id)
        if voice is None:
            return _error(404, "VOICE_NOT_FOUND", "voice_id is unknown")
        if service.health().status != "READY":
            return _error(503, "MODEL_NOT_READY", "TTS model is not ready")
        fingerprint = str(voice.metadata.get("fingerprint", ""))
        cache_key = hashlib.sha256(f"{PREVIEW_TEXT}|{fingerprint}".encode("utf-8")).hexdigest()[:12]
        safe_voice_id = re.sub(r"[^A-Za-z0-9_-]", "_", voice_id)
        preview_dir = request.app.state.output_dir / "previews"
        destination = preview_dir / f"{safe_voice_id}_{cache_key}.wav"
        try:
            with output_lock:
                if destination.is_file():
                    wav_bytes = destination.read_bytes()
                else:
                    result = service.synthesize(PREVIEW_TEXT, voice_id)
                    try:
                        wav_bytes = fit_wav_duration(result.wav_bytes, PREVIEW_SECONDS)
                        preview_dir.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(wav_bytes)
                    finally:
                        if result.output_path:
                            result.output_path.unlink(missing_ok=True)
            return Response(
                content=wav_bytes,
                media_type="audio/wav",
                headers={"Cache-Control": "private, max-age=3600", "X-Preview-Seconds": str(PREVIEW_SECONDS)},
            )
        except VoiceNotReadyError:
            return _error(409, "VOICE_NOT_READY", "voice is not ready for synthesis")
        except (OSError, ValueError):
            logger.exception("PREVIEW failed voice=%s", voice_id)
            return _error(500, "OUTPUT_WRITE_FAILED", "could not create voice preview")
        except Exception:
            logger.exception("PREVIEW failed voice=%s", voice_id)
            return _error(500, "GENERATION_FAILED", "voice preview generation failed")

    @app.post("/api/voices/{voice_id}/enable")
    def enable_voice(voice_id: str, request: Request):
        service = request.app.state.service
        if service.health().status != "READY":
            return _error(503, "MODEL_NOT_READY", "TTS model is not ready")
        try:
            with output_lock:
                service.enable_reference_voice(voice_id)
            return service.registry.get(voice_id).as_dict()
        except KeyError:
            return _error(404, "VOICE_NOT_FOUND", "voice_id is unknown")
        except VoiceNotReadyError:
            return _error(409, "VOICE_NOT_READY", "voice cannot be enabled")
        except Exception:
            return _error(500, "GENERATION_FAILED", "reference voice validation failed")

    def generate_one(payload: GenerateRequest, request: Request, *, write_output: bool = True):
        logger.info("GENERATE start segment=%s voice=%s text_chars=%d", payload.segment_id, payload.voice_id, len(payload.text))
        if not payload.text.strip():
            return _error(422, "INVALID_TEXT", "text must contain non-whitespace characters")
        if not SAFE_SEGMENT_ID.fullmatch(payload.segment_id) or payload.segment_id.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]}:
            return _error(422, "INVALID_TEXT", "segment_id contains unsafe filename characters")
        service = request.app.state.service
        if service.health().status != "READY":
            return _error(503, "MODEL_NOT_READY", "TTS model is not ready")
        started = time.perf_counter()
        try:
            result = service.synthesize_paused(
                payload.text,
                payload.voice_id,
                payload.speed,
                payload.pause_settings.to_domain() if payload.pause_settings else None,
            )
            logger.info("GENERATE done segment=%s duration=%.3fs", payload.segment_id, result.audio_duration_seconds or 0.0)
        except KeyError:
            return _error(404, "VOICE_NOT_FOUND", "voice_id is unknown")
        except VoiceNotReadyError:
            return _error(409, "VOICE_NOT_READY", "voice is not ready for synthesis")
        except ValueError:
            return _error(422, "INVALID_TEXT", "invalid synthesis input")
        except Exception:
            logger.exception("GENERATE failed segment=%s voice=%s", payload.segment_id, payload.voice_id)
            return _error(500, "GENERATION_FAILED", "TTS generation failed")
        # The engine may use a temporary WAV while constructing the response.
        # API output ownership belongs to this layer, so remove that artifact.
        if result.output_path and result.output_path != request.app.state.output_dir / f"{payload.segment_id}.wav":
            try:
                result.output_path.unlink(missing_ok=True)
            except OSError:
                pass
        response = {
            "segment_id": payload.segment_id, "speaker_id": payload.speaker_id,
            "voice_id": payload.voice_id,
            "duration": result.audio_duration_seconds or 0.0,
            "sample_rate": result.sample_rate,
            "generation_time": result.generation_seconds or (time.perf_counter() - started),
        }
        if not write_output:
            # Batch assembly stays in memory so a failed or interrupted batch
            # cannot leave per-segment WAV files in the public output folder.
            response["_wav_bytes"] = result.wav_bytes
            return response
        try:
            destination = request.app.state.output_dir / f"{payload.segment_id}.wav"
            request.app.state.output_dir.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(result.wav_bytes)
        except OSError:
            return _error(500, "OUTPUT_WRITE_FAILED", "could not write generated audio")
        response["audio_path"] = str(destination.resolve())
        return response

    @app.post("/api/tts/generate")
    def generate(payload: GenerateRequest, request: Request):
        with output_lock:
            return generate_one(payload, request)

    @app.post("/api/tts/batch")
    def batch(payload: BatchRequest, request: Request):
        results = []
        logger.info("BATCH start segments=%d output_name=%s", len(payload.items), payload.output_name or "<default>")
        with output_lock:
            for item in payload.items:
                logger.info("BATCH segment %d/%d generate=%s", len(results) + 1, len(payload.items), item.segment_id)
                result = generate_one(item, request, write_output=False)
                if isinstance(result, JSONResponse):
                    result = {"segment_id": item.segment_id, "speaker_id": item.speaker_id, "voice_id": item.voice_id, **json.loads(result.body)}
                results.append(result)
            if any("error" in item for item in results):
                logger.error("BATCH aborted: %d/%d segments failed; discarding generated audio", sum("error" in item for item in results), len(results))
                for item in results:
                    item.pop("_wav_bytes", None)
                return JSONResponse(status_code=422, content={"error": {"code": "BATCH_GENERATION_FAILED", "message": "one or more audio segments failed; see local_tts.log"}, "items": results})
            try:
                params = None
                frames = bytearray()
                for item in results:
                    wav_bytes = item.pop("_wav_bytes")
                    logger.info("BATCH read segment=%s bytes=%d", item["segment_id"], len(wav_bytes))
                    with wave.open(io.BytesIO(wav_bytes), "rb") as reader:
                        current = reader.getparams()
                        signature = (current.nchannels, current.sampwidth, current.framerate, current.comptype)
                        if params is None:
                            params = signature
                        elif signature != params:
                            raise ValueError("incompatible WAV formats")
                        frames.extend(reader.readframes(reader.getnframes()))
                output = io.BytesIO()
                with wave.open(output, "wb") as writer:
                    writer.setnchannels(params[0]); writer.setsampwidth(params[1]); writer.setframerate(params[2]); writer.writeframes(frames)
                voice_id = payload.items[0].voice_id
                raw_name = payload.output_name or f"{voice_id}_1"
                safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", Path(raw_name).stem) or f"{voice_id}_1"
                destination = request.app.state.output_dir / f"{safe_name}.wav"
                destination.write_bytes(output.getvalue())
                logger.info("BATCH joined segments=%d output=%s bytes=%d", len(results), destination, len(output.getvalue()))
                logger.info("BATCH complete output=%s", destination)
                for item in results:
                    item["audio_path"] = str(destination.resolve())
                return {"items": results, "output_path": str(destination.resolve())}
            except (OSError, ValueError):
                logger.exception("BATCH failed while joining output")
                return _error(500, "OUTPUT_WRITE_FAILED", "could not combine generated audio")

    return app

