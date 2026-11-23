"""Prepare the Windows capture tools on first launch."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

import imageio_ffmpeg

from recorder import RECORDER, ROOT

URL = "https://github.com/CS2OpenDev/CS2VideoGenerator/releases/download/v0.10.1/csvg-0.10.1-win-x64.zip"
SHA256 = "82a461a3ae4170c6030c9ef779903d7f5317698c3ed344b9680e33daff12693c"


def prepare():
    runtime = ROOT / "runtime"
    ffmpeg = runtime / "ffmpeg/ffmpeg.exe"
    if ffmpeg.is_file() and RECORDER.is_file():
        return
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime) as directory:
        staging = Path(directory)
        if not RECORDER.is_file():
            print("Downloading CS2 recording tools (first launch)...", flush=True)
            archive = staging / "capture.zip"
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "$ProgressPreference = 'SilentlyContinue'; "
                 "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
                 f"Invoke-WebRequest -UseBasicParsing -ErrorAction Stop -Uri '{URL}' -OutFile capture.zip"],
                cwd=staging, check=True, timeout=300,
            )
            with archive.open("rb") as data:
                digest = hashlib.file_digest(data, "sha256").hexdigest()
            if digest != SHA256:
                raise RuntimeError("Recording tools failed SHA-256 verification.")
            with ZipFile(archive) as package:
                package.extractall(staging)
            unpacked = staging / RECORDER.parent.name
            if not (unpacked / RECORDER.name).is_file():
                raise RuntimeError("Recording executable missing from archive.")
            RECORDER.parent.parent.mkdir(exist_ok=True)
            try:
                unpacked.rename(RECORDER.parent)
            except FileExistsError:
                if not RECORDER.is_file():
                    raise
        if not ffmpeg.is_file():
            ffmpeg.parent.mkdir(exist_ok=True)
            binary = staging / "ffmpeg.exe"
            shutil.copyfile(imageio_ffmpeg.get_ffmpeg_exe(), binary)
            binary.replace(ffmpeg)


if __name__ == "__main__":
    prepare()
