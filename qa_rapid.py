import json
import queue
import wave
from unittest.mock import patch
import numpy as np
from app import Worker
from engine import Engine, load_config
cfg = load_config(); cfg['voice_stop'] = True
engine = Engine(cfg)
with wave.open('qa-rapid.wav') as f:
    audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768
w = Worker(cfg, queue.Queue(), engine)
w.mode = 'idle'; w.armed = True
w.open_mic = lambda: None; w.close_mic = lambda: None
with patch('app.paste', return_value=False):
    for start in range(0, len(audio), 800):
        w.feed(audio[start:start+800])
    for _ in range(120): w.feed(np.zeros(800, dtype=np.float32))
results = [value for kind,value in list(w.events.queue) if kind == 'result']
assert len(results) == 1, results
assert 'atlas' not in results[0].lower() and 'stop writing' not in results[0].lower(), results
assert results[0].lower().startswith('immediately capture every word'), results
print('PASS streaming keyword-to-stop integration:', json.dumps(results), flush=True)
