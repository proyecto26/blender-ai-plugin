# Clothing for a simulated character

This is the character side of clothing: how to model garments so they can be simulated, layered and handed to the rig.
The simulation itself (cloth settings, pin groups, caches, bake targets) is in the `cloth-sim` skill; load it for the run.

## Decide per garment: skin, simulate, or both

| Garment | Approach | Why |
|---|---|---|
| Tight shirt, trousers, gloves, boots | Skinned to the rig | Follows the body; a sim adds cost and no visible gain |
| Loose shirt, jacket body | Skinned, plus a sim only for hero close-ups | Drape on the torso is mostly the rig |
| Cape, skirt, long coat tails, scarf | Simulated (or bone chains for games) | Moves independently of the body |
| Armour plates | Rigid, parented to a bone | Does not bend |
| Real-time game character | Bone chains or baked shape keys instead of a live sim | See `cloth-sim` -> `references/bake-targets.md` |

Say which approach each garment uses in the brief, before modelling. A garment built for a sim and later skinned (or the
reverse) needs different topology and usually gets rebuilt.

## Model the garment

- Separate mesh per garment: `SM_Char_[Name]_Cloth_[Piece]`, never joined to the body (see `SKILL.md`).
- Start from the body's shape, push outward, and leave a gap: a first guess of 5 to 10 mm at skin level for thin cloth,
  more for a coat. Layers stack in order (underwear, shirt, jacket), each outside the one below by at least that gap, or the
  sim starts with surfaces already inside each other and pops.
- Give it thickness only if it will be seen from the edge (collar, cuff, hem). A single sheet is cheaper and simulates
  better; add a Solidify modifier after the sim.
- Quads, even density, no long thin triangles on folds. Sim density: enough that a fold has at least 3 to 4 faces across it;
  too coarse and it cannot fold, too fine and it is slow. Settle on a density by running a short test.
- Keep hems, collars and seams on loops of the mesh, so pins and stiffness groups follow them cleanly.
- Apply scale and rotation on the garment before any sim.

## Collision body

The body the cloth collides with is not the render body.

- Make a simplified body: no fingers, no ears, no inner mouth, closed holes where limbs meet the torso. A few thousand
  triangles is plenty (a starting value; the point is to be much lighter than the hero mesh).
- Smooth it enough that cloth does not catch on edges. Pose it in the same pose as the garment's rest state.
- Hide it from render, and name it so it is easy to find: `COL_Body_Proxy` or similar.
- Margin: cloth stops at the collision distance from the surface, so the visible gap equals the distance. Set it to the
  garment gap above, then adjust by looking.

## Hand-off to the rig

- Skinned garments take weights from the body: Data Transfer modifier (vertex groups, nearest face interpolated) from the
  body mesh to the garment, then clean up by hand at cuffs and collars. Check the maximum number of influences per vertex
  (4 for most game engines, per `rigging` skill).
- Simulated garments take no weights from the rig except pins: pin the waist, collar, shoulder seams with a painted
  falloff, not a hard 0 and 1 edge, or the cloth creases along the line.
- Run the sim from a pre-roll: put the body in rest pose, settle the cloth for 20 to 60 frames (see
  `cloth-sim` -> `references/cloth-settings-presets.md`), then start the animation.
- Test the garment in the extreme poses in `rigging`: arms up, deep crouch, neck turn. A sim that passes only in the rest pose
  fails the first time the character moves.

## Failure signs

| Sign | Likely cause | Fix |
|---|---|---|
| Cloth pops on frame 1 | surfaces start inside the body or each other | enlarge the gap, or pre-roll from rest pose |
| Cloth explodes or jitters | very small faces, too few quality steps, or colliders with sharp edges | coarser mesh, raise quality steps, smooth the collision body |
| Cloth passes through the arm in fast moves | collision margin too small for the speed | raise quality steps and collision distance; slow the move for the test |
| Hem crumples into a ball | self collision on a thin sheet | turn self collision off first; add only if layers overlap |
| Crease along the pin line | binary pin weights | paint a soft falloff |
| Garment is too stiff or too floppy | settings do not suit the fabric | start from the preset in `cloth-settings-presets.md`, then change one value |
| Skinned garment tears at the elbow | weights not transferred, or too few loops | transfer weights, add a loop at the joint |
