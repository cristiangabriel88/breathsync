import os, sys, time, re
import customtkinter as ctk
from tkinter import messagebox
from mutagen import File as MutagenFile
import pygame

APP_TITLE = "BreathSync"
SEARCH_DIR = "rhythms"
BACKING_DIR = "backing"
POLL_MS = 150
WINDOW_W, WINDOW_H = 900, 750

class Rhythm:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.duration = self._get_duration()
        self.started_at = None
        self.paused = False
        self.accumulated_ms = 0
    def _get_duration(self):
        try:
            mf = MutagenFile(self.path)
            if mf and mf.info and getattr(mf.info, "length", None):
                return float(mf.info.length)
        except:
            pass
        return 0.0
    def reset(self):
        self.started_at = None
        self.paused = False
        self.accumulated_ms = 0
    def on_play_started(self):
        self.started_at = time.time()
        self.paused = False
    def on_pause(self):
        if self.started_at is not None and not self.paused:
            self.accumulated_ms += int((time.time() - self.started_at) * 1000)
            self.paused = True
            self.started_at = None
    def on_unpause(self):
        if self.paused:
            self.paused = False
            self.started_at = time.time()
    def current_ms(self):
        if self.started_at is not None and not self.paused:
            return self.accumulated_ms + int((time.time() - self.started_at) * 1000)
        return self.accumulated_ms

class TrackRow(ctk.CTkFrame):
    def __init__(self, master, rhythm, on_select, on_seek, selected=False):
        super().__init__(master, fg_color="#14171c", corner_radius=16)
        self.rhythm = rhythm
        self.on_select = on_select
        self.on_seek = on_seek
        self.selected = selected
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        root = self.winfo_toplevel()
        self.title = ctk.CTkLabel(self, text=rhythm.name, font=root.ui_font_bold)
        self.meta = ctk.CTkLabel(self, text=self._fmt_meta(), text_color="#9aa4b2", font=root.ui_font_md_bold)
        self.pb = ctk.CTkProgressBar(self, height=10, corner_radius=8, progress_color="#5aa3ff")
        self.title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.meta.grid(row=1, column=0, sticky="w", padx=16, pady=(2, 8))
        self.pb.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.pb.set(0)
        self._apply_selected_style()
        self.bind("<Button-1>", self._click)
        self.title.bind("<Button-1>", self._click)
        self.meta.bind("<Button-1>", self._click)
        self.pb.bind("<Button-1>", self._seek_event)
        self.pb.bind("<B1-Motion>", self._seek_event)
    def _fmt_meta(self):
        if self.rhythm.duration <= 0:
            return "Unknown length"
        total = int(self.rhythm.duration)
        m_rem, s_rem = divmod(total, 60)
        m_tot, s_tot = divmod(total, 60)
        return f"{m_rem:02d}:{s_rem:02d} / {m_tot:02d}:{s_tot:02d}"
    def _click(self, _): self.on_select(self)
    def _seek_event(self, event):
        w = max(1, self.pb.winfo_width())
        frac = min(1.0, max(0.0, event.x / w))
        self.on_seek(self, frac)
    def set_progress(self, frac): self.pb.set(max(0.0, min(1.0, frac)))
    def set_selected(self, val):
        self.selected = val
        self._apply_selected_style()
    def _apply_selected_style(self):
        if self.selected:
            self.configure(fg_color="#1c222b"); self.title.configure(text_color="#ffffff")
        else:
            self.configure(fg_color="#14171c"); self.title.configure(text_color="#e6edf3")
    def update_meta(self, elapsed_ms):
        total = self.rhythm.duration
        if total <= 0:
            self.meta.configure(text="Unknown length"); return
        elapsed = elapsed_ms / 1000.0
        remaining = max(0, total - elapsed)
        m_rem, s_rem = divmod(int(remaining), 60)
        m_tot, s_tot = divmod(int(total), 60)
        self.meta.configure(text=f"{m_rem:02d}:{s_rem:02d} / {m_tot:02d}:{s_tot:02d}")

class BackingRow(ctk.CTkFrame):
    def __init__(self, master, index, name, duration, on_click, on_volume, on_seek):
        super().__init__(master, fg_color="#3b414d", corner_radius=12)
        root = self.winfo_toplevel()
        self.index = index
        self.duration = duration
        self.on_click = on_click
        self.on_volume = on_volume
        self.on_seek = on_seek
        self.selected = False
        self.playing = False
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.name_label = ctk.CTkLabel(self, text=name, font=root.ui_font_small_bold)
        self.time_label = ctk.CTkLabel(self, text="00:00 / 00:00", text_color="#9aa4b2", font=root.ui_font_small)
        self.pb = ctk.CTkProgressBar(self, height=8, corner_radius=6, progress_color="#5aa3ff")
        self.pb.set(0)
        self.slider = ctk.CTkSlider(self, from_=0.0, to=1.0, number_of_steps=100, command=self._changed, height=14, corner_radius=8)
        self.slider.set(0.5)
        self.vol_pct = ctk.CTkLabel(self, text="50%", text_color="#9aa4b2", font=root.ui_font_small)
        self.name_label.grid(row=0, column=0, padx=12, pady=(8,0), sticky="w")
        self.time_label.grid(row=0, column=2, padx=12, pady=(8,0), sticky="e")
        self.pb.grid(row=1, column=0, columnspan=3, padx=12, pady=(6,0), sticky="ew")
        self.slider.grid(row=2, column=0, columnspan=2, padx=12, pady=(6,8), sticky="ew")
        self.vol_pct.grid(row=2, column=2, padx=12, pady=(6,8), sticky="e")
        self.bind("<Button-1>", self._click)
        self.name_label.bind("<Button-1>", self._click)
        self.time_label.bind("<Button-1>", self._click)
        self.pb.bind("<Button-1>", self._seek_event)
        self.pb.bind("<B1-Motion>", self._seek_event)
    def _changed(self, v):
        pct = int(float(v) * 100)
        self.vol_pct.configure(text=f"{pct}%")
        self.on_volume(self.index, float(v))
    def _click(self, _):
        self.on_click(self.index)
    def _seek_event(self, event):
        w = max(1, self.pb.winfo_width())
        frac = min(1.0, max(0.0, event.x / w))
        self.on_seek(self.index, frac)
    def set_progress(self, frac):
        self.pb.set(max(0.0, min(1.0, frac)))
    def update_time(self, elapsed_ms):
        if self.duration <= 0:
            self.time_label.configure(text="00:00 / 00:00")
            return
        elapsed = int((elapsed_ms // 1000) % int(self.duration))
        rem = max(0, int(self.duration) - elapsed)
        em, es = divmod(elapsed, 60)
        rm, rs = divmod(rem, 60)
        self.time_label.configure(text=f"{em:02d}:{es:02d} / {rm:02d}:{rs:02d}")
    def set_style(self, selected, playing):
        self.selected = selected
        self.playing = playing
        if selected:
            self.configure(fg_color="#1c222b")
            self.name_label.configure(text_color="#ffffff")
        else:
            self.configure(fg_color="#3b414d")
            self.name_label.configure(text_color="#e6edf3")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title(APP_TITLE)
        icon_path = os.path.join(self._base_folder(), "assets", "images", "logo_without_text.png")

        if os.path.exists(icon_path):
            try:
                self.iconphoto(False, ctk.CTkImage(light_image=None, dark_image=None, size=(32,32), file=icon_path))
            except:
                from tkinter import PhotoImage
        self.iconphoto(False, PhotoImage(file=icon_path))

        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(WINDOW_W, WINDOW_H)
        self.after(0, lambda: self.state("zoomed"))
        self.fullscreen = False
        self.fade_secs = 3.0
        self._audio_init()
        self.rhythms = self._load_rhythms()
        if not self.rhythms:
            messagebox.showerror(APP_TITLE, f"No MP3 found in .\\{SEARCH_DIR}")
            self.destroy(); return
        self.backing_sounds = self._load_backings()
        self.backing_channels = [pygame.mixer.Channel(i) for i in range(3)]
        self.backing_arrays = self._load_backing_arrays()
        self.backing_freq = (pygame.mixer.get_init() or (44100, 0, 2))[0]
        self.backing_states = []
        for i, p in enumerate(self._backing_paths()):
            dur = self._get_duration_safe(p) if p else 0.0
            self.backing_states.append({"playing": False, "paused": False, "started_at": None, "acc_ms": 0, "duration": dur, "slice_playing": False})
        while len(self.backing_states) < 3:
            self.backing_states.append({"playing": False, "paused": False, "started_at": None, "acc_ms": 0, "duration": 0.0, "slice_playing": False})
        self.selected_backing_idx = 0
        self.current_idx = 0
        self.playing = False

        self.wrapper = ctk.CTkFrame(self, fg_color="transparent")
        self.wrapper.pack(fill="both", expand=True)
        self.content = ctk.CTkFrame(self.wrapper, fg_color="transparent", width=WINDOW_W, height=WINDOW_H)
        self.content.pack_propagate(False)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        font_path = os.path.join(self._base_folder(), "assets", "fonts", "Asimovian-Regular.ttf")
        self.brand_font = self._load_brand_font(font_path, "Asimovian", 32, "bold")

        mono_path = os.path.join(self._base_folder(), "assets", "fonts", "Roboto_Mono", "RobotoMono-VariableFont_wght.ttf")
        self._register_font(mono_path)
        self.ui_font = ctk.CTkFont(family="Roboto Mono", size=13)
        self.ui_font_bold = ctk.CTkFont(family="Roboto Mono", size=13, weight="bold")
        self.ui_font_small = ctk.CTkFont(family="Roboto Mono", size=12)
        self.ui_font_small_bold = ctk.CTkFont(family="Roboto Mono", size=12, weight="bold")
        self.ui_font_md_bold = ctk.CTkFont(family="Roboto Mono", size=16, weight="bold")
        self.ui_font_h2_bold = ctk.CTkFont(family="Roboto Mono", size=18, weight="bold")
        self.ui_font_section_bold = ctk.CTkFont(family="Roboto Mono", size=20, weight="bold")

        topbar = ctk.CTkFrame(self.content, fg_color="transparent")
        topbar.pack(fill="x", padx=16, pady=(8,4))
        topbar.grid_columnconfigure(0, weight=1)
        topbar.grid_columnconfigure(1, weight=0)

        self.brand_label = ctk.CTkLabel(topbar, text="BreathSync", font=self.brand_font)
        self.brand_label.grid(row=0, column=0, sticky="w")

        self.play_btn = ctk.CTkButton(
            topbar,
            text="Play",
            width=180,
            height=40,
            corner_radius=20,
            font=self.ui_font_md_bold,
            command=self._toggle,
            fg_color="#5e1eff",
            hover_color="#420b82",
            text_color="#ffffff"
        )
        self.play_btn.grid(row=0, column=1, sticky="e", padx=(8,0))

        self.section_label = ctk.CTkLabel(topbar, text="Rhythms", font=self.ui_font_section_bold)
        self.section_label.grid(row=1, column=0, sticky="w", pady=(6,0))

        fader = ctk.CTkFrame(topbar, fg_color="transparent")
        fader.grid(row=1, column=1, sticky="e", pady=(6,0))
        self.fade_label = ctk.CTkLabel(fader, text="Fade (3s)", font=self.ui_font)
        self.fade_label.pack(side="left", padx=(0,8))
        self.fade_slider = ctk.CTkSlider(fader, from_=1, to=9, number_of_steps=8, command=self._fade_changed)
        self.fade_slider.set(3)
        self.fade_slider.pack(side="left", ipadx=40)

        self.list_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.list_container.pack(fill="x", padx=16)
        self.rows = []
        for i, r in enumerate(self.rhythms):
            row = TrackRow(self.list_container, r, on_select=self._on_row_select, on_seek=self._on_seek_request, selected=(i == 0))
            row.title.configure(text=f"Rhythm {i+1}")
            row.pack(fill="x", pady=6)
            self.rows.append(row)
        for rw in self.rows:
            rw.set_progress(0)
            rw.update_meta(0)

        self.backing_header = ctk.CTkLabel(self.content, text="Backing Tracks", font=self.ui_font_h2_bold)
        self.backing_header.pack(anchor="w", padx=20, pady=(6, 0))
        self.backing_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.backing_container.pack(fill="x", padx=16, pady=(4, 12))
        self.backing_rows = []
        names = [os.path.basename(p) if p else "—" for p in self._backing_paths()]
        for i in range(3):
            name = names[i] if i < len(names) else "—"
            dur = self.backing_states[i]["duration"] if i < len(self.backing_states) else 0.0
            row = BackingRow(self.backing_container, i, name, dur, on_click=self._select_backing, on_volume=self._set_backing_volume, on_seek=self._seek_backing)
            row.pack(fill="x", pady=6)
            self.backing_rows.append(row)

        self._apply_initial_backing_volumes()
        self._update_backing_row_styles()
        self._load_current_into_mixer()
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.bind("<Escape>", self._exit_fullscreen)
        self.bind_all("<space>", self._on_space)
        self.after(POLL_MS, self._tick)
        self.after(0, self._apply_windowed_layout)

    def _load_brand_font(self, path, family_hint, size, weight):
        try:
            self.tk.call('font', 'create', 'BrandFont', '-family', family_hint, '-size', size, '-weight', weight, '-file', path)
            return ctk.CTkFont(family='BrandFont', size=size, weight=weight)
        except Exception:
            if os.path.isfile(path) and sys.platform.startswith('win'):
                import ctypes
                ctypes.windll.gdi32.AddFontResourceExW(path, 16, 0)
            return ctk.CTkFont(family=family_hint, size=size, weight=weight)

    def _register_font(self, path):
        if os.path.isfile(path) and sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.gdi32.AddFontResourceExW(path, 16, 0)

    def _fade_changed(self, v):
        self.fade_secs = float(v)
        self.fade_label.configure(text=f"Fade ({int(self.fade_secs)}s)")

    def _apply_fullscreen_layout(self):
        self.wrapper.pack(fill="both", expand=True)
        self.content.configure(width=0, height=0)
        self.content.place(x=0, y=0, relwidth=1, relheight=1)

    def _apply_windowed_layout(self):
        self.wrapper.pack(fill="both", expand=True)
        self.content.configure(width=WINDOW_W, height=WINDOW_H)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.attributes("-fullscreen", True)
            self._apply_fullscreen_layout()
        else:
            self.attributes("-fullscreen", False)
            self.geometry(f"{WINDOW_W}x{WINDOW_H}")
            self._apply_windowed_layout()

    def _exit_fullscreen(self, event=None):
        if self.fullscreen:
            self.fullscreen = False
            self.attributes("-fullscreen", False)
            self.geometry(f"{WINDOW_W}x{WINDOW_H}")
            self._apply_windowed_layout()

    def _on_space(self, event=None):
        self._toggle()
        return "break"

    def _audio_init(self): pygame.mixer.init()
    def _base_folder(self):
        return os.path.dirname(sys.executable) if getattr(sys,"frozen",False) else os.path.dirname(os.path.abspath(__file__))
    def _folder(self, name):
        folder = os.path.join(self._base_folder(), name)
        os.makedirs(folder, exist_ok=True)
        return folder
    def _rhythms_folder(self): return self._folder(SEARCH_DIR)
    def _backing_folder(self): return self._folder(BACKING_DIR)
    def _load_rhythms(self):
        def nkey(p):
            name = os.path.basename(p)
            return [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', name)]
        folder = self._rhythms_folder()
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".mp3")]
        files.sort(key=nkey)
        files = files[:3]
        return [Rhythm(p) for p in files]
    def _backing_paths(self):
        files = [os.path.join(self._backing_folder(), f) for f in os.listdir(self._backing_folder()) if f.lower().endswith(".mp3")]
        files.sort()
        return files[:3]
    def _load_backings(self):
        paths = self._backing_paths()
        sounds = []
        for p in paths:
            try:
                sounds.append(pygame.mixer.Sound(p))
            except:
                sounds.append(None)
        while len(sounds) < 3:
            sounds.append(None)
        return sounds
    def _load_backing_arrays(self):
        arrs = []
        for snd in self.backing_sounds:
            try:
                import pygame.sndarray as sndarray
                if snd is not None:
                    arrs.append(sndarray.array(snd))
                else:
                    arrs.append(None)
            except:
                arrs.append(None)
        while len(arrs) < 3:
            arrs.append(None)
        return arrs
    def _get_duration_safe(self, path):
        try:
            mf = MutagenFile(path)
            if mf and mf.info and getattr(mf.info, "length", None):
                return float(mf.info.length)
        except:
            pass
        try:
            snd = pygame.mixer.Sound(path)
            return float(snd.get_length())
        except:
            return 0.0
    def _apply_initial_backing_volumes(self):
        for i, row in enumerate(self.backing_rows):
            v = row.slider.get()
            self.backing_channels[i].set_volume(v)
    def _set_backing_volume(self, idx, v):
        self.backing_channels[idx].set_volume(float(v))
    def _select_backing(self, idx):
        if idx == self.selected_backing_idx:
            st = self.backing_states[idx]
            if st["playing"] and not st["paused"]:
                self._pause_backing()
            elif st["playing"] and st["paused"] and self.playing:
                self._resume_backing()
            else:
                if self.playing:
                    self._start_backing_current()
            self._update_backing_row_styles()
            return
        old = self.selected_backing_idx
        if old != idx:
            st_old = self.backing_states[old]
            ch_old = self.backing_channels[old]
            if st_old["playing"] and not st_old["paused"] and st_old["started_at"] is not None:
                st_old["acc_ms"] += int((time.time() - st_old["started_at"]) * 1000)
            ch_old.stop()
            st_old["playing"] = False
            st_old["paused"] = False
            st_old["started_at"] = None
        self.selected_backing_idx = idx
        self._update_backing_row_styles()
        if self.playing:
            self._start_backing_current()
    def _update_backing_row_styles(self):
        for i, row in enumerate(self.backing_rows):
            st = self.backing_states[i]
            row.set_style(i == self.selected_backing_idx, st["playing"] and not st["paused"])
    def _start_backing_current(self):
        i = self.selected_backing_idx
        snd = self.backing_sounds[i] if i < len(self.backing_sounds) else None
        if not snd:
            return
        st = self.backing_states[i]
        for j, ch in enumerate(self.backing_channels):
            if j != i:
                ch.stop()
                self.backing_states[j]["playing"] = False
                self.backing_states[j]["paused"] = False
                self.backing_states[j]["started_at"] = None
        self._play_backing_from(i, st["acc_ms"])
        st["paused"] = False
        st["playing"] = True
        self._update_backing_row_styles()
    def _play_backing_from(self, idx, start_ms):
        st = self.backing_states[idx]
        ch = self.backing_channels[idx]
        base = self.backing_sounds[idx]
        arr = self.backing_arrays[idx]
        dur = st["duration"]
        if not base or not dur:
            return
        start_ms = max(0, min(int(dur * 1000) - 1, int(start_ms)))
        try:
            if arr is not None:
                import pygame.sndarray as sndarray
                total_frames = arr.shape[0]
                start_frame = int((start_ms / 1000.0) * self.backing_freq)
                start_frame = max(0, min(total_frames - 1, start_frame))
                slice_arr = arr[start_frame:]
                if slice_arr.size > 0:
                    slice_sound = sndarray.make_sound(slice_arr.copy())
                    ch.play(slice_sound, loops=0)
                    st["slice_playing"] = True
                    st["started_at"] = time.time()
                    vol = self.backing_rows[idx].slider.get()
                    ch.set_volume(vol)
                    return
            ch.play(base, loops=0)
            st["slice_playing"] = False
            st["started_at"] = time.time()
            vol = self.backing_rows[idx].slider.get()
            ch.set_volume(vol)
        except:
            ch.play(base, loops=0)
            st["slice_playing"] = False
            st["started_at"] = time.time()
            vol = self.backing_rows[idx].slider.get()
            ch.set_volume(vol)
    def _seek_backing(self, idx, frac):
        st = self.backing_states[idx]
        dur = st["duration"]
        if dur <= 0:
            return
        target_ms = int(max(0.0, min(1.0, frac)) * dur * 1000)
        st["acc_ms"] = target_ms
        st["started_at"] = None
        if st["playing"] and not st["paused"] and idx == self.selected_backing_idx and self.playing:
            self._play_backing_from(idx, target_ms)
        row = self.backing_rows[idx]
        row.set_progress(target_ms / (dur * 1000))
        row.update_time(target_ms)
        self._update_backing_row_styles()
    def _pause_backing(self):
        i = self.selected_backing_idx
        st = self.backing_states[i]
        ch = self.backing_channels[i]
        if st["playing"] and not st["paused"]:
            ch.pause()
            if st["started_at"] is not None:
                st["acc_ms"] += int((time.time() - st["started_at"]) * 1000)
            st["started_at"] = None
            st["paused"] = True
            self._update_backing_row_styles()
    def _resume_backing(self):
        i = self.selected_backing_idx
        st = self.backing_states[i]
        ch = self.backing_channels[i]
        if st["playing"] and st["paused"]:
            self._play_backing_from(i, st["acc_ms"])
            st["paused"] = False
            self._update_backing_row_styles()
    def _fade_out_current(self):
        ms = int(self.fade_secs * 1000)
        pygame.mixer.music.fadeout(ms)
    def _fade_in_next(self):
        ms = int(self.fade_secs * 1000)
        pygame.mixer.music.play(fade_ms=ms)
    def _on_row_select(self, row_widget):
        idx = self.rows.index(row_widget)
        if idx == self.current_idx:
            return
        was_playing = self.playing
        if self.playing:
            self._fade_out_current()
        for r in self.rhythms:
            r.reset()
        self.current_idx = idx
        for i, rw in enumerate(self.rows):
            rw.set_selected(i == self.current_idx)
            rw.set_progress(0)
            rw.update_meta(0)
        self._load_current_into_mixer()
        if was_playing:
            self._fade_in_next()
            self.rhythms[self.current_idx].on_play_started()
    def _load_current_into_mixer(self):
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.rhythms[self.current_idx].path)
        except:
            messagebox.showerror(APP_TITLE, f"Failed to load: {os.path.basename(self.rhythms[self.current_idx].path)}")
            self.playing = False
            self.play_btn.configure(text="Play")
    def _play(self):
        try:
            self._fade_in_next()
            self.rhythms[self.current_idx].on_play_started()
            self.playing = True
            self.play_btn.configure(text="Pause")
            self._start_backing_current()
        except:
            messagebox.showerror(APP_TITLE, "Playback error")
    def _pause(self):
        pygame.mixer.music.pause()
        pygame.mixer.pause()
        self.rhythms[self.current_idx].on_pause()
        self._pause_backing()
        self.playing = False
        self.play_btn.configure(text="Play")
    def _unpause(self):
        pygame.mixer.music.unpause()
        pygame.mixer.unpause()
        self.rhythms[self.current_idx].on_unpause()
        self._resume_backing()
        self.playing = True
        self.play_btn.configure(text="Pause")
    def _toggle(self):
        r = self.rhythms[self.current_idx]
        if not self.playing and r.started_at is None and r.accumulated_ms == 0:
            self._play()
        elif self.playing:
            self._pause()
        else:
            self._unpause()
    def _on_seek_request(self, row_widget, frac):
        idx = self.rows.index(row_widget)
        if idx != self.current_idx:
            self._on_row_select(row_widget)
        r = self.rhythms[self.current_idx]
        if r.duration <= 0:
            return
        target_ms = int(max(0.0, min(1.0, frac)) * r.duration * 1000)
        r.accumulated_ms = target_ms
        r.started_at = time.time() if self.playing and not r.paused else None
        if self.playing:
            try:
                pygame.mixer.music.play(start=target_ms / 1000.0)
                r.on_play_started()
                r.accumulated_ms = target_ms
            except:
                pass
        else:
            try:
                pygame.mixer.music.play(start=target_ms / 1000.0)
                pygame.mixer.music.pause()
                r.paused = True
                r.started_at = None
            except:
                pass
        self.rows[self.current_idx].set_progress(target_ms / (r.duration * 1000))
        self.rows[self.current_idx].update_meta(target_ms)
    def _tick(self):
        try:
            r = self.rhythms[self.current_idx]
            if r.duration > 0:
                cur_ms = r.current_ms()
                frac = cur_ms / (r.duration * 1000)
                self.rows[self.current_idx].set_progress(frac)
                self.rows[self.current_idx].update_meta(cur_ms)
                if self.playing and not pygame.mixer.music.get_busy():
                    self._on_track_end()
            for i, row in enumerate(self.backing_rows):
                st = self.backing_states[i]
                dur = st["duration"] if st["duration"] else 0.0
                if dur > 0 and st["playing"]:
                    if not st["paused"] and st["started_at"] is not None:
                        cur = st["acc_ms"] + int((time.time() - st["started_at"]) * 1000)
                    else:
                        cur = st["acc_ms"]
                    frac = (cur % int(dur * 1000)) / (dur * 1000)
                    row.set_progress(frac)
                    row.update_time(cur)
                    ch = self.backing_channels[i]
                    if st["slice_playing"] and not ch.get_busy() and not st["paused"]:
                        base = self.backing_sounds[i]
                        if base:
                            ch.play(base, loops=0)
                            st["slice_playing"] = False
                            st["started_at"] = time.time()
                            st["acc_ms"] = 0
                    if i == self.selected_backing_idx and not ch.get_busy() and not st["paused"]:
                        self._on_backing_end()
        finally:
            self.after(POLL_MS, self._tick)

    def _on_backing_end(self):
        i = self.selected_backing_idx
        st = self.backing_states[i]
        st["playing"] = False
        st["paused"] = False
        st["started_at"] = None
        st["acc_ms"] = 0
        if i + 1 < len(self.backing_sounds) and self.backing_sounds[i + 1] is not None:
            self.selected_backing_idx = i + 1
            self._start_backing_current()
        self._update_backing_row_styles()

    def _on_track_end(self):
        self._fade_out_current()
        self.rhythms[self.current_idx].reset()
        if self.current_idx < len(self.rhythms) - 1:
            self.current_idx += 1
            for i, rw in enumerate(self.rows):
                rw.set_selected(i == self.current_idx)
                rw.set_progress(0)
                rw.update_meta(0)
            self._load_current_into_mixer()
            self._fade_in_next()
            self.rhythms[self.current_idx].on_play_started()
            self.playing = True
            self.play_btn.configure(text="Pause")
        else:
            self.playing = False
            self.play_btn.configure(text="Play")
            self.rows[self.current_idx].set_progress(0)
            self.rows[self.current_idx].update_meta(0)

if __name__ == "__main__":
    App().mainloop()
