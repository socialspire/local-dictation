"""Smallest proof: transcribe and clean a wav file, print timings.
Usage: python proof.py sample.wav"""
import sys
import time
import wave

import numpy as np

from engine import SAMPLE_RATE, Engine, load_config


def read_wav(path):
    with wave.open(path) as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


t = time.perf_counter()
engine = Engine(load_config())
engine.warm_up()
print(f"load + warm up: {time.perf_counter() - t:.1f}s")

audio = read_wav(sys.argv[1])
print(f"audio length: {len(audio) / SAMPLE_RATE:.1f}s")
for run in (1, 2, 3):
    raw, clean, t_asr, t_llm = engine.process(audio)
    print(f"run {run}: transcribe {t_asr:.2f}s, cleanup {t_llm:.2f}s")
print(f"RAW:   {raw}")
print(f"CLEAN: {clean}")
