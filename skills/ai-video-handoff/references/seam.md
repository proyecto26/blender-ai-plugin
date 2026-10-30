# Seam handoff contract

Seam is a local app that renders an AI transition between two shots and joins several into one video. The
handoff produces exactly what Seam's MCP tool `create_sequence(shots, segments)` takes. Facts below come from
Seam's own source (`mcp_server.py`, `server.py`) and README; re-check with `list_presets` and the tool
docstring when Seam updates.

## seam_sequence.json

Written to `<out_dir>/seam/seam_sequence.json`:

- `shots`: absolute local paths in story order, forward slashes. 2-8 entries. Each is either a PNG still or an
  mp4 clip of 1-6 s.
- `segments`: `len(shots) - 1` dicts, one per hand-off between neighbouring shots.
- `size`: `[w, h]` Blender rendered at (multiples of 32). Informational only.
- `fps`: the clip frame rate.
- `notes`: reminders (preset choice, size, boundary frames).

Segment fields, as Seam's `SegmentIn` defines them:

| Field | Meaning |
|---|---|
| `preset` | id from Seam's `list_presets`. Required by Seam. The script writes `null` unless you pass `segments`. |
| `seconds` | take length; one of the lengths that preset lists (default 5; some presets list 5 and 10) |
| `seed` | optional, pins the take |
| `prompt_extra` | optional extra direction, max 600 characters |
| `a_desc`, `b_desc` | optional descriptions of the outgoing and incoming shot, max 400 characters. Omitted: Seam reads the image. Empty string: generic. |

The script fills `a_desc` and `b_desc` from the shot descriptions (truncated to 400). Pass `segments` to the
script to write your own, which are copied as-is and only counted (must equal `len(shots) - 1`).

## Boundary semantics

Seam takes a clip's first frame and last frame itself. The transition before a clip lands on its first frame;
the transition after it leaves from its last frame. The clip plays in full at its place in the sequence. A still
PNG is used as both ends. So:

- A moving shot is handed over as a clip. The script renders its frame range (clamped to 6 s), not separate
  boundary stills.
- A still shot is one PNG: the middle frame of its range, opaque RGB.
- Design the first and last frame of each moving shot for the transition. A clip that ends mid-blur gives a bad
  hand-off.

## Limits

- Shots: 2 to 8. Clips 1-6 s (Seam normalizes them to one clock on upload). Clip upload limit is 40 MB.
- Every take renders at the first shot's aspect ratio. Seam picks the output pixel size itself. The manifest does
  not promise an output size; render all shots at one size so the aspect is consistent.
- Seam re-encodes stills to RGB. Alpha, masks, depth and camera data are not consumed.
- Presets are qualified only at the lengths `list_presets` reports. Do not pass other lengths.

## Calling it

MCP (preferred): `list_presets`, edit the segments, `create_sequence(shots, segments)`, then `wait_sequence`,
`preview_sequence` (contact sheet of the whole arc) and `preview_job` per segment. `refine_segment` re-rolls one
transition; `extend_sequence` adds a shot at the end.

REST: upload each file with `POST /api/uploads?role=mid`. A clip returns `clip`, `first` and `last` ids; an image
returns an `id`. Build the body as `{"shots": [...], "segments": [...]}` where a clip shot is
`{"clip": <clip id>, "first": <first id>, "last": <last id>}` and a still is `{"image": <id>}`, then
`POST /api/sequences`. The manifest targets the MCP tool, so substitute upload ids yourself.

## Consent

Seam renders on the user's own GPU. Say how many takes will run and roughly how long before submitting. If Seam is
configured to use a paid or cloud backend, ask first.
