# Local Dictation

A personal Windows dictation application. Speech recognition, keyword detection,
and rewriting run on this PC. English core version, 2026-10-24.

## Launch

Double-click `start.bat` or the **Local Dictation** desktop shortcut.
The window can be hidden to the system tray. Close hides it; **Quit** exits.
Keyword listening starts ON. A Windows Startup shortcut launches the app hidden in the tray at user sign-in. Open settings from its tray icon. If AirPods are disconnected, it waits and retries automatically every three seconds. You can pause listening from the tray menu.

## Dictate into an app

Click the text field you want to write in, then:

- **Hold Right Ctrl**: speak, then release to finish.
- **Ctrl+Alt+Space**: start hands-free dictation; press again to finish.
- Enable **Listen for keywords** in Local Dictation, return to your text field,
  and say **atlas write**, **inbox write**, or **builder write**.
- Say **stop writing** to finish (configurable).
- Hands-free/keyword sessions also finish after five seconds of silence by
  default (configurable, 2–30 seconds or off).
- **Esc** cancels a session, including pending model work.

Text is pasted after the session finishes, rather than streamed word by word.
The app never presses Enter to submit a message. Each session is limited to
three minutes. Start a new session to continue.

If the foreground window changes before insertion, the result stays in
**Last result**. Focus the intended field and press **Ctrl+Alt+V** to insert it without speaking again, or use Copy result. Window checking does not identify individual text
fields within a browser tab: keep your cursor in the intended field until
insertion completes. Standard editable fields accepting Ctrl+V are supported;
elevated apps and custom editors may block it. The final text replaces the
clipboard contents and remains there for manual recovery. Clipboard history or
clipboard sync, if enabled in Windows, is controlled by Windows, not this app.

## AirPods

Connect your AirPods and select their microphone in Windows Sound settings.
In the app, open **Settings → Refresh**, choose the AirPods input
(prefer MME or WASAPI when available), then **Save controls**. Windows default
microphone is also supported. If the connection changes or a device disappears,
refresh and select it again. A disconnected microphone puts the listener into a waiting state. The app retries the saved microphone automatically; it does not silently use another microphone.

The gold orb responds to microphone loudness with a core pulse, moving particles, and expanding radio waves. Raise the silence threshold
if background noise prevents stopping; lower it if quiet speech is cut off.
The AirPods keyword-to-text path was confirmed by you on 2026-10-24. Reconnection after a physical reboot still needs a live check.

## Keywords and writing styles

Default mappings:

| Phrase | Style |
|---|---|
| atlas write | Casual: remove fillers, preserve your wording |
| inbox write | Gmail: polished email paragraphs |
| builder write | Prompt engineering: clarify instructions without answering them |

Edit a style or add your own name, keyword, and instructions. Keywords can contain
one to three English words. Names and keywords must be unique. Use distinctive
words that Whisper reliably recognizes; unusual names and homophones can be
misheard. The phrase must be recognized as **keyword + write**. Stop writing is
a reserved voice command when enabled, even if you meant to dictate those words.
Disable that option when you need the phrase literally.

Keyboard dictation uses your selected default style. Settings can be changed when
recording and keyword listening are both off. Saved in `config.json`.

## Local models and privacy

- Faster Whisper large-v3-turbo on the NVIDIA GPU, loaded from its existing local
  Hugging Face cache. Startup never downloads a model.
- Qwen3 4B Instruct (qwen3:4b-instruct) through Ollama, downloaded during setup.
  Requests go only to literal `127.0.0.1:11434`; proxies and redirects are disabled.
- Ollama must be running. If rewriting fails, the raw transcript appears in
  Last result without automatic insertion.
- Keyword detection uses rolling Whisper transcription every ~0.4 seconds while
  speech is present. This is a first-version tradeoff: custom phrases work
  without training, but recognition uses the GPU and is not an instant dedicated
  wake-word detector. Background speech can trigger a matching phrase.
- Audio stays in RAM and is not saved. Only the last result remains in the UI.
  Diagnostic logs contain errors/timings/counts, not dictated text.
- No accounts, analytics, remote inference, or runtime model downloads.
- Local rewriting can still make mistakes. Review important text before sending.

## Verification

`\.venv\Scripts\python.exe -m unittest test_core -v` tests command matching,
validation, hold release, silence stop, cancellation, command trimming, queued
last audio, and rewrite-failure recovery. `qa_stream.py` passes generated English
speech through the actual streaming keyword detection → transcription → rewrite
path. `qa_models.py` exercises each local model/style. `qa_insertion.py` is a
disposable native editor for verifying actual Ctrl+V with multiline Unicode text.
These synthetic checks do not substitute for a live AirPods test.

## Source and recovery

- `app.py`: native Tk window, system tray, global shortcuts, microphone worker,
  command detection, and insertion.
- `engine.py`: offline speech recognition, local rewriting, configuration validation.
- `backup-2026-10-24/`: original app, config, and launcher before this extension.
- `.venv/`: existing Python 3.12 environment; models are in the local caches.

This is a locally installed source application, not a portable standalone EXE.
Do not move the folder without updating the desktop shortcut.

Upstream documentation: [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
and [Qwen3 4B Instruct](https://ollama.com/library/qwen3:4b-instruct).

## Background startup and latency changes

The user Startup folder contains `Local Dictation.lnk`, pointing to this app with
`--background`. This starts at Windows user sign-in, not before login. Remove that
shortcut to disable auto-launch. `listen_on_startup` controls automatic microphone
listening, and can be changed in Settings. Ollama already has its own
Startup shortcut. No Windows security settings or other startup apps were changed.

Speech decoding is warmed before listening becomes ready. The local writing model
is warmed independently and requested to remain loaded. Keyword polling is 0.4s
instead of 1.2s; actual time also includes model inference and the spoken phrase.
The microphone stays open between sessions while armed. Queued audio recorded
during rewriting is retained for the next keyword check, subject to the existing
20-second queue capacity. The complete trigger is retained in audio and removed
from transcription afterward to protect the onset of the first dictated word.

Measured on this PC: speech-worker initialization 3.127s in the background launch
test; synthetic trigger detected at 0.8s of audio versus 1.2s with the old cadence.
These are test measurements, not a guarantee of zero latency or a cold-boot time.
`qa_rapid.py` verified a no-pause trigger-to-sentence fixture retained "Immediately"
as the first word. 14 core tests pass. Background process ran without a visible
window. AirPods were disconnected during the startup check, so physical reboot
and Bluetooth reconnection are not yet verified end to end.


## GitHub backup and current interface

See [RESTORE.md](RESTORE.md) for a fresh Windows installation, model setup,
backup exclusions and future pushes. Dependency versions are recorded in
`requirements.lock.txt`; use `config.example.json` on a fresh installation.

The Orbital interface uses bundled Oxanium, Space Grotesk and IBM Plex Mono
fonts. `orbital_ui.py` owns the interface; `orb_renderer.py` draws the voice-driven
particles, core pulse and radio waves. No simulated speech is used in the live
animation. Rendering pauses while hidden.

Current regression command: `.\.venv\Scripts\python.exe -m unittest test_core test_orbital -v`
(18 passing tests at backup time). Earlier measurements above are historical.
