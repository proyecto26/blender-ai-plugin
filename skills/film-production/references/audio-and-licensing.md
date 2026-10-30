# Audio and licensing

## Rules

1. Use only audio the user provides or explicitly approves. Do not download, scrape or generate sound unless
   the user asks.
2. Every audio item passed to `assemble_edit.py` needs a `license` string. The script refuses audio without
   one and writes `audio_credits.json` next to the mp4 (file, license, channel, start frame, volume, plus
   optional `title`, `author`, `source_url`, `notes`).
3. Keep the credits file with the film. Put its content in the film's description or end card when the license
   requires attribution.

## License types

| License | Commercial use | Attribution | Notes |
|---|---|---|---|
| CC0 / public domain | yes | no | safest; still record it |
| CC-BY 4.0 | yes | yes | credit title, author, license, link |
| CC-BY-SA | yes | yes | derivative must stay share-alike; avoid for a film mix unless the user agrees |
| CC-BY-NC | no | yes | personal or non-commercial projects only |
| Pro / paid library | per contract | per contract | keep the receipt or license id in `notes` |
| user-owned | yes | no | the user made it or owns the rights |

If the license is unclear, treat it as not usable and ask.

## Credit text

`"<title>" by <author>, licensed <license> (<source_url>)`

## Levels and mixing

- Music under dialogue: about -12 dB below the voice (`volume` around 0.25 against 1.0). Start with music
  `volume` 0.6-0.8 when there is no dialogue.
- Fade music in at the head (1-2 s) and out at the tail (2-3 s): use `fade_in` and `fade_out` in seconds.
- Dialogue on channel 2, music on 3, effects on 4. Video is always channel 1.
- Align hits to cuts: `start_frame` is in edit frames (1 = first frame of the film). Shots are laid back to
  back from frame 1, so cuts fall at the running sum of shot lengths.
- Audio longer than the film is cut at the last frame; fades are placed before the film end.
- Use WAV or FLAC when possible. Output audio is AAC at 48 kHz stereo.

## What you can and cannot check

You can verify duration, start frame, channel, volume and that the rendered mp4 contains audio. You cannot
hear it. Report levels as measured and ask the user to listen before delivery.
