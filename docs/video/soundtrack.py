#!/usr/bin/env python3
"""Generate the demo video soundtrack from timeline.json (Python stdlib only, no samples).

The music follows the edit: every cut gets a kick, a whoosh rises into it, the rhythm
pattern restarts at each cut, pads change chord every two shots, and a chime lands on
the closing card. Loudness normalization (-14 LUFS) happens in assemble.py via ffmpeg.

    python3 docs/video/soundtrack.py docs/video/build/soundtrack.wav
"""
import json
import math
import os
import random
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 44100
random.seed(26)

# A minor-ish progression (MIDI notes): Am, F, C, G, Dm, Am
CHORDS = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67], [50, 57, 62, 65], [57, 60, 64, 69]]


def hz(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def cut_times(timeline):
    fps, t = timeline["fps"], timeline["transition_frames"]
    starts, cursor = [], 0
    for i, shot in enumerate(timeline["shots"]):
        starts.append(cursor / fps)
        cursor += shot["frames"] - (t if i < len(timeline["shots"]) - 1 else 0)
    return starts, cursor / fps


def render(path):
    timeline = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
    cuts, duration = cut_times(timeline)
    n = int(duration * SR) + SR
    left = [0.0] * n
    right = [0.0] * n

    def add(start_s, samples, pan=0.0, gain=1.0):
        i0 = int(start_s * SR)
        gl, gr = gain * (1 - max(pan, 0)), gain * (1 + min(pan, 0))
        for k, v in enumerate(samples):
            i = i0 + k
            if 0 <= i < n:
                left[i] += v * gl
                right[i] += v * gr

    # Pads: detuned saws through a one-pole low-pass, one chord per two shots.
    for idx in range(0, len(cuts), 2):
        start = cuts[idx]
        end = cuts[idx + 2] if idx + 2 < len(cuts) else duration
        length = int((end - start + 0.6) * SR)
        chord = CHORDS[(idx // 2) % len(CHORDS)]
        for voice, note in enumerate(chord):
            for detune, pan in ((-0.12, -0.6), (0.12, 0.6)):
                f = hz(note + detune / 1.0)
                phase, lp, out = random.random(), 0.0, []
                alpha = 1 - math.exp(-2 * math.pi * 900 / SR)
                for k in range(length):
                    phase = (phase + f / SR) % 1.0
                    lp += alpha * ((2 * phase - 1) - lp)
                    env = min(1.0, k / (0.5 * SR)) * min(1.0, (length - k) / (0.6 * SR))
                    out.append(lp * env)
                add(start, out, pan=pan, gain=0.022)

    # Per-shot rhythm: kick on the cut, bass pulse + hats on 8ths (restart at every cut).
    eighth = 0.25
    for idx, start in enumerate(cuts):
        end = cuts[idx + 1] if idx + 1 < len(cuts) else duration - 1.0
        chord = CHORDS[(idx // 2) % len(CHORDS)]
        kick = []
        for k in range(int(0.28 * SR)):
            t = k / SR
            f = 45 + 80 * math.exp(-t * 30)
            kick.append(math.sin(2 * math.pi * f * t) * math.exp(-t * 11))
        add(start, kick, gain=0.55)
        if idx == 0:
            continue  # title breathes: no pulse
        steps = int((end - start) / eighth)
        bass_f = hz(chord[0] - 24)
        for s in range(steps):
            t0 = start + s * eighth
            bass = [math.tanh(1.5 * math.sin(2 * math.pi * bass_f * (k / SR))) * math.exp(-k / SR * 9)
                    for k in range(int(0.22 * SR))]
            add(t0, bass, gain=0.13)
            if s % 2 == 1:
                hat, prev = [], 0.0
                for k in range(int(0.05 * SR)):
                    noise = random.uniform(-1, 1)
                    hat.append((noise - prev) * math.exp(-k / SR * 90))
                    prev = noise
                add(t0, hat, pan=0.3, gain=0.06)

    # Whoosh into every cut: noise through a rising low-pass.
    for start in cuts[1:]:
        length, lp, out = int(0.4 * SR), 0.0, []
        for k in range(length):
            x = k / length
            cutoff = 200 + 5000 * x ** 2
            alpha = 1 - math.exp(-2 * math.pi * cutoff / SR)
            lp += alpha * (random.uniform(-1, 1) - lp)
            out.append(lp * math.sin(math.pi * x) ** 2)
        add(start - 0.4, out, pan=-0.2, gain=0.22)

    # Chime on the closing card.
    chime = []
    f0 = hz(81)
    for k in range(int(2.5 * SR)):
        t = k / SR
        chime.append(sum(a * math.sin(2 * math.pi * f0 * m * t) for m, a in ((1, 1), (2.76, 0.4), (5.4, 0.15)))
                     * math.exp(-t * 1.8))
    add(cuts[-1] + 0.2, chime, gain=0.12)

    # Master: fades + soft clip, write 16-bit stereo.
    fade_in, fade_out = int(0.3 * SR), int(1.5 * SR)
    total = int(duration * SR)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        frames = bytearray()
        for i in range(total):
            g = min(1.0, i / fade_in) * min(1.0, (total - i) / fade_out)
            frames += struct.pack("<hh", int(32767 * math.tanh(left[i] * g)), int(32767 * math.tanh(right[i] * g)))
        w.writeframes(bytes(frames))
    return {"path": path, "seconds": round(duration, 2), "cuts": len(cuts)}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "soundtrack.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    print(json.dumps(render(out)))
