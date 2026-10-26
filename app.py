"""SocialSpire Dictation: native Windows UI, audio worker, and global controls."""
import copy
import ctypes
from ctypes import wintypes
import json
import logging
import os
import queue
import re
import threading
import time
import sys
import winsound
import tkinter as tk
from tkinter import ttk, messagebox
from collections import deque

import numpy as np
import pyperclip
import pystray
import sounddevice as sd
from PIL import Image, ImageDraw
from pynput import keyboard
from engine import HERE, SAMPLE_RATE, Engine, load_config, save_config, validate_styles, find_command

logging.basicConfig(filename=os.path.join(HERE, 'dictation.log'), level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND


def foreground():
    return user32.GetForegroundWindow()


def paste(text, target):
    """Paste only into the original foreground window; retain text on the clipboard."""
    deadline = time.monotonic() + 3
    while any(user32.GetAsyncKeyState(v) & 0x8000 for v in (16, 17, 18, 91, 92)):
        if time.monotonic() > deadline:
            logging.info('Paste blocked: modifier key still held')
            return False
        time.sleep(.02)
    if not target or foreground() != target:
        logging.info('Paste blocked: foreground changed (target=%s current=%s)', target, foreground())
        return False
    pyperclip.copy(text)
    if foreground() != target:
        logging.info('Paste blocked: foreground changed during clipboard setup')
        return False
    controller = keyboard.Controller()
    with controller.pressed(keyboard.Key.ctrl):
        controller.press('v')
        controller.release('v')
    return True


def tray_image(color='#EC3013'):
    """SocialSpire mark on ink: four bars (under 40px), tallest takes the state color."""
    image = Image.new('RGBA', (64, 64), '#201E1D')
    draw = ImageDraw.Draw(image)
    for i, height in enumerate((10, 17, 29, 50)):
        x = 6 + i * 14
        draw.rectangle((x, 58 - height, x + 9, 58), fill=color if i == 3 else '#F3F2F2')
    return image


class Worker:
    """One owner for microphone, models and dictation state. No overlapping inference."""
    def __init__(self, cfg, events, engine=None):
        self.cfg, self.events, self.engine = cfg, events, engine
        self.commands = queue.Queue()
        self.audio = queue.Queue(maxsize=400)
        self.mode = 'loading'
        self.armed = cfg.get('listen_on_startup', False)
        self.retry_at = 0
        self.stream = None
        self.running = True
        self.target = None
        self.mic_level = 0.
        self.last_audio_at = 0.
        self.last_text = ''
        self.cancelled = threading.Event()
        self.reset_audio()

    def emit(self, kind, value):
        self.events.put((kind, value))

    def status(self, text):
        self.emit('status', text)
        self.emit('mode', self.mode)

    def reset_audio(self, preserve_pending=False):
        self.chunks = []
        self.samples = 0
        self.last_voice = 0
        self.heard_voice = False
        self.last_probe = 0
        self.started = 0
        self.overflow = False
        self.last_frame = time.monotonic()
        while not preserve_pending and not self.audio.empty():
            try:
                self.audio.get_nowait()
            except queue.Empty:
                break

    def open_mic(self):
        if self.stream:
            return
        self.reset_audio()
        def receive(data, frames, timing, status):
            self.mic_level = min(1., float(np.sqrt(np.mean(data * data))) * 16)
            self.last_audio_at = time.monotonic()
            if status:
                self.overflow = True
            try:
                self.audio.put_nowait(data[:, 0].copy())
            except queue.Full:
                self.overflow = True
        device = self.cfg.get('input_device')
        preferred = self.cfg.get('input_device_name') or self.cfg.get('input_name_contains')
        if preferred:
            device = next((i for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0
                and (d['name'] == preferred if self.cfg.get('input_device_name') else preferred in d['name'])
                and sd.query_hostapis(d['hostapi'])['name'] == self.cfg.get('input_hostapi')), None)
            if device is None:
                raise RuntimeError('Waiting for your saved AirPods microphone')
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                                    blocksize=800, device=device, callback=receive)
        self.stream.start()
        self.last_frame = time.monotonic()

    def close_mic(self):
        if self.stream:
            self.stream.close()
            self.stream = None

    def ready(self, preserve_pending=False):
        self.reset_audio(preserve_pending)
        self.mode = 'idle'
        if self.armed:
            try:
                self.open_mic()
            except Exception:
                self.close_mic()
                self.retry_at = time.monotonic() + 3
                self.emit('armed', True)
                self.status('Waiting for AirPods · will reconnect automatically')
                return
        else:
            self.close_mic()
        self.emit('armed', self.armed)
        self.status('Listening for keyword + write' if self.armed else 'Ready · microphone off')
        logging.info('Ready: keyword listening=%s microphone open=%s', self.armed, self.stream is not None)

    def start(self, mode, target, style=None, start=0):
        if self.mode != 'idle':
            return
        self.open_mic()
        self.mode, self.target = mode, target
        self.style = copy.deepcopy(style or next(s for s in self.cfg['styles'] if s['name'] == self.cfg['default_style']))
        if mode == 'keyword':
            self.started = start
            self.last_voice = self.samples
        else:
            self.reset_audio()
        self.cancelled.clear()
        logging.info('Started %s dictation: target=%s', mode, target)
        threading.Thread(target=winsound.Beep, args=(880, 70), daemon=True).start()
        self.status(f'Recording · {self.style["name"]} · {mode}')

    def finish(self, end=None):
        if self.mode not in ('hold', 'open', 'keyword'):
            return
        if not self.armed:
            self.close_mic()
        if self.overflow:
            raise RuntimeError('Audio was interrupted. Dictation was not inserted; please try again.')
        # Include frames queued during command recognition; never discard the last words.
        while not self.audio.empty():
            self.chunks.append(self.audio.get_nowait())
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, dtype=np.float32)
        audio = audio[self.started:end]
        recording_mode = self.mode
        self.mode = 'working'
        self.status('Transcribing and applying your writing style…')
        try:
            if len(audio) < SAMPLE_RATE * .25 or self.cancelled.is_set():
                return
            raw = self.engine.transcribe(audio)
            if recording_mode == 'keyword':
                # Keep the full trigger in captured audio; remove it from text so an
                # imperfect end timestamp cannot eat the first dictated word.
                pattern = r'\b' + r'\W+'.join(map(re.escape, self.style['keyword'].split())) + r'\W+(?:write|right|rite)\b[\s,.!?:;-]*'
                trigger = re.search(pattern, raw[:120], re.IGNORECASE)
                if trigger:
                    raw = raw[trigger.end():].lstrip()
                else:
                    raw = self.engine.transcribe(audio[getattr(self, 'trigger_end', self.started) - self.started:])
            if self.cfg['voice_stop']:
                raw = re.sub(r'\b[sS]top[\s,]+writing[.!?\s]*$', '', raw).strip()
            if not raw or self.cancelled.is_set():
                return
            warning = ''
            try:
                clean = self.engine._cleanup(raw, self.style) if self.cfg.get('cleanup', True) else raw
            except Exception:
                logging.exception('Local style model unavailable')
                clean = raw
                warning = 'Style model unavailable; showing original transcription. '
            if self.cancelled.is_set() or not self.running:
                return
            self.last_text = clean
            self.emit('result', clean)
            # A failed rewrite is reviewable, never silently passed off as styled text.
            inserted = not warning and paste(clean, self.target)
            self.emit('notice', warning + ('Paste sent to your app. Text is also on the clipboard.' if inserted
                      else 'Text kept here. Click your target text field, then press Ctrl+Alt+V to insert the last result.'))
            threading.Thread(target=winsound.Beep, args=(660 if inserted else 330, 90), daemon=True).start()
            logging.info('Completed dictation: %d characters; paste sent=%s', len(clean), bool(inserted))
        finally:
            self.ready(preserve_pending=self.armed)

    def feed(self, chunk):
        self.last_frame = time.monotonic()
        self.chunks.append(chunk)
        self.samples += len(chunk)
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        self.emit('level', min(1, rms * 12))
        if rms >= self.cfg['noise_floor']:
            self.last_voice = self.samples
            self.heard_voice = True
        if self.mode == 'idle':
            # A bounded rolling buffer is all that survives while waiting for a keyword.
            while self.samples > SAMPLE_RATE * 9 and self.chunks:
                dropped = len(self.chunks.pop(0))
                self.samples -= dropped
                self.last_probe = max(0, self.last_probe - dropped)
                self.last_voice = max(0, self.last_voice - dropped)
        elif self.mode in ('hold', 'open', 'keyword'):
            duration = (self.samples - self.started) / SAMPLE_RATE
            self.emit('duration', duration)
            if duration >= 180:
                self.finish()
                self.emit('notice', 'Three-minute session limit reached; dictation finished.')
                return
            if (self.mode != 'hold' and self.cfg['silence_enabled'] and
                self.samples - self.last_voice >= self.cfg['silence_seconds'] * SAMPLE_RATE):
                self.finish()
                return
        should_probe = self.armed if self.mode == 'idle' else self.cfg['voice_stop']
        if not should_probe or self.mode == 'working' or self.samples - self.last_probe < SAMPLE_RATE * self.cfg.get('probe_interval', .4):
            return
        self.last_probe = self.samples
        # Skip sustained silence to avoid unnecessary GPU work and hallucinated commands.
        if self.samples - self.last_voice > SAMPLE_RATE * 2 or not self.heard_voice:
            return
        all_audio = np.concatenate(self.chunks)
        offset = max(self.started, len(all_audio) - SAMPLE_RATE * 5)
        words = self.engine.listen(all_audio[offset:])
        if self.mode == 'idle' and self.armed:
            for style in self.cfg['styles']:
                match = find_command(words, style['keyword'] + ' write')
                if match:
                    self.trigger_end = offset + int(match[1] * SAMPLE_RATE)
                    self.start('keyword', foreground(), style, max(0, offset + int(match[0] * SAMPLE_RATE) - 1600))
                    # The same utterance may include a stop command and the entire message.
                    stop = find_command(words, 'stop writing') if self.cfg['voice_stop'] else None
                    if stop and stop[0] > match[1]:
                        self.finish(offset + int(stop[0] * SAMPLE_RATE))
                    return
        elif self.mode in ('hold', 'open', 'keyword') and self.cfg['voice_stop']:
            match = find_command(words, 'stop writing')
            if match:
                self.finish(offset + int(match[0] * SAMPLE_RATE))

    def command(self, name, value=None):
        if name == 'quit':
            self.running = False
            self.close_mic()
        elif name == 'config':
            self.cfg = value
            self.engine.cfg = value
            self.close_mic()
            self.ready()
        elif name == 'default_style':
            if value in [s['name'] for s in self.cfg['styles']]:
                self.cfg['default_style'] = value
        elif name == 'arm':
            if self.mode == 'idle':
                self.armed = bool(value)
                self.ready()
        elif name == 'hold_start':
            self.start('hold', value)
        elif name == 'hold_stop' and self.mode == 'hold':
            self.finish()
        elif name == 'toggle':
            if self.mode == 'idle':
                self.start('open', value)
            elif self.mode in ('open', 'keyword', 'hold'):
                self.finish()
        elif name == 'stop':
            self.finish()
        elif name == 'paste_last' and self.mode == 'idle':
            if self.last_text:
                inserted = paste(self.last_text, value)
                self.emit('notice', 'Paste sent to your app.' if inserted else
                          'Paste blocked. Keep your target field focused and release the shortcut keys.')
            else:
                self.emit('notice', 'No dictation result yet.')
        elif name == 'cancel':
            self.close_mic()
            self.ready()
            self.emit('notice', 'Dictation cancelled.')

    def run(self):
        startup = time.perf_counter()
        try:
            if self.engine is None:
                self.engine = Engine(self.cfg)
                self.engine.warm_up()
                def warm_writer():
                    for attempt in range(6):
                        if not self.running:
                            return
                        try:
                            self.engine.warm_cleanup()
                            logging.info('Local writing model warmed')
                            return
                        except Exception:
                            time.sleep(5)
                    logging.warning('Writing model unavailable at startup; will retry on dictation')
                threading.Thread(target=warm_writer, daemon=True).start()
            self.ready()
            logging.info('Speech worker startup %.3fs', time.perf_counter() - startup)
        except Exception as exc:
            logging.exception('Model startup failed')
            self.mode = 'error'
            self.status(f'Model startup failed: {exc}')
            return
        while self.running:
            try:
                try:
                    name, value = self.commands.get_nowait()
                    self.command(name, value)
                    continue
                except queue.Empty:
                    pass
                if self.overflow:
                    raise RuntimeError('Audio interrupted or buffer full. Please try again.')
                if self.armed and not self.stream and time.monotonic() >= self.retry_at:
                    sd._terminate(); sd._initialize()
                    self.ready()
                try:
                    chunk = self.audio.get(timeout=.05)
                except queue.Empty:
                    if self.stream and time.monotonic() - self.last_frame > 4:
                        raise RuntimeError('Microphone stopped responding. Reconnect AirPods and refresh microphones.')
                    continue
                pending = [chunk]
                while not self.audio.empty():
                    pending.append(self.audio.get_nowait())
                self.feed(np.concatenate(pending) if len(pending) > 1 else chunk)
            except Exception as exc:
                logging.exception('Audio session failed')
                self.close_mic()
                self.ready()
                self.emit('notice', f'{exc}\nConnect AirPods, then refresh and choose their microphone.')


class App:
    def __init__(self, background=False):
        self.cfg = load_config()
        from orbital_ui import register_fonts
        register_fonts()
        self.root = tk.Tk()
        if background:
            self.root.withdraw()
        self.root.title('SocialSpire Dictation')
        self.root.geometry('920x780')
        self.root.minsize(820, 700)
        self.root.configure(bg='#201E1D')
        self.events = queue.Queue()
        self.worker = Worker(copy.deepcopy(self.cfg), self.events)
        self.status = tk.StringVar(value='Loading local speech model…')
        self.notice = tk.StringVar(value='Your audio and text stay on this PC. No account. No cloud inference.')
        self.armed = tk.BooleanVar(value=False)
        self.duration = tk.StringVar(value='0:00')
        self.selected = None
        self.build()
        self.tray = pystray.Icon('socialspire-dictation', tray_image('#AE1800'), 'SocialSpire Dictation', pystray.Menu(
            pystray.MenuItem('Open settings', lambda: self.events.put(('show', None)), default=True),
            pystray.MenuItem('Keyword listening', lambda: self.send('arm', not self.worker.armed),
                            checked=lambda _: self.worker.armed),
            pystray.MenuItem('Quit', lambda: self.events.put(('quit', None)))))
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.held = set()
        self.keys = keyboard.Listener(win32_event_filter=self.key_filter)
        self.keys.start()
        self.thread = threading.Thread(target=self.worker.run, daemon=True)
        self.thread.start()
        self.root.protocol('WM_DELETE_WINDOW', self.hide)
        self.root.after(80, self.poll)

    def build(self):
        from orbital_ui import build_shell
        styles_tab, settings, result_tab = build_shell(self)
        self.tree = ttk.Treeview(styles_tab, columns=('keyword',), show='tree headings', height=4)
        self.tree.heading('#0', text='Writing style'); self.tree.heading('keyword', text='Say to begin')
        self.tree.pack(fill='x'); self.tree.bind('<<TreeviewSelect>>', self.select_style)
        fields = ttk.Frame(styles_tab); fields.pack(fill='x', pady=10)
        ttk.Label(fields, text='Style name').grid(row=0, column=0, sticky='w')
        ttk.Label(fields, text='Keyword (we add “write”)').grid(row=0, column=1, sticky='w', padx=14)
        self.name = tk.StringVar(); self.keyword = tk.StringVar()
        ttk.Entry(fields, textvariable=self.name, width=32).grid(row=1, column=0, sticky='ew')
        ttk.Entry(fields, textvariable=self.keyword, width=32).grid(row=1, column=1, sticky='ew', padx=14)
        ttk.Label(styles_tab, text='How should this style rewrite your speech?').pack(anchor='w')
        self.instructions = tk.Text(styles_tab, height=4, wrap='word', bg='#2A2827', fg='#F3F2F2', insertbackground='#FF6244', font=('Archivo', 11), relief='flat', padx=10, pady=8)
        self.instructions.pack(fill='both', expand=True, pady=6)
        buttons = ttk.Frame(styles_tab); buttons.pack(side='bottom', fill='x')
        ttk.Button(buttons, text='New style', command=self.new_style).pack(side='left')
        ttk.Button(buttons, text='Delete style', command=self.delete_style).pack(side='left', padx=8)
        ttk.Button(buttons, text='Save style', command=self.save_style).pack(side='right')
        self.instructions.pack_forget()
        self.instructions.pack(fill='both', expand=True, pady=6)
        ttk.Label(settings, text='Microphone').pack(anchor='w')
        row = ttk.Frame(settings); row.pack(fill='x', pady=6)
        self.mic = ttk.Combobox(row, state='readonly', width=68); self.mic.pack(side='left', fill='x', expand=True)
        ttk.Button(row, text='Refresh', command=self.refresh_mics).pack(side='right', padx=8)
        ttk.Label(settings, text='Connect AirPods before refreshing. Choose their Hands-Free / microphone input.', foreground='#A09E9D').pack(anchor='w')
        self.start_listening = tk.BooleanVar(value=self.cfg.get('listen_on_startup', False))
        ttk.Checkbutton(settings, text='Enable keyword listening when the app starts', variable=self.start_listening).pack(anchor='w', pady=(8, 0))
        ttk.Label(settings, text='Default style for keyboard dictation').pack(anchor='w', pady=(18, 6))
        self.default_style = ttk.Combobox(settings, state='readonly', width=32)
        self.default_style.pack(anchor='w'); self.default_style.set(self.cfg['default_style'])
        self.silence_enabled = tk.BooleanVar(value=self.cfg['silence_enabled'])
        self.voice_stop = tk.BooleanVar(value=self.cfg['voice_stop'])
        ttk.Checkbutton(settings, text='Finish hands-free / keyword dictation after silence', variable=self.silence_enabled).pack(anchor='w', pady=(18, 4))
        self.silence = tk.StringVar(value=str(self.cfg['silence_seconds']))
        row = ttk.Frame(settings); row.pack(anchor='w')
        ttk.Spinbox(row, from_=2, to=30, textvariable=self.silence, width=6).pack(side='left')
        ttk.Label(row, text=' seconds (hold-to-talk always waits for key release)').pack(side='left', padx=8)
        ttk.Checkbutton(settings, text='Enable spoken “stop writing” command', variable=self.voice_stop).pack(anchor='w', pady=10)
        row = ttk.Frame(settings); row.pack(anchor='w')
        ttk.Label(row, text='Silence threshold (lower = more sensitive)').pack(side='left')
        self.noise = tk.StringVar(value=str(self.cfg['noise_floor']))
        ttk.Entry(row, textvariable=self.noise, width=8).pack(side='left', padx=8)
        ttk.Button(settings, text='Save controls', command=self.save_controls).pack(anchor='e', pady=15)
        ttk.Label(result_tab, text='Only the latest result is kept in memory. Audio is never saved.').pack(anchor='w')
        self.result = tk.Text(result_tab, wrap='word', bg='#2A2827', fg='#F3F2F2', insertbackground='#FF6244', font=('Archivo', 12), relief='flat', padx=12, pady=12)
        self.result.pack(fill='both', expand=True, pady=10)
        ttk.Button(result_tab, text='Copy result', command=lambda: pyperclip.copy(self.result.get('1.0', 'end-1c'))).pack(side='bottom', anchor='e')
        self.result.pack_forget()
        self.result.pack(fill='both', expand=True, pady=10)
        self.refresh_styles(); self.refresh_mics()

    def send(self, name, value=None):
        self.worker.commands.put((name, value))

    def editable(self):
        if self.worker.mode != 'idle' or self.worker.armed:
            messagebox.showinfo('Finish dictation first', 'Finish the current session and turn off keyword listening before changing settings.')
            return False
        return True

    def refresh_mics(self):
        if self.worker.stream:
            return
        try:
            sd._terminate(); sd._initialize()
            self.devices = [(None, 'Windows default microphone')]
            self.devices += [(i, f'{d["name"]} · {sd.query_hostapis(d["hostapi"])["name"]}')
                             for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]
            self.mic['values'] = [label for _, label in self.devices]
            index = next((i for i, (device, _) in enumerate(self.devices) if device == self.cfg.get('input_device')), 0)
            self.mic.current(index)
        except Exception as exc:
            self.notice.set(f'Unable to list microphones: {exc}')

    def refresh_styles(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for i, s in enumerate(self.cfg['styles']): self.tree.insert('', 'end', iid=str(i), text=s['name'], values=(s['keyword'] + ' write',))
        self.default_style['values'] = [s['name'] for s in self.cfg['styles']]
        self.tree.selection_set('0')
        from orbital_ui import refresh_shortcuts
        refresh_shortcuts(self)

    def select_style(self, event=None):
        selection = self.tree.selection()
        if not selection: return
        self.selected = int(selection[0]); s = self.cfg['styles'][self.selected]
        self.name.set(s['name']); self.keyword.set(s['keyword'])
        self.instructions.delete('1.0', 'end'); self.instructions.insert('1.0', s['instructions'])

    def new_style(self):
        self.tree.selection_remove(self.tree.selection())
        self.selected = None; self.name.set(''); self.keyword.set(''); self.instructions.delete('1.0', 'end')

    def persist(self):
        validate_styles(self.cfg['styles'])
        save_config(self.cfg)
        self.send('config', copy.deepcopy(self.cfg))
        self.notice.set('Settings saved on this PC.')

    def save_style(self):
        if not self.editable(): return
        previous = copy.deepcopy(self.cfg)
        try:
            s = dict(name=self.name.get().strip(), keyword=self.keyword.get().strip().lower(), instructions=self.instructions.get('1.0', 'end').strip())
            if self.selected is None: self.cfg['styles'].append(s)
            else:
                if self.cfg['default_style'] == self.cfg['styles'][self.selected]['name']:
                    self.cfg['default_style'] = s['name']; self.default_style.set(s['name'])
                self.cfg['styles'][self.selected] = s
            self.persist(); self.refresh_styles()
        except Exception as exc:
            self.cfg = previous; messagebox.showerror('Could not save', str(exc))

    def delete_style(self):
        if not self.editable() or self.selected is None: return
        if len(self.cfg['styles']) == 1:
            messagebox.showinfo('Keep a style', 'At least one style is required.'); return
        del self.cfg['styles'][self.selected]
        if self.cfg['default_style'] not in [s['name'] for s in self.cfg['styles']]:
            self.cfg['default_style'] = self.cfg['styles'][0]['name']; self.default_style.set(self.cfg['default_style'])
        self.persist(); self.refresh_styles()

    def save_controls(self):
        if not self.editable(): return
        try:
            seconds, noise = float(self.silence.get()), float(self.noise.get())
            if not 2 <= seconds <= 30 or not .001 <= noise <= .2:
                raise ValueError('Silence must be 2–30 seconds and threshold 0.001–0.2.')
            device = self.devices[self.mic.current()][0]
            sd.check_input_settings(device=device, channels=1, samplerate=SAMPLE_RATE, dtype='float32')
            self.cfg.update(input_device=device, default_style=self.default_style.get(), silence_seconds=seconds,
                            silence_enabled=self.silence_enabled.get(), voice_stop=self.voice_stop.get(), noise_floor=noise,
                            listen_on_startup=self.start_listening.get())
            if device is not None:
                info = sd.query_devices(device)
                self.cfg.update(input_device_name=info['name'], input_hostapi=sd.query_hostapis(info['hostapi'])['name'])
            else:
                self.cfg.pop('input_device_name', None)
                self.cfg.pop('input_hostapi', None)
                self.cfg.pop('input_name_contains', None)
            self.persist()
        except Exception as exc: messagebox.showerror('Check your microphone and settings', str(exc))

    def arm(self):
        if self.worker.mode != 'idle':
            self.armed.set(self.worker.armed); return
        self.send('arm', self.armed.get())

    def key_filter(self, msg, data):
        down = msg in (0x100, 0x104)
        up = msg in (0x101, 0x105)
        if not (down or up): return True
        vk = data.vkCode
        active = self.worker.mode in ('hold', 'open', 'keyword', 'working')
        if vk == 0x1b and active:
            if down:
                self.worker.cancelled.set(); self.send('cancel')
            self.keys.suppress_event()
        matched = vk == 0xA3 or (vk in (32, 86) and (vk in self.held or
            (user32.GetAsyncKeyState(17) & 0x8000 and user32.GetAsyncKeyState(18) & 0x8000)))
        if not matched: return True
        if down and vk not in self.held:
            self.held.add(vk)
            if self.worker.mode != 'working':
                self.send({0xA3: 'hold_start', 32: 'toggle', 86: 'paste_last'}[vk], foreground())
        elif up and vk in self.held:
            self.held.remove(vk)
            if vk == 0xA3: self.send('hold_stop')
        self.keys.suppress_event()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'status': self.status.set(value)
                elif kind == 'notice': self.notice.set(value)
                elif kind == 'level': self.orb_target = value
                elif kind == 'armed': self.armed.set(value)
                elif kind == 'mode':
                    color = '#EC3013' if value in ('hold', 'open', 'keyword') else '#AE1800'
                    self.tray.icon = tray_image(color)
                    self.tray.title = 'SocialSpire Dictation · ' + value
                    if value == 'idle': self.orb_target = 0
                elif kind == 'duration': self.duration.set(f'{int(value)//60}:{int(value)%60:02}')
                elif kind == 'result': self.result.delete('1.0', 'end'); self.result.insert('1.0', value)
                elif kind == 'show': self.root.deiconify(); self.root.lift()
                elif kind == 'quit': self.quit(); return
        except queue.Empty: pass
        self.root.after(80, self.poll)

    def hide(self):
        self.root.withdraw()

    def quit(self):
        self.worker.cancelled.set()
        self.worker.running = False
        self.send('quit')
        self.keys.stop(); self.tray.stop(); self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    ctypes.windll.kernel32.CreateMutexW.restype = wintypes.HANDLE
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, 'Local\\ConnerDictation')
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, 'SocialSpire Dictation is already running. Open it from the system tray.', 'SocialSpire Dictation', 0)
    else:
        App(background='--background' in sys.argv).run()
