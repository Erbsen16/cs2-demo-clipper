from bisect import bisect_left, bisect_right
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

WEAPONS = {
    "狙击": "awp ssg08 scar20 g3sg1",
    "步枪": "ak47 m4a1 m4a1_silencer aug sg556 galilar famas",
    "手枪": "glock usp_silencer hkp2000 p250 tec9 fiveseven cz75a elite deagle revolver",
    "冲锋枪": "mac10 mp9 mp7 mp5sd ump45 p90 bizon",
}
ALL = "全部枪械"
MODES = ("高光", "全部击杀", "全部死亡", "击杀和死亡")


def read_demo(path):
    from demoparser2 import DemoParser

    parser = DemoParser(path)
    deaths = parser.parse_event(
        "player_death", player=["team_num"], other=["total_rounds_played", "is_warmup_period"]
    )
    deaths = deaths.loc[deaths["is_warmup_period"].eq(False)]
    # Keep 64-bit Steam IDs intact even when an event has no attacker.
    events = sorted(deaths.to_dict("records"), key=lambda event: event["tick"])
    players = {}
    for event in events:
        for role in ("attacker", "user"):
            name = event.get(f"{role}_name")
            if name and isinstance(name, str):
                steam_id = event.get(f"{role}_steamid")
                identity = steam_id if steam_id and str(steam_id) != "nan" else name
                players[f"{name} [{identity}]"] = identity
                event[f"{role}_identity"] = identity
    return events, dict(sorted(players.items()))


def select_events(events, player, mode, category):
    kills = [
        event for event in events
        if event.get("attacker_identity") == player
        and event.get("user_identity") != player
        and event.get("attacker_team_num") != event.get("user_team_num")
    ]
    if mode == "全部死亡":
        return [event for event in events if event.get("user_identity") == player], kills
    selected = kills
    if mode == "高光":
        round_counts = {}
        for event in kills:
            round_id = event["total_rounds_played"]
            round_counts[round_id] = round_counts.get(round_id, 0) + 1
        selected = [
            event for event in kills
            if round_counts[event["total_rounds_played"]] >= 2
            or any(event.get(flag) for flag in ("headshot", "noscope", "thrusmoke", "penetrated"))
        ]
    if category != ALL:
        weapons = WEAPONS[category].split()
        selected = [
            event for event in selected
            if event["weapon"].removeprefix("weapon_") in weapons
        ]
    if mode == "击杀和死亡":
        deaths = [event for event in events if event.get("user_identity") == player]
        selected = sorted(selected + deaths, key=lambda event: event["tick"])
    return selected, kills


COUNTERS = ("仅击杀", "击杀-死亡", "不显示")


def counter_text(kills, deaths, style, show_label):
    if style == "击杀-死亡":
        value = f"i{deaths}" if kills == 1 else f"{kills}-{deaths}"
    else:
        value = str(kills)
    return f"KILLS  {value}" if show_label else value


def make_clips(selected, kills, tick_zero, tick_rate, duration, *,
               deaths=(), style="仅击杀", show_label=True):
    windows = []
    for event in selected:
        moment = tick_zero + event["tick"] / tick_rate
        if not 0 <= moment < duration:
            continue
        start, end = max(0, moment - 5), min(duration, moment + 3)
        if windows and start <= windows[-1][1]:
            windows[-1] = (windows[-1][0], end)
        else:
            windows.append((start, end))
    if style == "不显示":
        return [(start, end, None, []) for start, end in windows]
    kill_times = sorted(tick_zero + event["tick"] / tick_rate for event in kills)
    death_times = sorted(tick_zero + event["tick"] / tick_rate for event in deaths) if style == "击杀-死亡" else []
    clips = []
    shown_kills = 0
    for start, end in windows:
        left, right = bisect_left(kill_times, start), bisect_left(kill_times, end)
        dleft, dright = bisect_left(death_times, start), bisect_left(death_times, end)
        initial_kills = left if style == "击杀-死亡" else shown_kills
        initial = counter_text(initial_kills, dleft, style, show_label)
        updates = []
        for moment in sorted(set(kill_times[left:right] + death_times[dleft:dright])):
            kill_count = initial_kills + bisect_right(kill_times, moment) - left
            death_count = bisect_right(death_times, moment)
            updates.append((moment - start, counter_text(kill_count, death_count, style, show_label)))
        clips.append((start, end, initial, updates))
        shown_kills += right - left
    return clips


def ass_time(value):
    units = round(value * 100)
    minutes, seconds = divmod(units, 6000)
    return f"{minutes // 60}:{minutes % 60:02}:{seconds // 100:02}.{seconds % 100:02}"


def write_counter(path, length, text, updates):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,32,&H00FFFFFF,&H00FFFFFF,&HFF000000,&HFF000000,-1,0,0,0,100,100,0,0,1,0,0,7,12,12,294,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    start = 0
    for end, next_text in [*updates, (length, None)]:
        if ass_time(end) != ass_time(start):
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}\n")
        text = next_text
        start = end
    path.write_text("".join(lines), encoding="utf-8")


def export_video(source, destination, selected, kills, tick_zero, rate, progress, **counter):
    import imageio_ffmpeg

    duration = imageio_ffmpeg.count_frames_and_secs(source)[1]
    clips = make_clips(selected, kills, tick_zero, rate, duration, **counter)
    encode_clips(destination, [(source, *clip) for clip in clips], progress)


def encode_clips(destination, clips, progress):
    import imageio_ffmpeg

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    if not clips:
        raise ValueError("所选事件都在录像范围之外，请检查时间对齐。")

    def ffmpeg(args, folder):
        result = subprocess.run(
            [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args],
            cwd=folder, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace").strip())

    with tempfile.TemporaryDirectory(dir=Path(destination).parent) as folder:
        root = Path(folder)
        entries = []
        for index, (source, start, end, initial, updates) in enumerate(clips):
            progress(f"正在编码片段 {index + 1} / {len(clips)}")
            filters = ["pad=ceil(iw/2)*2:ceil(ih/2)*2"]
            if initial is not None:
                write_counter(root / "counter.ass", end - start, initial, updates)
                filters.insert(0, "subtitles=counter.ass")
            name = f"clip{index}.mp4"
            ffmpeg([
                "-ss", str(start), "-i", source, "-t", str(end - start),
                "-map", "0:v:0", "-map", "0:a:0?",
                "-vf", ",".join(filters),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", name,
            ], folder)
            entries.append(f"file '{name}'\n")
        progress("正在合并片段…")
        (root / "clips.txt").write_text("".join(entries), encoding="ascii")
        ffmpeg(["-f", "concat", "-safe", "0", "-i", "clips.txt",
                "-c", "copy", "-movflags", "+faststart", "result.mp4"], folder)
        os.replace(root / "result.mp4", destination)


def export_demo(demo, destination, player_id, selected, kills, progress, **counter):
    from recorder import record_demo

    for event in selected:
        for role in ("attacker", "user"):
            if event.get(f"{role}_identity") == player_id:
                clips = make_clips(selected, kills, 0, 64, float("inf"), **counter)
                return record_demo(demo, destination, player_id, event[f"{role}_name"], clips, progress)
    raise ValueError("没有找到这名选手的片段。")


class Editor:
    def __init__(self, root):
        self.root = root
        self.events, self.players = [], {}
        root.title("CS2 自动剪辑")
        root.geometry("790x790")
        root.minsize(700, 725)
        root.configure(bg="#111827")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 25, "bold"))
        style.configure("Accent.TButton", background="#fbbf24", foreground="#111827")
        style.map("Accent.TButton", background=[("active", "#fcd34d")])
        panel = ttk.Frame(root, padding=28)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="CS2 自动剪辑", style="Title.TLabel").grid(row=0, columnspan=3, sticky="w")
        self.demo = tk.StringVar()
        self.video = tk.StringVar()
        self.player = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.category = tk.StringVar(value=ALL)
        self.tick = tk.StringVar(value="0")
        self.seconds = tk.StringVar(value="0")
        self.rate = tk.StringVar(value="64")
        self.status = tk.StringVar(value="请选择比赛 Demo。")
        self.demo_button = self.file_row(panel, 1, "比赛 Demo", self.demo, self.load_demo)
        self.file_row(panel, 2, "选手视角录像", self.video, self.load_video)
        ttk.Label(panel, text="选手").grid(row=3, column=0, sticky="w")
        self.player_box = ttk.Combobox(panel, textvariable=self.player, state="readonly")
        self.player_box.grid(row=3, column=1, columnspan=2, sticky="ew", pady=8)
        filters = ttk.Frame(panel)
        filters.grid(row=4, column=1, columnspan=2, sticky="w", pady=8)
        for mode in MODES:
            ttk.Button(filters, text=mode, command=lambda choice=mode: self.mode.set(choice)).pack(side="left", padx=(0, 6))
        self.weapon_box = ttk.Combobox(filters, textvariable=self.category, values=[ALL, *WEAPONS], state="readonly", width=10)
        self.weapon_box.pack(side="left")
        ttk.Label(panel, text="剪辑模式").grid(row=4, column=0, sticky="w")
        ttk.Label(panel, text="录像对齐").grid(row=5, column=0, sticky="w")
        alignment = ttk.Frame(panel)
        alignment.grid(row=5, column=1, columnspan=2, sticky="w", pady=8)
        for label, variable in [("Demo Tick", self.tick), ("录像秒数", self.seconds), ("Tick 率", self.rate)]:
            ttk.Label(alignment, text=label).pack(side="left", padx=(0, 4))
            entry = ttk.Entry(alignment, textvariable=variable, width=8)
            entry.pack(side="left", padx=(0, 10))
            if variable is self.seconds:
                self.seconds_entry = entry
        self.summary = ttk.Label(panel, wraplength=620)
        self.summary.grid(row=6, columnspan=3, sticky="w", pady=12)
        timeline = ttk.Frame(panel)
        timeline.grid(row=7, columnspan=3, sticky="nsew")
        panel.rowconfigure(7, weight=1)
        self.timeline = ttk.Treeview(
            timeline, columns=("tick", "weapon", "attacker", "victim"),
            show="headings", selectmode="browse", height=6,
        )
        for key, label, width in (
            ("tick", "Demo Tick", 95), ("weapon", "武器", 125),
            ("attacker", "击杀者", 170), ("victim", "被击杀者", 170),
        ):
            self.timeline.heading(key, text=label)
            self.timeline.column(key, width=width, stretch=key in ("attacker", "victim"))
        scrollbar = ttk.Scrollbar(timeline, orient="vertical", command=self.timeline.yview)
        self.timeline.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.timeline.pack(side="left", fill="both", expand=True)
        self.timeline.bind("<Double-1>", self.use_alignment_event)
        self.timeline.bind("<Return>", self.use_alignment_event)
        self.align_button = ttk.Button(panel, text="用选中事件对齐", command=self.use_alignment_event)
        self.align_button.grid(row=8, columnspan=3, sticky="w", pady=(8, 0))
        self.timeline.bind("<<TreeviewSelect>>", self.update_alignment_button)
        self.alignment_hint = ttk.Label(panel, text="选中一条事件填入 Tick，再输入该事件在录像中的秒数。")
        self.alignment_hint.grid(row=8, column=1, columnspan=2, sticky="e", pady=(8, 0))
        options = ttk.Frame(panel)
        options.grid(row=9, columnspan=3, sticky="w", pady=4)
        self.counter_style = tk.StringVar(value=COUNTERS[0])
        self.counter_label = tk.BooleanVar(value=True)
        ttk.Label(options, text="画面统计").pack(side="left")
        ttk.Combobox(options, textvariable=self.counter_style, values=COUNTERS, state="readonly", width=12).pack(side="left", padx=8)
        ttk.Checkbutton(options, text="显示 KILLS 字样", variable=self.counter_label).pack(side="left")
        self.visible_events = None
        self.export_button = ttk.Button(panel, text="导出 MP4", style="Accent.TButton", command=self.export)
        self.export_button.configure(text="从已有录像导出")
        self.export_button.grid(row=11, columnspan=3, sticky="ew", pady=4)
        self.auto_button = ttk.Button(panel, text="从 Demo 全自动导出 MP4", style="Accent.TButton", command=self.export_auto)
        self.auto_button.grid(row=10, columnspan=3, sticky="ew", pady=4)
        ttk.Label(panel, textvariable=self.status, wraplength=620).grid(row=12, columnspan=3, sticky="w", pady=8)
        self.busy = False
        for variable in (self.player, self.mode, self.category, self.video):
            variable.trace_add("write", self.refresh)
        self.refresh()

    def file_row(self, panel, row, label, variable, command):
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(panel, textvariable=variable, state="readonly").grid(row=row, column=1, sticky="ew", pady=8)
        button = ttk.Button(panel, text="选择文件", command=command)
        button.grid(row=row, column=2, padx=(8, 0))
        return button

    def selection(self):
        return select_events(self.events, self.players.get(self.player.get()), self.mode.get(), self.category.get()) if self.player.get() in self.players else ([], [])

    def update_alignment_button(self, *_):
        self.align_button.configure(state="normal" if self.timeline.selection() else "disabled")

    def use_alignment_event(self, event=None):
        if event and event.type == tk.EventType.ButtonPress:
            row = self.timeline.identify_row(event.y)
        else:
            row = next(iter(self.timeline.selection()), "")
        if row:
            self.tick.set(str(self.timeline.set(row, "tick")))
            self.seconds.set("")
            self.seconds_entry.focus_set()
            self.status.set("请输入该事件在录像中发生的秒数。")

    def refresh(self, *_):
        selected, _ = self.selection()
        if selected != self.visible_events:
            self.visible_events = selected
            self.timeline.delete(*self.timeline.get_children())
            for event in selected:
                self.timeline.insert("", "end", values=(
                    event["tick"], event.get("weapon") or "",
                    event.get("attacker_name") or "", event.get("user_name") or "",
                ))
        self.update_alignment_button()
        death_mode = self.mode.get() == MODES[2]
        self.weapon_box.configure(state="disabled" if death_mode else "readonly")
        first = f" 首个事件位于 Tick {selected[0]['tick']}。" if selected else ""
        self.summary.configure(text=f"{self.mode.get()} · {len(selected)} 个事件。每个事件前 5 秒、后 3 秒，重叠片段自动合并。{first}")
        self.export_button.configure(state="normal" if selected and self.video.get() and not self.busy else "disabled")
        self.auto_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.demo_button.configure(state="disabled" if self.busy else "normal")

    def background(self, work, success, status):
        import queue

        updates = queue.Queue()
        self.busy = True
        self.status.set(status)
        self.refresh()

        def run():
            try:
                result = work(lambda message: updates.put(("progress", message)))
                updates.put(("done", result))
            except Exception as error:
                updates.put(("error", str(error)))

        def poll():
            try:
                while True:
                    kind, payload = updates.get_nowait()
                    if kind == "progress":
                        self.status.set(payload)
                        continue
                    self.busy = False
                    if kind == "done":
                        success(payload)
                    else:
                        self.status.set("操作失败")
                        messagebox.showerror("操作失败", payload)
                    self.refresh()
                    return
            except queue.Empty:
                self.root.after(100, poll)

        threading.Thread(target=run, daemon=True).start()
        self.root.after(100, poll)

    def load_demo(self):
        path = filedialog.askopenfilename(filetypes=[("CS2 Demo", "*.dem")])
        if not path:
            return

        def loaded(result):
            self.events, self.players = result
            self.demo.set(path)
            self.player_box.configure(values=list(self.players))
            self.player.set(next(iter(self.players), ""))
            self.status.set(f"已读取 {len(self.players)} 名有事件的选手。")

        self.background(lambda _: read_demo(path), loaded, "正在解析 Demo…")

    def load_video(self):
        path = filedialog.askopenfilename(filetypes=[("视频", "*.mp4 *.mkv *.mov *.avi *.webm")])
        if path:
            self.video.set(path)

    def counter_options(self):
        player = self.players[self.player.get()]
        return {"style": self.counter_style.get(), "show_label": self.counter_label.get(),
                "deaths": [event for event in self.events if event.get("user_identity") == player]}

    def export_auto(self):
        destination = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if not destination:
            return
        demo = self.demo.get()
        player_id = self.players[self.player.get()]
        selected, kills = self.selection()
        counter = self.counter_options()
        self.background(
            lambda progress: export_demo(demo, destination, player_id, selected, kills, progress, **counter),
            lambda _: self.status.set(f"已导出 {destination}"),
            "正在准备自动导出…",
        )

    def export(self):
        import math

        try:
            tick, seconds, rate = map(float, (self.tick.get(), self.seconds.get(), self.rate.get()))
            if not all(math.isfinite(value) for value in (tick, seconds, rate)) or min(tick, seconds) < 0 or rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("录像对齐", "请输入有效的 Tick、录像秒数和 Tick 率。")
            return
        destination = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4", "*.mp4")])
        if not destination:
            return
        source = self.video.get()
        if Path(source).resolve() == Path(destination).resolve():
            messagebox.showerror("导出", "请选择与源录像不同的保存路径。")
            return
        selected, kills = self.selection()
        counter = self.counter_options()
        self.background(
            lambda progress: export_video(source, destination, selected, kills, seconds - tick / rate, rate, progress, **counter),
            lambda _: self.status.set(f"已导出 {destination}"),
            "正在读取录像…",
        )


if __name__ == "__main__":
    root = tk.Tk()
    Editor(root)
    root.mainloop()
