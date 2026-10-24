# Restore this backup on Windows

This repository backs up the application source, bundled fonts/artwork, tests,
and the Python dependency versions installed at backup time. It is not a disk
image or a standalone executable. Personal `config.json`, microphone identity,
custom vocabulary, logs, recordings, local historical copies, the Python virtual
environment and model caches are intentionally excluded.

## Requirements

- Windows with Python 3.12 (including Tcl/Tk) and Git.
- NVIDIA GPU and a compatible current NVIDIA driver. The current app explicitly
  uses CUDA; it does not automatically fall back to CPU.
- Ollama for Windows, running locally.
- Internet access for this initial dependency/model restore. Normal dictation
  uses local models and does not download anything at runtime.

## Restore

Run in PowerShell from the folder where you want to keep the app:

```powershell
git clone https://github.com/socialspire/local-dictation.git
cd local-dictation
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item config.example.json config.json
```

Copy the example only on a fresh installation; do not overwrite an existing
personal configuration. The example uses the Windows default microphone and
the three standard writing styles. It starts with keyword listening paused.

Download the speech and writing models once:

```powershell
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('mobiuslabsgmbh/faster-whisper-large-v3-turbo')"
ollama pull qwen3:4b-instruct
```

Alternatively restore the existing Hugging Face and Ollama model caches from
your own offline disk backup. Both models must be present before normal use.

Check the code, then launch:

```powershell
.\.venv\Scripts\python.exe -m unittest test_core test_orbital -v
.\start.bat
```

The automated tests mock model inference and audio input; they do not prove a
fresh GPU/driver installation works. Test your microphone and a short dictation
after restoring. Pause keyword listening before changing microphone settings.

## Start at sign-in

Create a Windows shortcut in your user Startup folder targeting the absolute
path to `.venv\Scripts\pythonw.exe`, with the absolute path to `app.py` followed
by `--background` as its arguments. Set its working directory to the app folder.
Enable **Settings Ã¢â€ â€™ Enable keyword listening when the app starts** and save.
Ollama must also run at sign-in for rewriting. Closing the app window hides it;
the tray menu's Quit action exits it.

## Future backups

From this directory, review and push intentional source changes:

```powershell
git status
git add -A
git diff --cached
git commit -m "Describe the changes"
git push
```

Ignored personal files remain local. GitHub receives future changes only when
you push; this is not an automatic continuous backup. Keep a separate private
disk backup of `config.json` if you want to preserve custom styles/preferences.

Bundled fonts retain their original OFL license files in `assets/`. The repository is public for viewing and backup. No general open-source
license is granted for the application; bundled fonts retain their own licenses.

## Optional integration checks

`qa_stream.py`, `qa_rapid.py`, `qa_models.py` and `qa_latency.py` use local
`qa-speech.wav` / `qa-rapid.wav` synthetic fixtures, which are not included in
this backup. They also need the installed models. `qa_latency.py` saves test
microphone settings to `config.json`; run it only with a disposable configuration.
The 18 unit tests above do not require these recordings or loaded models.
