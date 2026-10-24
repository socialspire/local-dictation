import json,time,wave
from pathlib import Path
import sounddevice as sd
import numpy as np
from engine import Engine,load_config,save_config,SAMPLE_RATE
from app import Worker
import queue
cfg=load_config()
cfg.update(listen_on_startup=True,probe_interval=.4,input_name_contains='AirPods',input_hostapi='MME')
save_config(cfg)
e=Engine(cfg); t=time.perf_counter(); e.warm_up(); print('decoder warmup',round(time.perf_counter()-t,3),flush=True)
with wave.open('qa-speech.wav') as f: a=np.frombuffer(f.readframes(f.getnframes()),dtype=np.int16).astype(np.float32)/32768
report=[]
for interval in (1.2,.4):
 c=dict(cfg,probe_interval=interval); w=Worker(c,queue.Queue(),e); w.mode='idle'; w.armed=True; w.open_mic=lambda:None
 detected=[]
 def start(*args):
  detected.append(w.samples/SAMPLE_RATE)
  raise StopIteration
 w.start=start
 t=time.perf_counter()
 try:
  for pos in range(0,len(a),800): w.feed(a[pos:pos+800])
 except StopIteration: pass
 item={'poll_seconds':interval,'trigger_detected_at_audio_seconds':detected[0] if detected else None,'total_inference_seconds':round(time.perf_counter()-t,3)}
 print(item,flush=True); report.append(item)
Path('qa-latency.json').write_text(json.dumps(report,indent=2))
