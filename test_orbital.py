import queue
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from app import Worker
from engine import load_config
from orbital_ui import animation_values

class OrbitalTests(unittest.TestCase):
    def test_radio_waves_require_voice_and_decay_in_silence(self):
        from orb_renderer import OrbRenderer, voice_energy
        self.assertEqual(voice_energy(.02), 0)
        self.assertGreater(voice_energy(.2), .4)
        renderer = OrbRenderer()
        renderer.render(320, .02)
        self.assertEqual(renderer.waves, [])
        renderer.render(320, .3)
        self.assertEqual(len(renderer.waves), 1)
        renderer.render(320, 0, dt=1.2)
        self.assertEqual(renderer.waves, [])

    def test_particle_renderer_responds_only_to_available_audio(self):
        from orb_renderer import OrbRenderer
        from PIL import ImageChops
        quiet = OrbRenderer().render(400, 0, dt=0)
        loud = OrbRenderer().render(400, 1, dt=0)
        self.assertIsNotNone(ImageChops.difference(quiet, loud).getbbox())
        disconnected = OrbRenderer().render(400, 1, dt=0, enabled=False)
        self.assertEqual(quiet.tobytes(), disconnected.tobytes())

    def test_microphone_callback_updates_visual_without_inference(self):
        cfg = load_config()
        cfg.pop('input_device_name', None)
        cfg.pop('input_name_contains', None)
        worker = Worker(cfg, queue.Queue(), engine=object())
        with patch('app.sd.InputStream', return_value=MagicMock()) as stream:
            worker.open_mic()
            callback = stream.call_args.kwargs['callback']
            callback(np.full((800, 1), .025, dtype=np.float32), 800, None, None)
            self.assertAlmostEqual(worker.mic_level, .4, places=5)
            self.assertGreater(worker.last_audio_at, 0)
            self.assertEqual(len(worker.audio.get_nowait()), 800)
            callback(np.zeros((800, 1), dtype=np.float32), 800, None, None)
            self.assertEqual(worker.mic_level, 0)

    def test_loudness_and_processing_states(self):
        quiet = animation_values(0, 'idle', True, True)
        loud = animation_values(1, 'idle', True, True)
        self.assertTrue(all(b > a for a, b in zip(quiet, loud)))
        self.assertEqual(animation_values(1, 'idle', True, False), animation_values(0, 'idle', True, False))
        self.assertGreater(animation_values(0, 'working', False, False)[2], quiet[2])

if __name__ == '__main__': unittest.main()
