import copy
import queue
import unittest
from unittest.mock import patch
import numpy as np
from engine import load_config, find_command, validate_styles, SAMPLE_RATE
from app import Worker

class FakeEngine:
    def __init__(self): self.calls = []; self.cfg = {}; self.words = []
    def transcribe(self, audio): self.calls.append(len(audio)); return 'Preserved transcript.'
    def _cleanup(self, raw, style): return raw
    def listen(self, audio): return self.words

class CoreTests(unittest.TestCase):
    def worker(self):
        cfg = load_config(); cfg['voice_stop'] = False; cfg['listen_on_startup'] = False
        w = Worker(cfg, queue.Queue(), FakeEngine())
        w.mode = 'idle'; w.open_mic = lambda: None; w.close_mic = lambda: None
        return w

    def test_keyword_boundaries_and_custom_multiword(self):
        words = [dict(word=x, start=i, end=i+1) for i,x in enumerate(['Hey', 'Blue', 'Moon', 'write.', 'Hello'])]
        self.assertEqual(find_command(words, 'blue moon write'), (1, 4))
        self.assertIsNone(find_command(words, 'moonlight write'))
        self.assertIsNone(find_command(words, 'moon right'))

    def test_spoken_write_homophones(self):
        for spelling in ('write', 'right', 'rite'):
            words = [dict(word='Atlas', start=0, end=.4), dict(word=spelling, start=.4, end=.8)]
            self.assertEqual(find_command(words, 'atlas write'), (0, .8))
            self.assertIsNone(find_command(words, 'inbox write'))

    @patch('app.paste', return_value=True)
    def test_retry_uses_current_target_and_preserved_text(self, paste):
        w = self.worker(); w.last_text = 'A preserved dictation.'
        w.command('paste_last', 987)
        paste.assert_called_once_with('A preserved dictation.', 987)

    def test_duplicate_keywords_rejected(self):
        styles = load_config()['styles']; validate_styles(styles)
        styles[1]['keyword'] = styles[0]['keyword'].upper()
        with self.assertRaises(ValueError): validate_styles(styles)

    @patch('app.paste', return_value=True)
    def test_hold_waits_for_release_and_drains_pending_audio(self, paste):
        w = self.worker(); w.start('hold', 123)
        for _ in range(120): w.feed(np.zeros(800, dtype=np.float32))
        self.assertEqual(w.mode, 'hold')
        w.audio.put(np.ones(800, dtype=np.float32))
        w.command('hold_stop')
        self.assertEqual(w.engine.calls, [96800])
        self.assertEqual(w.mode, 'idle'); paste.assert_called_once()

    @patch('app.paste', return_value=True)
    def test_silence_finishes_open_mode(self, paste):
        w = self.worker(); w.cfg['silence_seconds'] = 2; w.start('open', 123)
        w.feed(np.ones(800, dtype=np.float32)*.1)
        for _ in range(40): w.feed(np.zeros(800, dtype=np.float32))
        self.assertEqual(w.mode, 'idle'); paste.assert_called_once()

    @patch('app.paste', return_value=True)
    def test_command_audio_is_excluded(self, paste):
        w = self.worker(); w.chunks = [np.ones(160000, dtype=np.float32)]; w.samples=160000
        w.start('keyword', 123, w.cfg['styles'][1], start=16000)
        w.finish(128000)
        self.assertEqual(w.engine.calls, [112000, 112000])
        self.assertEqual(w.style['name'], 'Gmail')

    @patch('app.paste', return_value=True)
    def test_cancel_never_transcribes_or_pastes(self, paste):
        w = self.worker(); w.start('hold', 123)
        w.feed(np.ones(8000, dtype=np.float32)); w.command('cancel')
        self.assertEqual(w.engine.calls, []); paste.assert_not_called()

    @patch('app.paste', return_value=True)
    def test_rewrite_failure_preserves_text_without_auto_paste(self, paste):
        w = self.worker(); w.start('open', 123); w.feed(np.ones(8000, dtype=np.float32))
        w.engine._cleanup = lambda *a: (_ for _ in ()).throw(RuntimeError('offline service unavailable'))
        w.finish(); paste.assert_not_called()
        self.assertIn(('result', 'Preserved transcript.'), list(w.events.queue))

    @patch('app.pyperclip.copy')
    @patch('app.foreground', return_value=999)
    @patch('app.user32.GetAsyncKeyState', return_value=0)
    def test_focus_change_never_pastes(self, state, foreground, clipboard):
        from app import paste
        self.assertFalse(paste('private text', 123))
        clipboard.assert_not_called()

    def test_audio_overflow_blocks_insertion(self):
        w = self.worker(); w.start('hold', 123); w.overflow = True
        with self.assertRaises(RuntimeError): w.finish()
        self.assertEqual(w.engine.calls, [])

    def test_startup_waits_and_retries_missing_airpods(self):
        w = self.worker(); w.armed = True
        w.open_mic = lambda: (_ for _ in ()).throw(RuntimeError('not connected'))
        w.ready()
        self.assertTrue(w.armed)
        self.assertEqual(w.mode, 'idle')
        self.assertGreater(w.retry_at, 0)

    def test_rearming_preserves_audio_captured_during_rewrite(self):
        w = self.worker(); w.armed = True
        w.audio.put(np.ones(800, dtype=np.float32))
        w.ready(preserve_pending=True)
        self.assertEqual(w.audio.qsize(), 1)

    @patch('app.paste', return_value=True)
    def test_full_trigger_removed_without_clipping_first_word(self, paste):
        w = self.worker(); w.start('keyword', 123, w.cfg['styles'][0])
        w.engine.transcribe = lambda audio: 'Atlas right. Immediately capture this first word.'
        w.feed(np.ones(16000, dtype=np.float32)); w.finish()
        paste.assert_called_once_with('Immediately capture this first word.', 123)

if __name__ == '__main__': unittest.main()
