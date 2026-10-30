# Story to shots

## Beats

A beat is one story change: someone wants something, learns something or loses something. Write each as
"X does Y, so Z".

- Short (30-60 s): 4-6 beats. Setup, want, obstacle, attempt, turn, resolution.
- Causality test: every cut answers "and because of that...", never "and then, somewhere else...". If two beats
  can swap places without breaking anything, they are a montage, not a story.
- Stranger test: someone with no context retells it in two sentences.
- One protagonist, one want. Secondary characters exist to help or block it.
- Give each beat a timing; the sum must equal the target runtime.

## Shot sizes

| Size | Frames the subject | Use for |
|---|---|---|
| Extreme wide (EWS) | tiny in the environment | place, scale, loneliness |
| Wide (WS) | whole body plus surroundings | geography, action |
| Medium (MS) | waist up | dialogue, gesture |
| Close-up (CU) | face or one object | emotion, key information |
| Extreme close-up (ECU) | detail (eye, hand, button) | tension, reveal |

Open a scene wide, cut closer as attention narrows. A size change of at least two steps reads as a cut; one
step looks like a jump cut.

## Lens language (35 mm full-frame equivalent)

| Focal length | Feel |
|---|---|
| 18-24 mm | wide, exaggerated depth, energy, unease |
| 35 mm | natural environment, the default for storytelling |
| 50 mm | neutral, close to human sight |
| 85 mm | portrait, compressed background, intimacy |
| 135 mm+ | isolation, voyeur feel, heavy compression |

Pick two or three lenses per film. Put the lens in the shot list (`lens_mm`).

## Camera motion

Mark each shot `still` or `moving` in the shot list. A move needs a motivation: following the subject,
revealing information, or raising tension. Prefer slow push-ins and tracking over random orbits. Check moving
shots at their first and last frame in previews.

## Timing math

- `frames = seconds x fps`. At 24 fps: 1 s = 24 frames, 2.5 s = 60 frames.
- Typical shot length: 2-5 s (48-120 frames at 24 fps). Close-ups 1-3 s; establishing wides 3-6 s.
- Shot ranges are inclusive: `start = 1, end = 48` is 48 frames. The next shot starts at `end + 1`.
- Runtime = total frames / fps. Check that `sum(end - start + 1)` over all shots matches the target.
- Gaps between shots are dropped in the edit (shots are laid back to back), so use gaps only to leave room
  for animation lead-in.
- Hold the last frame of a beat for 6-12 frames when something important was just said or shown.

## Shot list template

| id | frames | camera | lens | motion | beat | description |
|---|---|---|---|---|---|---|
| S010 | 1-72 | CAM_S010 | 24 | still | setup | wide of the empty street, mascot enters left |
| S020 | 73-120 | CAM_S020 | 50 | moving | want | slow push-in on the mascot looking at the shop |

Ids go up in tens (S010, S020...) so shots can be inserted later. Camera names default to `CAM_<id>`.
