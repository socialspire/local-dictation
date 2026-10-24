import tkinter as tk
import threading
import queue
import json
from pathlib import Path
from app import paste, foreground

root = tk.Tk(); root.title('Dictation QA scratchpad'); root.geometry('700x420')
tk.Label(root, text='Disposable local insertion test. No messages are sent.', font=('Segoe UI', 12)).pack(pady=12)
editor = tk.Text(root, font=('Segoe UI', 12)); editor.pack(fill='both', expand=True, padx=14)
expected = 'Local dictation insertion test.\n\nSecond paragraph: punctuation, 123, and Unicode café.'
def run():
    editor.focus_set()
    target = foreground()
    def insert():
        ok = paste(expected, target)
        root.after(500, lambda: check(ok))
    root.after(300, lambda: threading.Thread(target=insert, daemon=True).start())
def check(ok):
    actual = editor.get('1.0', 'end-1c')
    result = dict(paste_sent=ok, exact_match=actual == expected, actual=actual)
    Path('qa-insertion-result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    status.config(text='PASS: exact multiline Unicode text inserted.' if result['exact_match'] else 'FAIL: inspect output')
tk.Button(root, text='Run insertion test', command=run).pack(pady=10)
status = tk.Label(root, text='Ready'); status.pack(side='bottom')
editor.pack_forget(); editor.pack(fill='both', expand=True, padx=14)
root.mainloop()
