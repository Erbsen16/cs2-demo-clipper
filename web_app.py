import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import webbrowser
from urllib.parse import quote

from app import ALL, COUNTERS, HIGHLIGHTS, MODES, WEAPONS, make_clips, read_demo, select_events
from capture_settings import CaptureSettings, SIZES
from recorder import RECORDER, record_demo


def serve():
    token = secrets.token_urlsafe(24)
    prefix = "/" + token
    html = Path(__file__).with_name("editor.html").read_bytes()
    lock = threading.Lock()
    state = {"events": [], "players": {}, "busy": False, "message": "", "output": None, "filename": ""}

    with tempfile.TemporaryDirectory(prefix="cs2-editor-") as directory:
        folder = Path(directory)
        demo = folder / "match.dem"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def send(self, data, content_type, status=200):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def reply(self, data, status=200):
                self.send(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

            def do_GET(self):
                if self.path == prefix + "/":
                    self.send(html, "text/html; charset=utf-8")
                elif self.path == prefix + "/preview-frame.jpg":
                    self.send(Path(__file__).with_name("preview-frame.jpg").read_bytes(), "image/jpeg")
                elif self.path == prefix + "/advanced.js":
                    self.send(Path(__file__).with_name("advanced.js").read_bytes(), "text/javascript; charset=utf-8")
                elif self.path == prefix + "/status":
                    with lock:
                        self.reply({
                            "players": list(state["players"]), "ready": RECORDER.is_file(),
                            "busy": state["busy"], "message": state["message"],
                            "download": bool(state["output"]),
                            "highlights": HIGHLIGHTS, "sizes": SIZES, "modes": MODES, "weapons": [ALL, *WEAPONS],
                        })
                elif self.path == prefix + "/download":
                    with lock:
                        output = state["output"]
                        filename = state["filename"]
                    if not output:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(output.stat().st_size))
                    self.send_header("Content-Disposition", f"attachment; filename=CS2-clips.mp4; filename*=UTF-8''{quote(filename, safe='')}")
                    self.end_headers()
                    with output.open("rb") as video:
                        shutil.copyfileobj(video, self.wfile)
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path not in (prefix + "/demo", prefix + "/preview", prefix + "/export"):
                    self.send_error(404)
                    return
                with lock:
                    if state["busy"]:
                        self.reply({"error": "正在处理，请稍候。"}, 409)
                        return
                    state["busy"] = True
                background = False
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if self.path.endswith("/demo"):
                        if not 0 < length <= 4 * 1024**3:
                            raise ValueError("请选择小于 4 GB 的 .dem 文件。")
                        pending = folder / "upload.dem"
                        try:
                            with pending.open("wb") as file:
                                while length:
                                    chunk = self.rfile.read(min(length, 1024**2))
                                    if not chunk:
                                        raise ValueError("文件读取中断，请重新选择。")
                                    file.write(chunk)
                                    length -= len(chunk)
                            events, players = read_demo(str(pending))
                            if not players:
                                raise ValueError("这份 Demo 中没有可剪辑的选手事件。")
                            pending.replace(demo)
                        finally:
                            pending.unlink(missing_ok=True)
                        state.update(events=events, players=players, output=None, message="")
                        self.reply({"players": list(players)})
                    else:
                        if not 0 < length <= 4096:
                            raise ValueError("剪辑选项无效。")
                        settings = json.loads(self.rfile.read(length))
                        player = state["players"].get(settings.get("player"))
                        mode, weapon = settings.get("mode"), settings.get("weapon")
                        if player is None or mode not in MODES or weapon not in (ALL, *WEAPONS):
                            raise ValueError("请先选择 Demo、选手和剪辑模式。")
                        advanced = CaptureSettings.from_request(settings.get("advanced"))
                        style = settings.get("counter", COUNTERS[0])
                        show_label = settings.get("showLabel", True)
                        if style not in COUNTERS or not isinstance(show_label, bool):
                            raise ValueError("统计显示选项无效。")
                        highlights = settings.get("highlights", list(HIGHLIGHTS))
                        if not isinstance(highlights, list) or any(
                            not isinstance(item, str) or item not in HIGHLIGHTS for item in highlights
                        ):
                            raise ValueError("高光类型无效。")
                        montage = mode == "单回合特剪"
                        transition = settings.get("transition", "original")
                        if transition not in ("original", "broadcast"):
                            raise ValueError("转场样式无效。")
                        events = state["events"]
                        rounds = []
                        if montage:
                            matches, _ = select_events(events, player, "高光", weapon, highlights)
                            rounds = sorted({event["total_rounds_played"] for event in matches})
                        selected, kills = select_events(events, player, mode, weapon, highlights, settings.get("round"))

                        if self.path.endswith("/preview"):
                            clips = make_clips(selected, kills, 0, 64, float("inf"), montage=montage)
                            self.reply({"events": len(selected), "clips": len(clips), "rounds": rounds})
                        elif not RECORDER.is_file():
                            raise ValueError("内置录制组件缺失，请从完整的工具目录启动。")
                        elif not selected:
                            raise ValueError("当前筛选没有可剪辑的事件。")
                        else:
                            def update(message):
                                with lock:
                                    state["message"] = message

                            def render():
                                output = folder / (secrets.token_hex(8) + ".mp4")
                                try:
                                    deaths = [event for event in state["events"] if event.get("user_identity") == player]
                                    clips = make_clips(selected, kills, 0, 64, float("inf"),
                                                       deaths=deaths, style=style, show_label=show_label, montage=montage)
                                    name = settings["player"].rsplit(" [", 1)[0]
                                    record_demo(demo, output, player, name, clips, update, advanced, montage, broadcast=transition == "broadcast")
                                    with lock:
                                        state.update(output=output, filename=f"{name}-{mode}.mp4", message="视频已生成，可以下载。")
                                except Exception as error:
                                    update(f"导出失败：{error}")
                                finally:
                                    with lock:
                                        state["busy"] = False

                            with lock:
                                state.update(message="正在准备自动导出…", output=None)
                            threading.Thread(target=render, daemon=True).start()
                            background = True
                            self.reply({"message": "正在准备自动导出…"})
                except Exception as error:
                    self.reply({"error": str(error)}, 400)
                finally:
                    if not background:
                        with lock:
                            state["busy"] = False

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            url = f"http://127.0.0.1:{server.server_port}{prefix}/"
            print(f"CS2 editor: {url}", flush=True)
            webbrowser.open(url)
            server.serve_forever()


if __name__ == "__main__":
    serve()
