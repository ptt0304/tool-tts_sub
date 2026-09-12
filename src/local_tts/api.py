from __future__ import annotations

import re
import time
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field

from local_tts.service import TTSService, VoiceNotReadyError

SAFE_SEGMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

OPERATOR_UI = r"""<!doctype html><html><head><meta charset='utf-8'><title>Local_TTS</title><style>body{font:15px Segoe UI,Arial;max-width:1040px;margin:28px auto;color:#17202a;background:#f6f8fb}.card{background:#fff;border:1px solid #dbe3ec;border-radius:8px;padding:18px;margin:12px 0}input,select,textarea,button{padding:9px;margin:5px 0;box-sizing:border-box}input,select,textarea{width:100%;border:1px solid #aeb9c6;border-radius:4px}textarea{min-height:120px}button{background:#146c94;color:#fff;border:0;border-radius:4px;cursor:pointer;margin-right:6px}button.secondary{background:#586b7c}label{font-weight:600;display:block;margin-top:8px}.muted{color:#5b6875}pre{background:#101820;color:#d9e7f5;padding:12px;white-space:pre-wrap;min-height:72px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ready{color:#16733b}.disabled{color:#a95a00}</style></head><body><h1>Local_TTS</h1><p id='health' class='muted'>Đang kết nối dịch vụ…</p><div class='card'><h2>Tạo giọng nói</h2><div class='row'><div><label>Nhập văn bản trực tiếp</label><textarea id='text' placeholder='Nhập nội dung tiếng Việt…'></textarea></div><div><label>Hoặc chọn SRT / TXT</label><input id='source' type='file' accept='.srt,.txt,text/plain'><label>Từ điển thay thế (mỗi dòng: từ => cách đọc)</label><textarea id='dictionary' placeholder='OpenAI => Ô-pần AI'></textarea></div></div><div class='row'><div><label>Giọng nói</label><select id='voice'></select><button class='secondary' id='enable'>Xác thực & bật giọng ZK đã chọn</button><p id='voiceinfo' class='muted'></p></div><div><label>Tốc độ</label><input id='speed' type='number' min='0.25' max='3' step='0.1' value='1'><label>Output prefix</label><input id='prefix' value='tts'></div></div><button id='generate'>Tạo WAV</button></div><div class='card'><h2>Thư viện giọng</h2><p class='muted'>Giọng ZK được hiển thị đầy đủ. Chỉ giọng READY tạo audio được; nút xác thực chạy inference thật cho giọng ZK đã chọn trước khi bật.</p><div id='library'></div></div><pre id='result'>Chờ dịch vụ sẵn sàng…</pre><script>
const out=$('#result'),voice=$('#voice'),health=$('#health');let voices=[];function $(s){return document.querySelector(s)}
async function load(){try{let current=voice.value,h=await (await fetch('/api/health')).json(),v=(await (await fetch('/api/voices')).json()).voices;voices=v;health.textContent=`Model: ${h.status} | READY: ${h.voices} | Tổng giọng: ${v.length}`;voice.innerHTML=v.map(x=>`<option value="${x.voice_id}">${x.display_name} — ${x.status}</option>`).join('');let first=v.find(x=>x.voice_id===current)||v.find(x=>x.status==='READY');if(first)voice.value=first.voice_id;$('#library').innerHTML=v.map(x=>`<div class='${x.status==='READY'?'ready':'disabled'}'>${x.display_name} (${x.voice_id}) — ${x.status}${x.status_reason?' : '+x.status_reason:''}</div>`).join('');info()}catch(e){health.textContent='Đang chờ Local_TTS khởi động…';setTimeout(load,1000)}}
function info(){let x=voices.find(v=>v.voice_id===voice.value);$('#voiceinfo').textContent=x?`${x.source} | ${x.status}`:''}voice.onchange=info;
function replaceText(t){for(let line of $('#dictionary').value.split(/\r?\n/)){let p=line.split('=>');if(p.length===2&&p[0].trim())t=t.split(p[0].trim()).join(p.slice(1).join('=>').trim())}return t}
function cues(t){if(!t.trim())return [];if(!t.includes('-->'))return t.split(/\r?\n+/).map((x,i)=>({n:i+1,text:x.trim()})).filter(x=>x.text);return t.trim().split(/\r?\n\s*\r?\n/).map((b,i)=>{let l=b.split(/\r?\n/).filter(Boolean),p=/^\d+$/.test(l[0])?1:0;return {n:p?l[0]:i+1,text:l.slice(p+1).filter(x=>!x.includes('-->')).join(' ').trim()}}).filter(x=>x.text)}
$('#enable').onclick=async()=>{let id=voice.value;if(!id)return;out.textContent='Đang xác thực giọng ZK bằng inference thật…';let r=await fetch(`/api/voices/${id}/enable`,{method:'POST'}),d=await r.json();if(d.error)out.textContent=`Không thể bật: ${d.error.message}`;else{out.textContent=`Đã bật ${d.display_name}.`;await load()}};
$('#generate').onclick=async()=>{let f=$('#source').files[0],raw=f?await f.text():$('#text').value,c=cues(replaceText(raw)),id=voice.value,prefix=$('#prefix').value.replace(/[^A-Za-z0-9_-]/g,'_')||'tts',speed=+$('#speed').value;if(!c.length||!id){out.textContent='Nhập văn bản/chọn file và chọn giọng READY.';return}if(voices.find(x=>x.voice_id===id)?.status!=='READY'){out.textContent='Giọng ZK chưa READY. Hãy bấm “Xác thực & bật” trước.';return}out.textContent=`Đang tạo ${c.length} audio…`;let r=await fetch('/api/tts/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items:c.map((x,i)=>({segment_id:`${prefix}_${String(x.n||i+1).padStart(6,'0')}`,speaker_id:'LOCAL_UI',voice_id:id,text:x.text,speed}))})}),d=await r.json(),bad=d.items.filter(x=>x.error).length;out.textContent=`Hoàn tất ${d.items.length-bad}/${d.items.length}. WAV nằm trong outputs/.${bad?' Lỗi: '+bad:''}`};load();</script></body></html>"""


class GenerateRequest(BaseModel):
    segment_id: str
    speaker_id: str = Field(min_length=1, max_length=128)
    voice_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=10_000)
    speed: float = Field(default=1.0, gt=0, le=3)


class BatchRequest(BaseModel):
    items: list[GenerateRequest] = Field(min_length=1, max_length=100)


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

    def generate_one(payload: GenerateRequest, request: Request):
        if not payload.text.strip():
            return _error(422, "INVALID_TEXT", "text must contain non-whitespace characters")
        if not SAFE_SEGMENT_ID.fullmatch(payload.segment_id) or payload.segment_id.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1,10)], *[f"LPT{i}" for i in range(1,10)]}:
            return _error(422, "INVALID_TEXT", "segment_id contains unsafe filename characters")
        service = request.app.state.service
        if service.health().status != "READY":
            return _error(503, "MODEL_NOT_READY", "TTS model is not ready")
        started = time.perf_counter()
        try:
            result = service.synthesize(payload.text, payload.voice_id, payload.speed)
        except KeyError:
            return _error(404, "VOICE_NOT_FOUND", "voice_id is unknown")
        except VoiceNotReadyError:
            return _error(409, "VOICE_NOT_READY", "voice is not ready for synthesis")
        except ValueError:
            return _error(422, "INVALID_TEXT", "invalid synthesis input")
        except Exception:
            return _error(500, "GENERATION_FAILED", "TTS generation failed")
        try:
            destination = request.app.state.output_dir / f"{payload.segment_id}.wav"
            request.app.state.output_dir.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(result.wav_bytes)
        except OSError:
            return _error(500, "OUTPUT_WRITE_FAILED", "could not write generated audio")
        return {
            "segment_id": payload.segment_id, "speaker_id": payload.speaker_id,
            "voice_id": payload.voice_id, "audio_path": str(destination.resolve()),
            "duration": result.audio_duration_seconds or 0.0,
            "sample_rate": result.sample_rate,
            "generation_time": result.generation_seconds or (time.perf_counter() - started),
        }

    @app.post("/api/tts/generate")
    def generate(payload: GenerateRequest, request: Request):
        with output_lock:
            return generate_one(payload, request)

    @app.post("/api/tts/batch")
    def batch(payload: BatchRequest, request: Request):
        results = []
        with output_lock:
            for item in payload.items:
                result = generate_one(item, request)
                if isinstance(result, JSONResponse):
                    result = {"segment_id": item.segment_id, "speaker_id": item.speaker_id, "voice_id": item.voice_id, **json.loads(result.body)}
                results.append(result)
        return {"items": results}

    return app

