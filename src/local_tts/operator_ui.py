OPERATOR_UI = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local_TTS</title>
  <style>
    body{font:15px Segoe UI,Arial;max-width:1040px;margin:28px auto;padding:0 14px;color:#17202a;background:#f6f8fb}
    .card{background:#fff;border:1px solid #dbe3ec;border-radius:8px;padding:18px;margin:12px 0}
    input,select,textarea,button{padding:9px;margin:5px 0;box-sizing:border-box}
    input,select,textarea{width:100%;border:1px solid #aeb9c6;border-radius:4px}
    textarea{min-height:120px} button{background:#146c94;color:#fff;border:0;border-radius:4px;cursor:pointer;margin-right:6px}
    button.secondary{background:#586b7c} label{font-weight:600;display:block;margin-top:8px}.muted{color:#5b6875}
    pre{background:#101820;color:#d9e7f5;padding:12px;white-space:pre-wrap;min-height:72px}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .ready{color:#16733b}.disabled{color:#a95a00} dialog{border:0;border-radius:10px;box-shadow:0 10px 35px #0004;width:min(660px,90vw)}
    dialog::backdrop{background:#0007}.pause-grid{display:grid;grid-template-columns:1fr 120px;gap:8px 18px;align-items:center}.pause-grid label{margin:0}
    .voice-row{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid #edf1f5;padding:5px 0}.voice-row span{min-width:0}.voice-row button{flex:0 0 auto;padding:6px 10px}
    .hint{background:#fff8c9;border:1px solid #d3c56c;padding:10px;text-align:center}.actions{text-align:right;margin-top:14px}
    @media(max-width:700px){.row{grid-template-columns:1fr}.pause-grid{grid-template-columns:1fr 100px}}
  </style>
</head>
<body>
  <h1>Local_TTS</h1>
  <p id="health" class="muted">Đang kết nối dịch vụ…</p>
  <div class="card">
    <h2>Tạo giọng nói</h2>
    <div class="row">
      <div><label>Nhập văn bản trực tiếp</label><textarea id="text" placeholder="Nhập nội dung tiếng Việt…"></textarea></div>
      <div><label>Hoặc chọn SRT / TXT</label><input id="source" type="file" accept=".srt,.txt,text/plain"><label>Từ điển thay thế (mỗi dòng: từ =&gt; cách đọc)</label><textarea id="dictionary" placeholder="OpenAI => Ô-pần AI"></textarea></div>
    </div>
    <div class="row">
      <div><label>Giọng nói</label><select id="voice"></select><button class="secondary" id="enable">Xác thực &amp; bật giọng ZK đã chọn</button><p id="voiceinfo" class="muted"></p></div>
      <div><label>Tốc độ</label><input id="speed" type="number" min="0.25" max="3" step="0.1" value="1"><label>Output prefix</label><input id="prefix" value="tts"></div>
    </div>
    <button class="secondary" id="pauseOpen">Cấu hình ngắt nghỉ</button>
    <span id="pauseSummary" class="muted"></span><br>
    <button id="generate">Tạo WAV</button>
  </div>
  <div class="card"><h2>Thư viện giọng</h2><p class="muted">Mỗi giọng có nút nghe thử 10 giây với cùng câu: “Xin chào, bạn đang sử dụng công cụ TTS của Tùng, đây là phần nghe thử giọng nói tiếng Việt. Chúc bạn một ngày làm việc hiệu quả, vui vẻ và tràn đầy cảm hứng.” Lần đầu cần chờ tạo audio; các lần sau dùng cache.</p><audio id="voicePreview" controls preload="none" hidden></audio><div id="library"></div></div>
  <pre id="result">Chờ dịch vụ sẵn sàng…</pre>

  <dialog id="pauseDialog">
    <h2>Cấu hình ngắt nghỉ</h2>
    <p class="hint">Có thể chèn <strong>[break]</strong> vào văn bản để dùng thời gian nghỉ tùy chỉnh.</p>
    <div class="pause-grid">
      <label for="pauseSpace">Khoảng trắng (một hoặc nhiều), giây</label><input id="pauseSpace" type="number" min="0" max="10" step="0.01">
      <label for="pauseComma">Dấu phẩy (,), giây</label><input id="pauseComma" type="number" min="0" max="10" step="0.05">
      <label for="pausePeriod">Dấu chấm (.), giây</label><input id="pausePeriod" type="number" min="0" max="10" step="0.05">
      <label for="pauseQuestion">Dấu hỏi (?), giây</label><input id="pauseQuestion" type="number" min="0" max="10" step="0.05">
      <label for="pauseColon">Dấu hai chấm (: ;), giây</label><input id="pauseColon" type="number" min="0" max="10" step="0.05">
      <label for="pauseEllipsis">Dấu ba chấm (...), giây</label><input id="pauseEllipsis" type="number" min="0" max="10" step="0.05">
      <label for="pauseNewline">Xuống dòng, giây</label><input id="pauseNewline" type="number" min="0" max="10" step="0.05">
      <label for="pauseBreak">[break], giây</label><input id="pauseBreak" type="number" min="0" max="10" step="0.05">
    </div>
    <div class="actions"><button class="secondary" id="pauseCancel">Hủy</button><button id="pauseSave">Lưu và xác nhận</button></div>
  </dialog>

  <script>
    function $(selector){return document.querySelector(selector)}
    const out=$('#result'),voice=$('#voice'),health=$('#health'),previewAudio=$('#voicePreview');let voices=[],previewUrl=null,previewButton=null;
    const pauseDefaults={space:0,comma:.25,period:.45,question:.55,colon:.30,ellipsis:.65,newline:.50,break_time:1};
    let pauseValues={...pauseDefaults,...JSON.parse(localStorage.getItem('local_tts_pauses')||'{}')};
    const pauseFields={space:'#pauseSpace',comma:'#pauseComma',period:'#pausePeriod',question:'#pauseQuestion',colon:'#pauseColon',ellipsis:'#pauseEllipsis',newline:'#pauseNewline',break_time:'#pauseBreak'};
    function showPauseValues(){for(const [key,selector] of Object.entries(pauseFields))$(selector).value=pauseValues[key];$('#pauseSummary').textContent=`Cách ${pauseValues.space}s · Phẩy ${pauseValues.comma}s · Chấm ${pauseValues.period}s · Hỏi ${pauseValues.question}s · Ba chấm ${pauseValues.ellipsis}s · Xuống dòng ${pauseValues.newline}s · [break] ${pauseValues.break_time}s`}
    function pausePayload(){return {...pauseValues}}
    $('#pauseOpen').onclick=()=>{showPauseValues();$('#pauseDialog').showModal()};
    $('#pauseCancel').onclick=()=>$('#pauseDialog').close();
    $('#pauseSave').onclick=()=>{const next={};for(const [key,selector] of Object.entries(pauseFields)){const value=Number($(selector).value);if(!Number.isFinite(value)||value<0||value>10){out.textContent='Thời gian nghỉ phải từ 0 đến 10 giây.';return}next[key]=value}pauseValues=next;localStorage.setItem('local_tts_pauses',JSON.stringify(next));showPauseValues();$('#pauseDialog').close();out.textContent='Đã lưu cấu hình ngắt nghỉ trên trình duyệt này.'};
    async function load(){try{let current=voice.value,h=await (await fetch('/api/health')).json(),v=(await (await fetch('/api/voices')).json()).voices;voices=v;health.textContent=`Model: ${h.status==='READY'?'Sẵn sàng':h.status} | Sẵn sàng: ${h.voices} | Tổng giọng: ${v.length}`;voice.innerHTML=v.map(x=>`<option value="${x.voice_id}">${x.display_name}</option>`).join('');let first=v.find(x=>x.voice_id===current)||v.find(x=>x.status==='READY');if(first)voice.value=first.voice_id;$('#library').innerHTML=v.map(x=>`<div class="voice-row ${x.status==='READY'?'ready':'disabled'}"><span>${x.display_name} (${x.voice_id})${x.status==='READY'?'':` — ${x.status}${x.status_reason?' : '+x.status_reason:''}`}</span><button class="secondary" data-preview="${x.voice_id}" ${x.status==='READY'?'':'disabled'}>▶ Nghe thử 10s</button></div>`).join('');info()}catch(e){health.textContent='Đang chờ Local_TTS khởi động…';setTimeout(load,1000)}}
    function info(){let x=voices.find(v=>v.voice_id===voice.value);$('#voiceinfo').textContent=x?`${x.source}${x.status==='READY'?'':` | ${x.status}`}`:''}voice.onchange=info;
    function replaceText(t){for(let line of $('#dictionary').value.split(/\r?\n/)){let p=line.split('=>');if(p.length===2&&p[0].trim())t=t.split(p[0].trim()).join(p.slice(1).join('=>').trim())}return t}
    function cues(t){if(!t.trim())return [];if(!t.includes('-->'))return [{n:1,text:t.trim()}];return t.trim().split(/\r?\n\s*\r?\n/).map((b,i)=>{let l=b.split(/\r?\n/).filter(Boolean),p=/^\d+$/.test(l[0])?1:0;return {n:p?l[0]:i+1,text:l.slice(p+1).filter(x=>!x.includes('-->')).join('\n').trim()}}).filter(x=>x.text)}
    $('#library').onclick=async event=>{let button=event.target.closest('button[data-preview]');if(!button)return;if(button===previewButton&&!previewAudio.paused){previewAudio.pause();button.textContent='▶ Nghe thử 10s';previewButton=null;out.textContent='Đã dừng nghe thử.';return}if(button.disabled)return;if(previewButton){previewButton.disabled=false;previewButton.textContent='▶ Nghe thử 10s'}previewAudio.pause();if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null}previewButton=button;button.disabled=true;button.textContent='⏳ Đang tạo…';out.textContent=`Đang tạo bản nghe thử 10 giây cho ${button.dataset.preview}…`;try{let response=await fetch(`/api/voices/${encodeURIComponent(button.dataset.preview)}/preview`,{method:'POST'});if(!response.ok){let error=await response.json();throw new Error(error.error?.message||'Không thể tạo preview')}previewUrl=URL.createObjectURL(await response.blob());previewAudio.src=previewUrl;previewAudio.hidden=false;await previewAudio.play();button.disabled=false;button.textContent='■ Dừng';out.textContent=`Đang phát bản nghe thử: ${button.dataset.preview}`}catch(error){button.disabled=false;button.textContent='▶ Nghe thử 10s';out.textContent=`Lỗi nghe thử: ${error.message}`}};
    previewAudio.onended=()=>{if(previewButton){previewButton.disabled=false;previewButton.textContent='▶ Nghe thử 10s'}previewButton=null};
    $('#enable').onclick=async()=>{let id=voice.value;if(!id)return;out.textContent='Đang xác thực giọng ZK bằng inference thật…';let r=await fetch(`/api/voices/${id}/enable`,{method:'POST'}),d=await r.json();if(d.error)out.textContent=`Không thể bật: ${d.error.message}`;else{out.textContent=`Đã bật ${d.display_name}.`;await load()}};
    $('#generate').onclick=async()=>{let f=$('#source').files[0],raw=f?await f.text():$('#text').value,c=cues(replaceText(raw)),id=voice.value,prefix=$('#prefix').value.replace(/[^A-Za-z0-9_-]/g,'_')||'tts',speed=+$('#speed').value;if(!c.length||!id){out.textContent='Nhập văn bản/chọn file và chọn giọng.';return}if(voices.find(x=>x.voice_id===id)?.status!=='READY'){out.textContent='Giọng chưa sẵn sàng. Hãy bấm “Xác thực & bật” trước.';return}let outputName=f?f.name.replace(/\.[^.]+$/,''):`${id}_1`;out.textContent=`Đang tạo ${c.length} đoạn và ghép thành một WAV…`;let r=await fetch('/api/tts/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({output_name:outputName,items:c.map((x,i)=>({segment_id:`${prefix}_${String(x.n||i+1).padStart(6,'0')}`,speaker_id:'LOCAL_UI',voice_id:id,text:x.text,speed,pause_settings:pausePayload()}))})}),d=await r.json();if(d.error){out.textContent=`Lỗi: ${d.error.message}`;return}out.textContent=`Hoàn tất: ${d.items[0]?.audio_path||'WAV'}`};
    showPauseValues();load();
  </script>
</body>
</html>"""
