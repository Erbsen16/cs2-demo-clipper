"""Validated advanced capture settings shared by the web editor and encoder."""
from dataclasses import dataclass

SIZES = {
    "16:9": [(1280, 720), (1920, 1080), (2560, 1440)],
    "4:3": [(1024, 768), (1280, 960), (1440, 1080)],
    "16:10": [(1280, 800), (1680, 1050), (1920, 1200)],
}


@dataclass(frozen=True)
class CaptureSettings:
    width: int
    height: int
    fps: int
    crf: int
    camera: str
    fov: int
    radar: float
    zoom: float
    position: str
    x: float
    y: float
    fontSize: int

    @classmethod
    def from_request(cls, data):
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("高级设置格式无效。")

        def choice(key, choices):
            value = data.get(key)
            if type(value) not in (str, int) or value not in choices:
                raise ValueError(f"不支持的高级设置：{key}")
            return value

        def number(key, low, high):
            value = data.get(key)
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError(f"高级设置 {key} 超出范围。")
            return value

        ratio = choice("ratio", SIZES.keys())
        sizes = {f"{w}x{h}": (w, h) for w, h in SIZES[ratio]}
        width, height = sizes[choice("size", sizes.keys())]
        return cls(width, height, choice("fps", (24, 30, 60)), choice("crf", (16, 18, 23)),
                   choice("camera", ("eyes", "chase")), choice("fov", range(54, 69)),
                   number("radar", 0.8, 1.3), number("zoom", 0.25, 1),
                   choice("position", ("radar", "custom")), number("x", 0, 100), number("y", 0, 94), choice("fontSize", range(16, 73)))

    def setup_commands(self):
        commands = [f"cl_hud_radar_scale {self.radar:.2f}", "cl_radar_scale_dynamic 0",
                    f"cl_radar_scale {self.zoom:.2f}", f"spec_mode {3 if self.camera == 'chase' else 1}"]
        if self.camera == "eyes":
            commands.append(f"viewmodel_fov {self.fov:d}")
        return commands

    def subtitle_layout(self):
        if self.position == "radar":
            return 7, round(12 * self.height / 720), round((44 + 250 * self.radar) * self.height / 720)
        return (7 if self.x <= 50 else 9), round(self.width * self.x / 100), round(self.height * self.y / 100)
