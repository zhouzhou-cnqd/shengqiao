"""Build a self-contained, privacy-safe single-audio demo page.

With no --input, the script generates a synthetic speech-like waveform. Pass an
authorized local PCM WAV to visualize a real recording without uploading it.
This public demo performs preprocessing and STFT visualization only; it does
not claim to run the private classifier or reconstruction weights.
"""

from __future__ import annotations

import argparse
import base64
import cmath
import io
import json
import math
import random
import sys
import tempfile
import wave
from array import array
from pathlib import Path

TARGET_RATE = 16_000


def synthetic_audio() -> list[float]:
    """Return a deterministic, speech-like signal with three syllable envelopes."""
    rng, phase, audio = random.Random(42), 0.0, []
    for index in range(int(TARGET_RATE * 2.8)):
        t = index / TARGET_RATE
        phase += 2 * math.pi * (118 + 13 * math.sin(2 * math.pi * 0.7 * t)) / TARGET_RATE
        voiced = sum(math.sin((harmonic + 1) * phase) / (harmonic + 1) for harmonic in range(9))
        envelope = sum(math.exp(-0.5 * ((t - center) / width) ** 2) for center, width in [(0.55, 0.22), (1.4, 0.28), (2.25, 0.24)])
        audio.append((voiced + rng.gauss(0, 0.035)) * envelope)
    peak = max(abs(value) for value in audio)
    return [0.88 * value / peak for value in audio]


def read_wav(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as wav:
        channels, width, rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
        if width != 2:
            raise ValueError("Only 16-bit PCM WAV input is supported.")
        samples = array("h")
        samples.frombytes(wav.readframes(frames))
        if sys.byteorder != "little":
            samples.byteswap()
    audio = [sum(samples[i:i + channels]) / channels / 32768 for i in range(0, len(samples), channels)]
    if rate != TARGET_RATE:
        output_length = round(len(audio) * TARGET_RATE / rate)
        resampled = []
        for index in range(output_length):
            position = index * rate / TARGET_RATE
            left = min(int(position), len(audio) - 1)
            right = min(left + 1, len(audio) - 1)
            fraction = position - left
            resampled.append(audio[left] * (1 - fraction) + audio[right] * fraction)
        audio = resampled
    peak = max((abs(value) for value in audio), default=1) or 1
    return [value / peak for value in audio]


def wav_bytes(audio: list[float]) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TARGET_RATE)
        pcm = array("h", [round(max(-1, min(1, value)) * 32767) for value in audio])
        if sys.byteorder != "little":
            pcm.byteswap()
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def fft(values: list[complex]) -> None:
    size = len(values)
    target = 0
    for source in range(1, size):
        bit = size >> 1
        while target & bit:
            target ^= bit
            bit >>= 1
        target ^= bit
        if source < target:
            values[source], values[target] = values[target], values[source]
    length = 2
    while length <= size:
        root = cmath.exp(-2j * math.pi / length)
        for start in range(0, size, length):
            factor = 1 + 0j
            for offset in range(length // 2):
                even = values[start + offset]
                odd = values[start + offset + length // 2] * factor
                values[start + offset], values[start + offset + length // 2] = even + odd, even - odd
                factor *= root
        length *= 2


def spectrogram(audio: list[float]) -> list[list[int]]:
    size, hop = 512, 128
    if len(audio) < size:
        audio += [0.0] * (size - len(audio))
    count = 1 + (len(audio) - size) // hop
    window = [0.5 - 0.5 * math.cos(2 * math.pi * index / (size - 1)) for index in range(size)]
    frames = []
    peak = -1e9
    for frame_index in range(count):
        values = [complex(audio[frame_index * hop + index] * window[index], 0) for index in range(size)]
        fft(values)
        row = [20 * math.log10(abs(value) + 1e-7) for value in values[:257]]
        peak = max(peak, max(row))
        frames.append(row)
    return [[round(max(0, min(1, (frames[x][bin_index] - peak + 72) / 72)) * 255) for x in range(count)] for bin_index in range(257)]


def build_html(audio: list[float], label: str) -> str:
    encoded = base64.b64encode(wav_bytes(audio)).decode("ascii")
    matrix = json.dumps(spectrogram(audio), separators=(",", ":"))
    duration = len(audio) / TARGET_RATE
    return f"""<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>声桥 · 单音频演示</title>
<style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#eef1ec,#eee7e4);color:#26312c;font:15px/1.6 system-ui}}main{{width:min(1050px,92vw);padding:34px;border:1px solid #829087;border-radius:28px;background:#ffffffaa;box-shadow:0 25px 70px #52605922}}h1{{margin:0;font:600 38px Georgia,serif}}p{{color:#66716b}}.meta{{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}}.meta span{{padding:5px 10px;border:1px solid #829087;border-radius:999px}}audio,canvas{{width:100%}}canvas{{height:360px;background:#070b18;border-radius:14px}}.note{{padding:13px 16px;border-left:4px solid #9a7279;background:#fff8}}</style>
<main><h1>声桥 · 单音频预处理演示</h1><p>{label}</p><div class=\"meta\"><span>16 kHz</span><span>单声道</span><span>{duration:.2f} s</span><span>512 点 STFT</span></div><audio controls src=\"data:audio/wav;base64,{encoded}\"></audio><h2>输入频谱</h2><canvas id=\"s\" width=\"1000\" height=\"360\"></canvas><p class=\"note\">公开演示仅执行音频标准化与频谱分析，不加载患者数据、分类权重或重建权重。真实模型结果仅在授权本地环境中运行。</p></main>
<script>const m={matrix},c=document.querySelector('#s'),x=c.getContext('2d'),h=m.length,w=m[0].length,stops=[[7,11,24],[13,8,135],[126,3,168],[204,71,120],[248,149,64],[240,249,33]];function mix(a,b,t){{return Math.round(a+(b-a)*t)}}function col(v){{let p=Math.min(.999,v/255)*(stops.length-1),i=Math.floor(p),t=p-i,a=stops[i],b=stops[i+1];return `rgb(${{mix(a[0],b[0],t)}},${{mix(a[1],b[1],t)}},${{mix(a[2],b[2],t)}})`}}x.fillStyle='#070b18';x.fillRect(0,0,c.width,c.height);for(let i=0;i<w;i++)for(let j=0;j<h;j++){{x.fillStyle=col(m[j][i]);x.fillRect(i*c.width/w,c.height-(j+1)*c.height/h,Math.ceil(c.width/w)+1,Math.ceil(c.height/h)+1)}}</script></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Authorized local 16-bit PCM WAV. Omit to use the synthetic example.")
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "shengqiao-single-audio.html")
    args = parser.parse_args()
    audio = read_wav(args.input) if args.input else synthetic_audio()
    label = f"本地授权音频：{args.input.name}" if args.input else "仓库内置算法即时生成的合成语音状信号（不来自任何受试者）"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(audio, label), encoding="utf-8")
    print(f"Demo written to: {args.output.resolve()}")


if __name__ == "__main__":
    main()

