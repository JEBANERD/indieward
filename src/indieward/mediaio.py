"""Thin ffmpeg/ffprobe wrappers for decoding and encoding audio and video."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np


class MediaToolMissing(RuntimeError):
    pass


def _bin(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MediaToolMissing(
            f"{name} was not found. Install FFmpeg (https://ffmpeg.org/download.html) and make sure "
            f"'{name}' is on your PATH."
        )
    return path


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe(path) -> dict:
    out = subprocess.run(
        [_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        check=True,
        capture_output=True,
    ).stdout
    return json.loads(out)


def video_info(path) -> dict:
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    return {"width": int(v["width"]), "height": int(v["height"]), "fps": fps, "has_audio": has_audio}


def read_audio(path, sr: int | None = None, mono: bool = False) -> tuple[np.ndarray, int]:
    """Decode any audio (or a video's audio track) to float32 (frames, channels)."""
    info = probe(path)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if a is None:
        raise ValueError(f"{path} has no audio stream")
    rate = sr or int(a["sample_rate"])
    ch = 1 if mono else int(a.get("channels", 2))
    raw = subprocess.run(
        [_bin("ffmpeg"), "-v", "error", "-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", str(ch), "-ar", str(rate), "-"],
        check=True,
        capture_output=True,
    ).stdout
    data = np.frombuffer(raw, dtype=np.float32).reshape(-1, ch)
    return data.astype(np.float64), rate


def write_audio(path, data: np.ndarray, sr: int, codec_args: list[str] | None = None) -> None:
    """Encode float audio (frames, channels). Format follows the file extension."""
    data = np.clip(data, -1.0, 1.0).astype(np.float32)
    ch = data.shape[1] if data.ndim == 2 else 1
    ext = Path(path).suffix.lower()
    if codec_args is None:
        codec_args = {
            ".wav": ["-acodec", "pcm_s16le"],
            ".mp3": ["-acodec", "libmp3lame", "-b:a", "192k"],
            ".ogg": ["-acodec", "libvorbis", "-q:a", "6"],
            ".m4a": ["-acodec", "aac", "-b:a", "192k"],
            ".flac": ["-acodec", "flac"],
        }.get(ext, [])
    subprocess.run(
        [_bin("ffmpeg"), "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "-",
         *codec_args, str(path)],
        input=data.tobytes(),
        check=True,
    )


def iter_frames(path, size: tuple[int, int] | None = None, gray: bool = False, fps: float | None = None):
    """Yield decoded frames as float arrays (h, w, 3) or (h, w) if gray."""
    info = video_info(path)
    w, h = size or (info["width"], info["height"])
    filters = []
    if fps:
        filters.append(f"fps={fps}")
    if size:
        filters.append(f"scale={w}:{h}:flags=area")
    pix = "gray" if gray else "rgb24"
    cmd = [_bin("ffmpeg"), "-v", "error", "-i", str(path)]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-f", "rawvideo", "-pix_fmt", pix, "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * (1 if gray else 3)
    try:
        while True:
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            arr = np.frombuffer(buf, dtype=np.uint8).astype(np.float64)
            yield arr.reshape(h, w) if gray else arr.reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait()


class FrameWriter:
    """Encode rgb24 frames to H.264, copying the audio track from ``audio_src``."""

    def __init__(self, path, width: int, height: int, fps: float, audio_src=None, crf: int = 18):
        cmd = [_bin("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{width}x{height}", "-r", f"{fps:.6f}", "-i", "-"]
        if audio_src is not None:
            cmd += ["-i", str(audio_src), "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "copy"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", str(path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, frame: np.ndarray) -> None:
        self.proc.stdin.write(np.clip(np.rint(frame), 0, 255).astype(np.uint8).tobytes())

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding video")


def transcode(src, dst, args: list[str]) -> None:
    subprocess.run([_bin("ffmpeg"), "-v", "error", "-y", "-i", str(src), *args, str(dst)], check=True)
