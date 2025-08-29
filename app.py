import os, sys, time
import customtkinter as ctk
from tkinter import messagebox
from mutagen import File as MutagenFile
import pygame

APP_TITLE = "BreathSync"
SEARCH_DIR = "rhythms"
BACKING_DIR = "backing"
POLL_MS = 150
WINDOW_W, WINDOW_H = 800, 700

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
        self.title = ctk.CTkLabel(self, text=rhythm.name, font=("Segoe UI", 13, "bold"))
        self.meta = ctk.CTkLabel(self, text=self._fmt_meta(), text_color="#9aa4b2", font=("Segoe UI", 16, "bold"))
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
    def __init__(self, master, name, on_volume):
        super().__init__(master, fg_color="#14171c", corner_radius=12)
        self.label = ctk.CTkLabel(self, text=name, font=("Segoe UI", 12, "bold"))
        self.val_label = ctk.CTkLabel(self, text="50%", text_color="#9aa4b2", font=("Segoe UI", 12))
        self.slider = ctk.CTkSlider(self, from_=0.0, to=1.0, number_of_steps=100, command=self._changed, height=14, corner_radius=8)
        self.on_volume = on_volume
        self.slider.set(0.5)
        self.grid_columnconfigure(1, weight=1)
        self.label.grid(row=0, column=0, padx=12, pady=10, sticky="w")
        self.slider.grid(row=0, column=1, padx=12, pady=10, sticky="ew")
        self.val_label.grid(row=0, column=2, padx=12, pady=10, sticky="e")
    def _changed(self, v):
        pct = int(float(v) * 100)
        self.val_label.configure(text=f"{pct}%")
        self.on_volume(float(v))

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.title(APP_TITLE)
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(WINDOW_W, WINDOW_H)
        self.fullscreen = False
        self.fade_secs = 3.0
        self._audio_init()
        self.rhythms = self._load_rhythms()
        if not self.rhythms:
            messagebox.showerror(APP_TITLE, f"No MP3 found in .\\{SEARCH_DIR}")
            self.destroy(); return
        self.backing_sounds = self._load_backings()
        self.backing_channels = [pygame.mixer.Channel(i) for i in range(3)]
        self.current_idx = 0
        self.playing = False
        self._pending_seek_ms = None

        self.wrapper = ctk.CTkFrame(self, fg_color="transparent")
        self.wrapper.pack(fill="both", expand=True)
        self.content = ctk.CTkFrame(self.wrapper, fg_color="transparent", width=WINDOW_W, height=WINDOW_H)
        self.content.pack_propagate(True)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        topbar = ctk.CTkFrame(self.content, fg_color="transparent")
        topbar.pack(fill="x", padx=16, pady=(8,4))
        self.header = ctk.CTkLabel(topbar, text="BreathSync • Rhythms", font=("Segoe UI", 23, "bold"))
        self.header.pack(side="left")
        self.fs_btn = ctk.CTkButton(topbar, text="⛶", width=40, command=self._toggle_fullscreen)
        self.fs_btn.pack(side="right", padx=(8,0))
        self.fade_label = ctk.CTkLabel(topbar, text="Fade (3s)")
        self.fade_label.pack(side="right", padx=8)
        self.fade_slider = ctk.CTkSlider(topbar, from_=1, to=9, number_of_steps=8, command=self._fade_changed)
        self.fade_slider.set(3)

        self.fade_slider.pack(side="right", padx=8, ipadx=40)

        self.list_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.list_container.pack(fill="x", padx=16)
        self.rows = []
        for i, r in enumerate(self.rhythms):
            row = TrackRow(self.list_container, r, on_select=self._on_row_select, on_seek=self._on_seek_request, selected=(i == 0))
            row.pack(fill="x", pady=6)
            self.rows.append(row)
        for rw in self.rows:
            rw.set_progress(0)
            rw.update_meta(0)

        self.controls = ctk.CTkFrame(self.content, fg_color="transparent")
        self.controls.pack(fill="x", padx=16, pady=6)
        self.play_btn = ctk.CTkButton(self.controls, text="Play", width=180, height=40, corner_radius=20, font=("Segoe UI",16,"bold"), command=self._toggle)
        self.play_btn.pack(pady=8)

        self.backing_header = ctk.CTkLabel(self.content, text="Backing Tracks", font=("Segoe UI", 18, "bold"))
        self.backing_header.pack(anchor="w", padx=20, pady=(6, 0))
        self.backing_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.backing_container.pack(fill="x", padx=16, pady=(4, 12))
        self.backing_rows = []
        names = [os.path.basename(p) if p else "—" for p in self._backing_paths()]
        for i in range(3):
            name = names[i] if i < len(names) else "—"
            row = BackingRow(self.backing_container, name, on_volume=self._make_volume_handler(i))
            row.pack(fill="x", pady=6)
            self.backing_rows.append(row)

        self._apply_initial_backing_volumes()
        self._load_current_into_mixer()
        self.after(POLL_MS, self._tick)

    def _fade_changed(self, v):
        self.fade_secs = float(v)
        self.fade_label.configure(text=f"Fade ({int(self.fade_secs)}s)")

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.attributes("-fullscreen", True)
            self.content.place(relx=0.5, rely=0.5, anchor="center")
            self.content.configure(width=WINDOW_W, height=WINDOW_H)
            self.content.pack_propagate(True)
        else:
            self.attributes("-fullscreen", False)
            self.geometry(f"{WINDOW_W}x{WINDOW_H}")
            self.content.place(relx=0.5, rely=0.5, anchor="center")
            self.content.configure(width=WINDOW_W, height=WINDOW_H)
            self.content.pack_propagate(True)

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
        files = [os.path.join(self._rhythms_folder(), f) for f in os.listdir(self._rhythms_folder()) if f.lower().endswith(".mp3")]
        files.sort()
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
    def _apply_initial_backing_volumes(self):
        for i, row in enumerate(self.backing_rows):
            v = row.slider.get()
            self.backing_channels[i].set_volume(v)
    def _make_volume_handler(self, idx):
        def h(v): self.backing_channels[idx].set_volume(float(v))
        return h
    def _fade_out_current(self):
        ms = int(self.fade_secs * 1000)
        pygame.mixer.music.fadeout(ms)
        self.backing_channels[self.current_idx].fadeout(ms)
    def _fade_in_next(self):
        ms = int(self.fade_secs * 1000)
        pygame.mixer.music.play(fade_ms=ms)
        snd = self.backing_sounds[self.current_idx]
        if snd:
            self.backing_channels[self.current_idx].play(snd, loops=-1, fade_ms=ms)
            vol = self.backing_rows[self.current_idx].slider.get()
            self.backing_channels[self.current_idx].set_volume(vol)
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
        except:
            messagebox.showerror(APP_TITLE, "Playback error")
    def _pause(self):
        pygame.mixer.music.pause()
        pygame.mixer.pause()
        self.rhythms[self.current_idx].on_pause()
        self.playing = False
        self.play_btn.configure(text="Play")
    def _unpause(self):
        pygame.mixer.music.unpause()
        pygame.mixer.unpause()
        self.rhythms[self.current_idx].on_unpause()
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
        finally:
            self.after(POLL_MS, self._tick)

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
