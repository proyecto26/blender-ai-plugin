# Demo video source

`docs/blender-ai-plugin.mp4` is rendered entirely by Blender using this plugin's own skill scripts. No stock
footage and no screen recording. Captions are 3D text rendered in Blender; the music is synthesized by
`soundtrack.py` (Python stdlib only).

| File | Role |
|------|------|
| `timeline.json` | Single source of truth: shots, durations, captions, accent color, fonts |
| `build_video.py` | Builds each shot's look by calling the skills' scripts, renders the frames and caption overlays |
| `soundtrack.py` | Generates a cut-synced soundtrack from the timeline |
| `assemble.py` | ffmpeg: per-shot clips → xfade chain → −14 LUFS audio → mp4, preview GIF, poster |
| `icon.py` | Renders `.claude-plugin/icon.png` from the neon hero shot |

```bash
B=/Applications/Blender.app/Contents/MacOS/Blender          # Blender 5.1+
$B -b --factory-startup --python docs/video/build_video.py -- '{"stills": true}'   # 1 frame/shot, review first
$B -b --factory-startup --python docs/video/build_video.py -- '{}'                 # full render (~minutes)
python3 docs/video/assemble.py                                                       # needs ffmpeg + libx264
$B -b --factory-startup --python docs/video/icon.py
```

Fonts come from macOS system paths in `timeline.json`; change them on other platforms. Build output goes to
`docs/video/build/` (git-ignored).
