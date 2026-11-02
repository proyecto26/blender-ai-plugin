# Terrain with a road bed

`scripts/terrain_heightfield.py` builds a seeded terrain mesh and can flatten a corridor along a curve. It makes the
ground; it does not make the road surface.

## Steps

1. Draw the road centreline as a curve object (`CRV_Road`). Give its points the heights you want the road to have: the
   corridor copies the curve's Z, so a climbing road needs climbing points.
2. Run the script with `corridor`:
   `{"name": "GEO_Terrain", "size": 80, "resolution": 161, "seed": 3, "height": 5, "corridor": {"curve": "CRV_Road", "half_width": 3, "falloff": 6}}`
3. Check `result.corridor.flat_vertices`: zero means the curve is outside the terrain or the resolution is too coarse for
   `half_width`.
4. Build the road surface separately (for example with the swept-profile script in this skill) and keep it at the same
   curve. Use `corridor.offset` to sink the bed a few centimetres under it so the road does not float on the noise.

## How the corridor works

For each terrain vertex the script finds the nearest point of the evaluated curve in XY and takes the curve's Z there.
Within `half_width` the terrain height is that Z (minus `offset`). From `half_width` out to `half_width + falloff` it
blends back to the noise with a smoothstep. Further away the terrain is the untouched noise: the test compares those
vertices with a corridor-free terrain of the same seed.

## Limits

- Nearest point is measured in XY only. A road that crosses over itself (a bridge, a spiral ramp) takes the closer branch.
- The curve is flattened across its width; there is no banking.
- Vertices are on a regular grid. A narrow `half_width` against a coarse `resolution` gives a ragged edge.
- The curve is read from its evaluated polyline, so a Bezier curve follows its resolution setting.
- The noise has no erosion and no biome logic. It is a base for sculpting or for scattering, not a finished landscape.
- Only the straight, sloping poly-curve case is covered by the test. Bezier and closed curves run through the same code
  and are untested.
