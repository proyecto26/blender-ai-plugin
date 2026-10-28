#!/usr/bin/env python3
"""Assemble the rendered shots into docs/blender-ai-plugin.mp4 (+ preview GIF and poster).

Steps: per-shot clip (frames + caption overlay; PS1 shot upscaled nearest-neighbour and
pillarboxed 4:3) -> xfade chain timed from timeline.json -> soundtrack (soundtrack.py)
normalized to -14 LUFS -> mux. Requires ffmpeg with libx264.

    python3 docs/video/assemble.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
TL = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
FPS, T = TL["fps"], TL["transition_frames"]
TRANSITIONS = {"blockout": "fadeblack", "realistic": "smoothleft", "toon": "smoothleft", "ps1": "pixelize",
               "voxel": "smoothleft", "iso": "smoothleft", "noir": "fade", "neon": "smoothleft",
               "ship": "fadeblack", "stats": "fade", "cta": "fadeblack"}


def ff(*args):
    cmd = ["ffmpeg", "-v", "error", "-y", *args]
    subprocess.run(cmd, check=True)


def clip(shot):
    sid = shot["id"]
    out = os.path.join(BUILD, "clips", f"{sid}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    base = ("scale=1440:1080:flags=neighbor,pad=1920:1080:240:0:black" if sid == "ps1"
            else "scale=1920:1080:flags=lanczos")
    ff("-framerate", str(FPS), "-i", os.path.join(BUILD, "frames", sid, "%04d.png"),
       "-framerate", str(FPS), "-i", os.path.join(BUILD, "overlay", sid, "%04d.png"),
       "-filter_complex", f"[0:v]{base},format=rgba[b];[b][1:v]overlay=format=auto,format=yuv420p[v]",
       "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-r", str(FPS), out)
    return out


def main():
    clips = [clip(s) for s in TL["shots"]]
    inputs, chain, offset = [], "", 0.0
    for c in clips:
        inputs += ["-i", c]
    prev = "[0:v]"
    for i, shot in enumerate(TL["shots"][1:], start=1):
        offset += (TL["shots"][i - 1]["frames"] - T) / FPS
        label = f"[x{i}]"
        chain += (f"{prev}[{i}:v]xfade=transition={TRANSITIONS.get(shot['id'], 'fade')}:"
                  f"duration={T / FPS:.4f}:offset={offset:.4f}{label};")
        prev = label
    silent = os.path.join(BUILD, "video_silent.mp4")
    ff(*inputs, "-filter_complex", chain.rstrip(";"), "-map", prev, "-c:v", "libx264", "-crf", "18",
       "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent)

    wav = os.path.join(BUILD, "soundtrack.wav")
    subprocess.run([sys.executable, os.path.join(HERE, "soundtrack.py"), wav], check=True)
    final = os.path.join(DOCS, "blender-ai-plugin.mp4")
    ff("-i", silent, "-i", wav, "-filter_complex", "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
       "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
       "-movflags", "+faststart", final)

    media = os.path.join(DOCS, "media")
    os.makedirs(media, exist_ok=True)
    gif = os.path.join(media, "preview.gif")
    ff("-ss", "3.6", "-t", "16", "-i", final, "-filter_complex",
       "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
       gif)
    ff("-ss", "1.6", "-i", final, "-frames:v", "1", "-q:v", "3", os.path.join(media, "poster.jpg"))
    sizes = {p: os.path.getsize(p) for p in (final, gif)}
    print(json.dumps({"video": final, "bytes": sizes}, indent=2))


if __name__ == "__main__":
    main()
