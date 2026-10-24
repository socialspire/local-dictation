# Verification — 2026-10-24

Passed:
- 9 automated behavior tests (`python -m unittest test_core -v`).
- Real cached Whisper recognition of synthesized English wake and stop phrases.
- Full rolling-audio integration: atlas write → transcription → local rewrite → stop writing.
  Exactly one result, without either command, retaining the dictated Friday meeting.
- Local Qwen3 4B rewrite checks for casual, email, and prompt wording.
- Actual Windows Ctrl+V in a disposable native editor: exact multiline Unicode match.
  See qa-insertion-result.json.
- Native settings window visually inspected; layout clipping corrected.
- Local model downloaded successfully; runtime Whisper offline-only and rewrite endpoint
  pinned to 127.0.0.1 with environment proxies and redirects disabled.

Not verified:
- Live AirPods audio (not connected as a usable default microphone during this build).
- Physical hold/toggle shortcut use with live microphone audio.
- Every external application/browser/editor; current insertion proof used a native Tk editor.
- Accuracy across accents/noisy environments or arbitrary custom wake phrases.

Known first-version limits: final text pasted on stop; rolling Whisper keyword polling
rather than a dedicated low-power wake detector; three-minute sessions; clipboard replaced
with the final result; foreground window checks do not distinguish fields in one window.


Follow-up update:
- User confirmed successful live AirPods keyword dictation.
- 14 core tests now pass, including no-pause first-word preservation and missing-mic retry.
- Actual synthetic no-pause audio returns "Immediately capture every word from the start."
- Windows Startup shortcut target/arguments verified; matching --background launch runs with no visible window.
- Worker initialization measured 3.127s; writer warm-up succeeded.
- Synthetic trigger detection moved from 1.2s to 0.8s of audio (0.4s poll cadence).
- Four separate design previews: no JavaScript errors, style/pause interactions checked,
  and no horizontal overflow at desktop and 320px content widths.
- No physical reboot was performed; live reconnect remains unverified.

Orbital release — 2026-10-24:
- User-approved first font option deployed into the native app and launched visibly.
- Oxanium, Space Grotesk and IBM Plex Mono registered privately from bundled OFL fonts.
- Gold orb rendering driven directly by microphone callback RMS, with smoothing, idle and processing states.
- Rendering is skipped while hidden or on another page; offline inference and existing shortcuts preserved.
- 16 tests pass: 14 core regressions plus direct callback-to-level and animation-state checks.
- Live Dictation, Writing styles and Settings pages visually checked in the running app.
- Startup shortcut retained; listen_on_startup remains enabled. No reboot performed.
- Current AirPods input unavailable. App visibly waits for microphone; new real-microphone animation cannot be confirmed until reconnect.
- Previous app.py, engine.py and config.json retained in backup-before-orbital.

Alive Orbital release — 2026-10-24:
- Approved motion preview ported into the native main window: 2,200 particles, organic filaments, three independently rotating rings and luminous core.
- Real microphone callback RMS controls expansion, particle motion/brightness, core pulse and outward ripples. No simulated speech envelope in live code.
- Hidden-window render suspension and offline models preserved; active saved style retained.
- 17 tests pass, including callback-to-level and real renderer quiet/loud/disconnected comparisons.
- Measured 600px rendering at 9.73 ms/frame over 30 frames.
- Relaunched actual app and visually verified new orb, AirPods Connected and Listening state.
- Fresh spoken end-to-end dictation not exercised in this release check.
- Previous UI saved at backup-before-orbital/orbital_ui-static.py.

Radio-wave refinement — 2026-10-24:
- Visual-only noise gate and nonlinear gain make ordinary speech visibly responsive without changing audio or recognition settings.
- Stronger core expansion, radial particle displacement and brighter filaments; reduced quiet drift and rotation.
- Voice-triggered expanding radio arcs decay over 1.15 seconds; quiet input never creates new waves.
- Main heading now Speak your thoughts, with Voice Dictation caption.
- 18 tests pass, including wave emission, silence decay and background noise suppression.
- Quiet/speech renderer comparison visually checked; app restarted with changes.
