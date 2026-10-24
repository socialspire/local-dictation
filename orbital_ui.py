"""Orbital native interface. Assets/fonts are bundled; no network or browser runtime."""
import ctypes
import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk
from PIL import ImageTk
from orb_renderer import OrbRenderer

ASSETS = Path(__file__).parent / 'assets'
BG, PANEL, GOLD, INK, MUTED, LINE = '#000000', '#090909', '#e8b75b', '#f4f0e7', '#96938b', '#28231b'


def register_fonts():
    for path in ASSETS.glob('*.ttf'):
        ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)


def label(parent, text='', **kw):
    return tk.Label(parent, text=text, bg=kw.pop('bg', BG), fg=kw.pop('fg', INK), font=kw.pop('font', ('Space Grotesk', 11)), **kw)


def button(parent, text, command, active=False):
    return tk.Button(parent, text=text, command=command, bg='#241b0c' if active else PANEL,
        fg=GOLD if active else MUTED, activebackground='#30240f', activeforeground=GOLD,
        relief='flat', bd=0, highlightthickness=1, highlightbackground=LINE,
        font=('Space Grotesk', 11), padx=18, pady=10, cursor='hand2', takefocus=True)


def show_page(app, name):
    app.page = name
    for key, pane in app.panes.items():
        pane.grid_remove()
        app.nav[key].configure(bg='#21190c' if key == name else PANEL, fg=GOLD if key == name else MUTED)
    app.panes[name].grid(row=0, column=0, sticky='nsew')


def choose_style(app, name):
    app.cfg['default_style'] = name
    app.default_style.set(name)
    from engine import save_config
    save_config(app.cfg)
    app.send('default_style', name)
    refresh_shortcuts(app)


def refresh_shortcuts(app):
    for child in app.shortcut_frame.winfo_children(): child.destroy()
    for s in app.cfg['styles']:
        name = s['name']
        b = button(app.shortcut_frame, 'Prompts' if name == 'Prompt engineering' else name,
                   lambda n=name: choose_style(app, n), name == app.cfg['default_style'])
        b.pack(side='left', padx=2)
    selected = next(s for s in app.cfg['styles'] if s['name'] == app.cfg['default_style'])
    app.trigger_label.configure(text='Say “' + selected['keyword'] + ' write” to begin')


def build_shell(app):
    app.root.configure(bg=BG)
    app.root.geometry('1280x900')
    app.root.minsize(1000, 780)
    app.root.title('Local Dictation · Orbital')
    app.root.iconbitmap(str(Path(__file__).parent / 'local-dictation.ico'))
    style = ttk.Style(); style.theme_use('clam')
    style.configure('.', background=BG, foreground=INK, font=('Space Grotesk', 11))
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=INK)
    style.configure('TButton', background='#17130c', foreground=GOLD, padding=(14, 9), bordercolor=LINE)
    style.map('TButton', background=[('active', '#30240f')])
    for widget in ('TEntry', 'TSpinbox', 'TCombobox'):
        style.configure(widget, fieldbackground='#12100c', foreground=INK, insertcolor=GOLD, arrowcolor=GOLD, bordercolor=LINE)
        style.map(widget, fieldbackground=[('readonly', '#12100c')], foreground=[('readonly', INK)])
    style.configure('TCheckbutton', background=BG, foreground=INK)
    style.map('TCheckbutton', background=[('active', '#17130c')], foreground=[('active', GOLD)])
    style.configure('Treeview', background='#0c0b09', fieldbackground='#0c0b09', foreground=INK, rowheight=36, bordercolor=LINE)
    style.configure('Treeview.Heading', background='#17130c', foreground=GOLD)
    style.map('Treeview', background=[('selected', '#3c2b10')], foreground=[('selected', '#ffe0a0')])
    top = tk.Frame(app.root, bg=PANEL, height=57, highlightbackground=LINE, highlightthickness=1)
    top.pack(side='top', fill='x'); top.pack_propagate(False)
    label(top, '◌', bg=PANEL, fg=GOLD, font=('Oxanium', 27)).pack(side='left', padx=(24, 12))
    label(top, 'Local Dictation', bg=PANEL, font=('Oxanium', 17, 'bold')).pack(side='left')
    label(top, '●  ON DEVICE', bg=PANEL, fg=GOLD, font=('IBM Plex Mono', 9)).pack(side='right', padx=24)
    body = tk.Frame(app.root, bg=BG); body.pack(fill='both', expand=True)
    side = tk.Frame(body, bg=PANEL, width=210, highlightbackground=LINE, highlightthickness=1)
    side.pack(side='left', fill='y'); side.pack_propagate(False)
    app.panes = {}; app.nav = {}
    deck = tk.Frame(body, bg=BG); deck.pack(side='left', fill='both', expand=True)
    deck.rowconfigure(0, weight=1); deck.columnconfigure(0, weight=1)
    for name in ('Dictation', 'Writing styles', 'Settings', 'Last result'):
        pane = tk.Frame(deck, bg=BG, padx=28, pady=22)
        app.panes[name] = pane
        b = button(side, name, lambda n=name: show_page(app, n)); b.configure(anchor='w', highlightthickness=0, pady=16)
        b.pack(fill='x', padx=2, pady=(18 if name == 'Dictation' else 3, 0)); app.nav[name]=b
    bottom = tk.Frame(side,bg=PANEL); bottom.pack(side='bottom', fill='x', padx=20, pady=22)
    button(bottom, 'Quit application', app.quit).pack(fill='x', pady=(10,0), side='bottom')
    button(bottom, 'Hide to tray', app.hide).pack(fill='x', pady=(12,0), side='bottom')
    app.mic_caption=label(bottom,'AirPods',bg=PANEL,font=('Space Grotesk',11));app.mic_caption.pack(anchor='w')
    app.connection_caption=label(bottom,'Connecting…',bg=PANEL,fg=MUTED,font=('IBM Plex Mono',9));app.connection_caption.pack(anchor='w',pady=(5,0))
    home = app.panes['Dictation']
    home.rowconfigure(1,weight=1);home.columnconfigure(0,weight=1)
    heading = tk.Frame(home,bg=BG);heading.grid(row=0,column=0,sticky='ew')
    app.status_chip=label(heading,'Loading',fg=GOLD,font=('IBM Plex Mono',11),highlightbackground='#715624',highlightthickness=1,padx=15,pady=9)
    app.status_chip.pack(side='right',anchor='n')
    label(heading,'VOICE DICTATION',fg=GOLD,font=('IBM Plex Mono',9)).pack(anchor='w')
    label(heading,'Speak your thoughts.',font=('Oxanium',24,'bold')).pack(anchor='w',pady=(6,0))
    app.canvas=tk.Canvas(home,bg=BG,highlightthickness=0)
    app.canvas.grid(row=1,column=0,sticky='nsew')
    controls=tk.Frame(home,bg=BG);controls.grid(row=2,column=0,sticky='ew')
    app.trigger_label=label(controls,font=('IBM Plex Mono',11));app.trigger_label.pack(pady=(4,12))
    app.shortcut_frame=tk.Frame(controls,bg=BG);app.shortcut_frame.pack()
    app.listen_button=button(controls,'Pause listening',lambda: toggle_listening(app),True)
    app.listen_button.pack(pady=14)
    app.notice_line=label(controls,textvariable=app.notice,fg=MUTED,font=('Space Grotesk',9),wraplength=850)
    app.notice_line.pack(pady=(0,10))
    footer=tk.Frame(home,bg=BG,highlightbackground=LINE,highlightthickness=1)
    footer.grid(row=3,column=0,sticky='ew')
    label(footer,'Hold Right Ctrl to talk',fg=MUTED,font=('IBM Plex Mono',9)).pack(side='left',padx=8,pady=10)
    label(footer,'Say “stop writing” to finish',fg=MUTED,font=('IBM Plex Mono',9)).pack(side='right',padx=8,pady=10)
    for name, text in [('Writing styles','Your words. Your way.'),('Settings','Fine-tune your signal.'),('Last result','Your latest dictation.')]:
        label(app.panes[name],name.upper(),fg=GOLD,font=('IBM Plex Mono',9)).pack(anchor='w')
        label(app.panes[name],text,font=('Oxanium',23,'bold')).pack(anchor='w',pady=(8,20))
    app.orb_renderer=OrbRenderer()
    app.orb_level=0.;app.orb_clock=time.monotonic();app.orb_target=0.
    app.orb_image_id=app.canvas.create_image(0,0)
    app.page='Dictation';show_page(app,'Dictation')
    app.root.after(40,lambda:animate(app))
    # Dark native title bar without removing normal Windows window controls.
    def dark_title():
        value=ctypes.c_int(1)
        hwnd=ctypes.windll.user32.GetParent(app.root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,20,ctypes.byref(value),ctypes.sizeof(value))
    app.root.after(150,dark_title)
    return app.panes['Writing styles'],app.panes['Settings'],app.panes['Last result']


def toggle_listening(app):
    if app.worker.mode in ('hold','open','keyword'):
        app.send('stop')
    elif app.worker.mode=='idle':
        app.send('arm',not app.worker.armed)


def animation_values(level,mode,armed,connected):
    live=mode in ('hold','open','keyword')
    level=max(0.,min(1.,level)) if connected and mode!='working' else 0.
    if mode=='working':
        return 1.02,1.,10.
    if not connected or not armed and not live:
        return .52,1.,.25
    return .82 + level*.65,1.+level*.065,(1.2 if live else .5)+level*9


def animate(app):
    if not app.root.winfo_exists():return
    now=time.monotonic();dt=min(.15,now-app.orb_clock);app.orb_clock=now
    connected=app.worker.stream is not None
    mode=app.worker.mode
    stale=now-getattr(app.worker,'last_audio_at',0)> .3
    target=0. if stale else getattr(app.worker,'mic_level',0.)
    app.orb_level+=(target-app.orb_level)*(0.55 if target>app.orb_level else .17)
    app.connection_caption.configure(text='● Connected' if connected else '○ Waiting for microphone',fg='#b6bd8b' if connected else MUTED)
    name=app.cfg.get('input_device_name') or app.cfg.get('input_name_contains') or 'Default microphone'
    app.mic_caption.configure(text='AirPods Pro' if 'AirPods' in name else 'Microphone')
    active=mode in ('hold','open','keyword')
    status='Recording' if active else 'Processing' if mode=='working' else 'Loading' if mode=='loading' else 'Model error' if mode=='error' else 'Listening' if connected and app.worker.armed else 'Waiting for mic' if app.worker.armed else 'Paused'
    app.status_chip.configure(text='●  '+status)
    app.listen_button.configure(text='Finish dictation' if active else 'Processing…' if mode=='working' else 'Pause listening' if app.worker.armed else 'Resume listening',state='disabled' if mode in ('loading','working','error') else 'normal')
    if app.root.state()!='normal' or app.page!='Dictation':
        app.root.after(350,lambda:animate(app));return
    width,height=app.canvas.winfo_width(),app.canvas.winfo_height()
    size=max(64,min(width-12,height-8,760))
    image=app.orb_renderer.render(size,app.orb_level,mode=='working',dt,
                                  connected and (app.worker.armed or active))
    app.orb_photo=ImageTk.PhotoImage(image)
    app.canvas.itemconfigure(app.orb_image_id,image=app.orb_photo)
    app.canvas.coords(app.orb_image_id,width/2,height/2)
    app.root.after(40,lambda:animate(app))
