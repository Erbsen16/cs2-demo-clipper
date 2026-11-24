import json
import msvcrt
import shutil
import os
from pathlib import Path
import re
import subprocess
import tempfile
import winreg

ROOT = Path(__file__).resolve().parent
RECORDER = ROOT / "runtime/csvg/csvg-0.10.1-win-x64/csvg.exe"


def game_directory():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    libraries = [steam]
    registry = steam / "steamapps/libraryfolders.vdf"
    if registry.exists():
        libraries.extend(Path(item.replace("\\\\", "\\")) for item in
                         re.findall(r'"path"\s+"([^"]+)"', registry.read_text(encoding="utf-8-sig")))
    for library in libraries:
        game = library / "steamapps/common/Counter-Strike Global Offensive"
        if (game / "game/bin/win64/cs2.exe").is_file():
            return game
    raise RuntimeError("未找到 Steam 中安装的 CS2。")


def record_demo(demo, destination, player_id, player_name, clips, progress, advanced=None, montage=False, *, broadcast=False):
    from app import encode_clips

    if not RECORDER.is_file():
        raise RuntimeError("录制组件缺失，请从完整工具目录启动。")
    lock_path = Path(tempfile.gettempdir()) / "cs2-editor-recording.lock"
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("已有剪辑窗口正在录制，请等待本次导出结束。") from error
        _capture(demo, destination, player_id, player_name, clips, progress, encode_clips, advanced, montage, broadcast)


def _capture(demo, destination, player_id, player_name, clips, progress, encode_clips, advanced, montage, broadcast):
    running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cs2.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if b'"cs2.exe"' in running.stdout.lower():
        raise RuntimeError("CS2 正在运行。退出当前游戏后再点导出，工具会自动开启回放。")
    game = game_directory()
    ffmpeg = ROOT / "runtime/ffmpeg"
    with tempfile.TemporaryDirectory(dir=Path(destination).resolve().parent) as directory:
        root = Path(directory)
        settings = {"Cs2VideoGenerator": {"Cs2RootInstallationDirectory": str(game)},
                    "Capture": {"InEngine": {"FrameFormat": "Jpg", "IntermediateEncoderPreset": "p2"}},
                    "Ffmpeg": {"BinaryDirectory": str(ffmpeg)}}
        if advanced:
            settings["Capture"]["InEngine"].update({
                "AdditionalSetupCommands": advanced.setup_commands(),
                "JpegQuality": {16: 97, 18: 90, 23: 82}[advanced.crf],
            })
        if not shutil.which("nvidia-smi.exe"):
            settings["Capture"]["InEngine"].pop("IntermediateEncoderPreset")
        (root / "appsettings.json").write_text(json.dumps(settings), encoding="utf-8")
        pending = list(clips)
        sources = []
        env = dict(os.environ, PATH=str(ffmpeg) + os.pathsep + os.environ["PATH"])
        log_path = Path(tempfile.gettempdir()) / "cs2-editor-capture.log"
        batch = 0
        with log_path.open("w", encoding="utf-8") as log:
            while pending:
                base = f"sequence_{batch}"
                definition = {
                    "settings": {"outputDirectory": directory, "baseFileName": base,
                                 "width": advanced.width if advanced else 1280,
                                 "height": advanced.height if advanced else 720,
                                 "frameRate": advanced.fps if advanced else 24, "concatenateClips": False},
                    "clips": [
                        {"demoFilePath": str(Path(demo).resolve()), "matchChecksum": Path(demo).stem,
                         "startTick": round(start * 64), "endTick": round(end * 64),
                         "playerSteamId": int(player_id), "playerNameToSpectate": player_name}
                        for start, end, _, _ in pending
                    ],
                }
                config = root / "clips.json"
                config.write_text(json.dumps(definition), encoding="utf-8")
                progress(f"正在启动 CS2，剩余 {len(pending)} 个片段…")
                completed = 0
                timed_out = False
                with subprocess.Popen(
                    [str(RECORDER), "generate", "--file", str(config)], cwd=root, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding="utf-8", errors="replace",
                ) as process:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        match = re.search(r"Clip (\d+)/\d+ started", line)
                        if match:
                            progress(f"CS2 正在录制片段 {len(sources) + int(match[1])}/{len(sources) + len(pending)}")
                        if re.search(r"Clip \d+/\d+: " + base + r"_\d+\.mp4", line):
                            completed += 1
                        if "WaitForEndTick" in line and "timed out" in line:
                            timed_out = True
                if process.returncode == 0:
                    completed = len(pending)
                for index, (start, end, initial, updates) in enumerate(pending[:completed]):
                    recording = root / f"{base}_{index:03}.mp4"
                    if not recording.is_file():
                        raise RuntimeError(f"录制片段缺失，详情见 {log_path}")
                    sources.append((str(recording), 0, end - start, initial, updates))
                pending = pending[completed:]
                if process.returncode:
                    if not timed_out or not pending:
                        raise RuntimeError(f"CS2 录制失败。详细日志：{log_path}")
                    start, end, initial, updates = pending[0]
                    if end - start <= 2:
                        raise RuntimeError(f"CS2 回放没有到达目标时间。详细日志：{log_path}")
                    middle = round((start + end) * 32) / 64
                    offset = middle - start
                    before = [(t, text) for t, text in updates if t < offset]
                    after = [(t - offset, text) for t, text in updates if t >= offset]
                    right_initial = before[-1][1] if before else initial
                    pending[:1] = [(start, middle, initial, before),
                                   (middle, end, right_initial, after)]
                    progress("当前片段录制超时，已保留完成的片段，正在分段重试…")
                batch += 1
        encode_clips(destination, sources, progress, advanced, montage, broadcast=broadcast)
