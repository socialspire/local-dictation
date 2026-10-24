import json
import time
import wave
import numpy as np
from engine import Engine, load_config, save_config
cfg = load_config()
save_config(cfg)
engine = Engine(cfg)
with wave.open('qa-speech.wav') as f:
    print('WAV', f.getframerate(), f.getnchannels(), f.getsampwidth(), flush=True)
    audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
print('WORDS', json.dumps(engine.listen(audio)), flush=True)
print('RAW', engine.transcribe(audio), flush=True)
for style in cfg['styles']:
    t = time.perf_counter()
    print('STYLE', style['name'], engine._cleanup('Hey Alex um can you send me the updated schedule by Friday I need it for the team meeting thanks Conner', style), 'SECONDS', round(time.perf_counter() - t, 2), flush=True)
