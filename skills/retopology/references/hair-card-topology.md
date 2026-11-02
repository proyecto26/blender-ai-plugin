# Hair card topology

How to build the mesh of a game hair card so it bends, costs little, and does not show its edges. Where cards go on the
head, the atlas layout, and card counts per LOD are in the `hair-groom` skill (`references/hair-card-atlas.md`,
`references/groom-flow-regions.md`, and the LOD table in its `SKILL.md`). This file covers the topology of a single card.

## What a card is

A flat or slightly curved strip, textured with hair on a transparent background. The silhouette comes from the alpha in the
texture, so the mesh can stay simple.

## Topology rules

| Part | Rule | Reason |
|---|---|---|
| Rows along the length | 2 to 4 segments (3 to 5 rows of vertices) for a card that must bend with the head or wind; 1 segment for a short, stiff card | each segment is a place the card can bend; extra rows cost triangles and add no shape |
| Across the width | 1 segment for a flat card; 2 (a centre ridge) for a card with a curved cross-section | a ridge stops the card reading as a flat sheet from the side |
| Quads, then triangulate | build as quads in a regular grid; triangulate only at export | even, predictable triangulation in the engine |
| Taper | narrow the width to about 20 to 40% at the tip, and move vertices rather than cutting the mesh | hair thins toward the ends; the alpha can finish the point |
| Root | root row sits just under the hairline or inside the scalp cap, never floating above it | no gap between skin and hair |
| Orientation | edge loops cross the length (like rungs), and the long edges follow hair flow | the card bends along the flow and not across it |
| Normals | all facing outward from the head, or all the same way for a double-sided material | flipped cards show as dark patches |

## Triangle count

A strip with `n` segments along the length and `k` across has `2 * n * k` triangles.

| Card | Segments (n by k) | Triangles |
|---|---|---|
| Short stiff | 1 by 1 | 2 |
| Standard | 3 by 1 | 6 |
| Curved cross-section | 3 by 2 | 12 |
| Long, wind-animated | 4 by 2 | 16 |

Multiply by the card count of the LOD (see `hair-groom` -> `SKILL.md`: for example 80 to 200 cards for a hero close-up, 8 to
20 for distant). A hero head with 150 curved cards of 12 triangles is 1,800 triangles, small beside the polycount tiers for
characters in `blender-mcp-workflow` -> `references/polycount-budgets.md`. The cost that grows with cards is not
triangles but overlap: many layered transparent cards cost fill rate per pixel. That is why LODs drop cards.

## UV layout

- Straight strips, root at one end of the UV rectangle, tip at the other, so the texture always runs root to tip. The UV
  rectangle fills the atlas cell with the padding set in `hair-card-atlas.md`.
- Mirror and reuse atlas cells across cards: one cell, many cards. Rotating a UV rectangle by 180 degrees flips root and tip;
  keep root-to-tip direction consistent or the texture's gradient runs backwards.

## Building from a groom

For a groom made with curves (see `hair-groom`): one card per guide curve or per clump of guides; set the card's long axis
along the curve; resample the curve to the number of rows above; extrude to the width. Do this with the shrinkwrap-style
approach used for body retopology: keep the groom as a hidden reference and check the card silhouette against it from the
game camera (see `retopology` `SKILL.md`, Validation Checklist).

## Failure signs

| Sign | Cause | Fix |
|---|---|---|
| Cards look like paper from the side | flat cross-section, no ridge, one layer | use a curved cross-section; add a second layer at an angle |
| Visible edge line where cards meet the scalp | root floats above the scalp | sink the root row into the scalp cap |
| Bright or dark patches | flipped normals, or inconsistent facing | recalculate normals outward; check double-sided setting |
| Hair texture runs from tip to root | UV flipped | flip UV; check every card |
| Frame time rises with many cards | transparent overdraw | fewer cards in the LOD; fewer overlapping layers |
