---
name: film-production
description: "Make an animated short in Blender: shot list, previews, fix loop, EEVEE render, licensed audio, mp4. Use for an animated short, trailer or multi-shot film. Ships tested scripts. Not for one shot (use camera-cinematography)."
license: MIT
metadata:
  author: https://github.com/proyecto26
  version: "1.0.0"
  category: production
  stage: film
---

# Film Production

Story first, pictures second. Blender does everything: previs, render, edit, encode. No subprocess, no network, no ffmpeg binary: the mp4 comes from Blender's own FFmpeg.

## Order of operations

1. **Concept**: one idea a stranger can retell in two sentences.
2. **Beats**: 4-8 beats, each causing the next ("and because of that..."), with timings that sum to the target runtime. See `references/story-to-shots.md`.
3. **Shot list**: id, frame range, camera, lens, motion, beat, description. Apply it with `scripts/shot_list.py`.
4. **Previs**: block the scene, characters and lighting; render previews.
5. **Preview-inspect-fix loop** (below) until every shot passes.
6. **Final render** (guidance below).
7. **Edit with audio** using `scripts/assemble_edit.py`.

Do not start step 4 before the user has seen the beats and shot list. Skipping them is the main cause of rejected cuts.

## Scripts

All scripts read JSON `ARGS`, return a JSON-safe dict, and are idempotent. Use forward slashes in paths.

Apply the shot list (writes `scene["film_shots"]`, one marker per shot bound to its camera, fps and frame range):

```python
import runpy
r = runpy.run_path("<skill_dir>/scripts/shot_list.py", init_globals={"ARGS": {"fps": 24, "shots": [
    {"id": "S010", "start": 1, "end": 48, "camera": "CAM_S010", "lens_mm": 35, "motion": "still",
     "beat": "Setup", "description": "Wide: mascot at the door", "camera_location": [0, -6, 1.5], "look_at": [0, 0, 1]}]}})["result"]
```

It rejects duplicate ids, `start > end` and overlaps before changing anything, creates missing cameras (unless `create_cameras` is false), and never deletes markers whose name is not a shot id. Rerun it after every timing change.

Render preview stills and a contact sheet:

```python
import runpy
r = runpy.run_path("<skill_dir>/scripts/preview_frames.py", init_globals={"ARGS": {
    "out_dir": "<project>/film/previews", "shots": ["S010"], "frames_per_shot": 3}})["result"]
```

Defaults: 480x270, EEVEE, 8 samples, first/middle/last frame. `r["contact_sheet"]["tiles"]` maps each tile to its shot and frame, row by row from the top-left. All render settings are restored afterwards.

Build the edit and, when ready, render it:

```python
import runpy
r = runpy.run_path("<skill_dir>/scripts/assemble_edit.py", init_globals={"ARGS": {
    "out_path": "<project>/film/final.mp4", "render": False,
    "audio": [{"path": "<project>/music/theme.wav", "license": "CC0", "volume": 0.8, "fade_in": 1, "fade_out": 2}]}})["result"]
```

It builds a separate `EDIT` scene (it refuses to rebuild a scene of that name it did not create; scene strips per shot with each shot's camera, sound strips with volume keyframe fades) and sets H.264 in an MPEG-4 container, with AAC audio only when `audio` is given (no audio stream otherwise). With `render: True` it reads the mp4 back into `verify`: frame count, size and, with audio, a decoded stream of the film's length (`verify.ok`). The source scene is never modified. Run it first with `render: False` and check `strips`, then again with `render: True`. Use `frames: [1, 24]` for a quick test render.

## Preview-inspect-fix loop

1. Run `preview_frames.py` for the shots in play.
2. `Read` `contact_sheet.png`. Look at every tile; do not skim.
3. List defects per shot: framing, subject cut off, wrong lens feel, lighting jump, character off-model, floating contact, empty frame, clipping, wrong camera.
4. Fix only what the list names (camera, light, pose, timing). Do not redo the scene.
5. Re-render only the failing shots (`shots: [...]`) and compare with the previous sheet.
6. **Stop rule:** when the same shot fails twice, stop fixing it. Report what was tried, what still fails, and the best hypothesis. Ask whether to simplify the shot or change the story beat.

Three stills show composition, not motion. For `moving` shots also preview frames near the start and end of the move (`frames_per_shot: 5`) and check that the move reads as motivated.

## Continuity rules

- One protagonist the camera can follow, recognizable in every shot: same rig, materials, scale, proportions.
- Lighting: fix a key direction and colour temperature per scene and keep them across cuts; change them only on a story beat.
- Lenses: pick two or three focal lengths for the film (for example 24 wide, 35 neutral, 85 detail). A lens change needs a reason.
- Screen direction: keep the subject moving the same way across a cut; keep the 180-degree line unless the cut is a deliberate disorientation.
- Reuse the same camera for repeated framings of one location; do not create near-duplicates.
- Store lens and framing choices in the shot list, not only in the cameras, so reruns reproduce them.

## Final render guidance

- Engine: EEVEE (`BLENDER_EEVEE`). Settings that matter: render samples (64 is a good default), ray tracing for reflections/GI, shadow quality, motion blur on `scene.render.use_motion_blur`, and colour management (keep AgX unless the look demands otherwise; the edit scene copies the source view transform).
- Frame rate: choose once (24 for film feel, 30 for web) and set it with `shot_list.py`; never change fps after animating.
- Resolution: 1920x1080 for delivery; previews stay at 480x270.
- Long films (over about 20 seconds or heavy scenes): render each shot to an image sequence first, so a crash does not lose work. No script automates this yet; do it by hand: per shot, set the source scene's frame range to the shot and its camera marker active, set `render.image_settings.file_format` to PNG and `render.filepath` to `<project>/renders/<shot_id>/`, render the animation; then in the EDIT scene replace each scene strip with an image strip of that folder. Short films can render straight from the edit scene.
- Render a still or a 24-frame slice first and inspect it before the full render.
- A scene strip's source scene is only evaluated correctly for animation renders. To inspect an edit frame, render a short animation range and read a frame from it; a single still rendered after `frame_set` can show stale content.
- Never overwrite a previous final: write `final_v2.mp4`.

## Audio rules

- Use only audio the user supplies or explicitly approves: free licenses (CC0, CC-BY) or paid/pro licensed tracks. Record the license for every file; `assemble_edit.py` refuses audio without a `license` and writes `audio_credits.json` next to the mp4.
- Never download audio, never scrape, never generate sound in code unless the user asks for it.
- Duck music under dialogue (lower `volume`), fade in/out at the head and tail, and keep dialogue and music on separate channels.
- You cannot hear the result. Verify by measurement (duration, channel, start frame) and tell the user to listen.
- See `references/audio-and-licensing.md` for license types and credit text.

## Hand-off to AI video

When a shot should become an AI-generated clip (a first/last frame, a mask or a depth pass), use the `ai-video-handoff` skill. It reads `scene["film_shots"]` and the shot markers, so keep both current.

## Gates

Record a verdict per stage in the brief: PASS, FAIL, NOT_CHECKED or N/A, with one line of evidence.

| Stage | PASS when |
|---|---|
| story | beats pass the stranger test and timings sum to the target runtime |
| shot_list | `shot_list.py` returned no overlaps and the user approved the table |
| previs | every shot has a preview sheet and no open defects |
| fix_loop | each shot passed, or was reported after two failures |
| final_render | frames rendered at the target size and fps, spot-checked |
| edit | strips in shot order, audio credited, mp4 size above 0 and frame count matches |
| audio | licenses recorded; mix levels measured; the user was told to listen (NOT_CHECKED for the ear) |

## References

- `references/story-to-shots.md`: beats, shot sizes, lens language, timing math.
- `references/audio-and-licensing.md`: licenses, credits, levels.
