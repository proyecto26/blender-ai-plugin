# Iteration 16: Phase 2, medium-value items

Source: the "Phase 2" list in `docs/plans/iteration-15-agent-skills-comparison.md`. Low-value items (PBR statistics,
auto retopology, outline normals, hair cards) stay in the roadmap. Shared rules: the iteration 15 verdict, result-file,
FINISHED and restore contracts; scripts never delete or overwrite user data and only remove datablocks they created.

## Batch P: preflight, materials, budgets (`blender-mcp-workflow`)

- **P1 `env_report.py`** (new, read only): Blender version, available render engines, enabled add-ons, GPU devices
  when Cycles is present, and the valid values of any enum the caller names (`enums=["BooleanModifier.solver", ...]`;
  an unknown name is an error entry, not a crash). Acceptance: a snapshot of what the script could touch is equal
  before and after: datablock names per type, selection, active object, mode, frame, render engine and device, the
  enabled add-on list and Cycles device preferences, and `bpy.data.is_dirty` (tested with a clean and an already
  dirty file); a known enum returns its real values.
- **P2 material dependencies in `validate_asset.py`**: FAIL when a face uses an empty slot or a slot index beyond the
  slots; FAIL when an image node's file is missing and the image is not packed; WARN when an sRGB image's Color output (not its Alpha output) feeds a data
  socket (Normal, Roughness, Metallic, Alpha, Height via Normal Map or Bump) or a Non-Color image feeds Base Color.
  Each with a bad and a good fixture.
- **P3 budgets in `validate_asset.py`**: `max_materials`, `max_texture_px`, `max_bones` (unset means not checked):
  over budget is FAIL with the measured value. Per audited object: `max_materials` counts distinct materials used by
  its faces; `max_texture_px` is the largest image dimension (width or height) among images its materials use, each
  image counted once; `max_bones` counts deform bones of the armatures its Armature modifiers point to. A boundary
  fixture at exactly the limit PASSes.

## Batch V: views and round trip

- **V1 `capture_views.py`**: `isolate=True` shows only the asset (others hidden for the capture), `wire=True` adds a
  wireframe view, `contact_sheet=True` writes one image tiling all views. Acceptance: hide flags, shading, object
  colors, render resolution, file format and camera are restored, also when a capture fails; the sheet's pixel size
  equals the tiled views.
- **V2 `export-pipeline/scripts/fbx_roundtrip.py`** (new): export the selection to a new file (refuse an existing file
  unless `overwrite=True`), import it into a temporary scene, compare per-object world dimensions (0.1%), bone names
  and parents, and action names; then remove only the temporary scene and the datablocks the import created.
  Identity: the import runs into the same file, so Blender renames clashes, and names alone cannot match. Before
  export each selected object gets a temporary custom property `bap_rt_id` (a counter) and FBX writes custom
  properties (`use_custom_props=True`); imported objects are the set that appeared during the import, matched by that
  id, never by name. The temporary property is removed from the originals in `finally`. Clips are matched in export
  order per armature, and their names compared after dropping an `<armature>|` prefix and the importer's `.NNN`
  suffix. An exported object with no imported match is a FAIL entry naming it. Acceptance: the user's datablock names
  and custom properties are unchanged after; a scaled-wrong export (global_scale 2) FAILs; `SM_Box` and `SM_Box.001`
  exported together, and two actions on one armature, pass.

## Batch B: bake and animation

- **B1 `bake_maps.py` controls**: several high-poly sources, `cage` object or `cage_extrusion`, `max_ray_distance`,
  `uv_layer`, `normal_convention` ("OPENGL" or "DIRECTX": green flipped for DirectX), a metallic map (Cycles has no
  metallic pass: wire metallic into emission temporarily and restore the nodes), and `orm=True` packing AO, roughness
  and metallic into R, G, B of one image. Acceptance: DirectX green equals 1 minus OpenGL green within 1/255; nodes
  identical after apart from the one `SK_BakeTarget` image node the bake leaves by design, also when a bake fails midway (inject the failure); ORM channels equal the separate maps. File
  collisions: any existing image datablock of the target name, at any size, is refused unless `overwrite=True`
  (then it is reused and its pixels, colorspace and path change, as documented); an existing output file is refused
  unless `overwrite=True`. Fixture: a same-size image of the target name is left untouched without `overwrite`.
  The iteration 15 tests that rerun a bake without `overwrite` (`test_iter15_uv.py`) are updated to pass
  `overwrite=True`, keeping their regression coverage.
- **B2 `animation/scripts/bake_check.py`** (new): checks that the baked action alone reproduces the source motion.
  The target is evaluated with its bone constraints, its drivers and its NLA temporarily muted and only the baked
  action assigned (so a constraint or driver cannot supply the motion), and restored after. Per mapped bone and frame it compares the pose relative
  to rest (evaluated `matrix` against the rest matrix, so different rest orientations are allowed): the rotation, and
  the translation relative to rest of every mapped bone (not only the root), scaled by the ratio of rig heights (so
  proportions may differ). FAIL above 2 degrees rotation or 1% of the target rig height for translation. A piston
  fixture (a bone that only translates) whose bake lost its location keys FAILs. Scale relative to rest is compared too
  (FAIL when any axis differs by more than 1%), and a hydraulic fixture (Stretch To) whose bake lost its scale keys
  FAILs. Measured only when the baked action exists and has keys on the mapped bones, else
  FAIL. Fixtures: a correct bake PASSes; a wrong keyed action whose motion was masked by a Copy Rotation constraint
  FAILs; the same wrong action masked by a driver FAILs; a different rest orientation with the same motion PASSes.
  Restores frame, actions, constraints, drivers and NLA.
- **B3 loop check in `bake_check.py`**: for a cyclic action, compare the pose at the first and last frame (rotation
  within 1 degree, location within 0.5% of rig height) and the velocity across the seam (the step last-1 to last and
  the step first to first+1 differ by at most 25% plus a floor of 0.2 degrees per frame for rotation and 0.1% of rig
  height per frame for location). `root_motion=True` leaves the root's translation out of the pose comparison and
  checks only its velocity, with the same linear rule. A pop at the seam FAILs.

## Batch D: deformation

- **D1 `cloth-sim/scripts/garment_check.py`** (new): over rest plus the stress poses, count garment vertices inside the
  body (closest point and normal side on the evaluated body); coverage is the share of garment vertices that had a
  body point in range; coverage below 0.9 is NOT_CHECKED, never PASS; restores pose, frame and actions. Each pose must
  be reached (evaluated rotation within 5 degrees of the request, as in `stress_check.py`), else NOT_REACHED (FAIL).
  The body must be a closed, consistently wound mesh, else the check is NOT_CHECKED. Fixtures: a blocked pose FAILs
  even with full coverage; a garment that pokes through in one pose FAILs; a loose garment PASSes.
- **D2 `rigging/scripts/shape_key_audit.py`** (new, read only): keys with no delta (max below 1e-6 of the mesh size),
  non-finite deltas, keys relative to a missing key, keys whose drivers target missing objects or bones, `.L`/`.R`
  pairs whose mirrored deltas differ by more than 1% of the mesh bounding-box diagonal (mirror across X, vertices
  matched by nearest mirrored position within 1e-4 of that diagonal; unmatched vertices make the pair NOT_CHECKED).

## Batch E: environment and procedural

- **E1 `environment-artist/scripts/kit_check.py`** (new, read only): modular pieces on a grid: dimensions are multiples
  of `grid_m`, origin on a grid point, and the vertices on each bounding-box face (the snapping faces: within 1e-4 m
  of the face plane) sit on grid lines in that face, so neighbours meet. Tolerance 1e-4 m.
- **E2 scatter limits in `scatter_props.py`**: `min_spacing_m`, `max_slope_deg`, `height_range_m`; placement honours
  them and the result reports the measured minimum spacing, maximum slope and height range of the placed props, each
  compared to its limit (a violation FAILs).
- **E3 `geometry-nodes/scripts/gn_diagnostics.py`** (new, read only on data): per Geometry Nodes modifier: missing
  node group (FAIL); a Geometry-type group input that nothing uses inside the group is only listed (INFO: a
  generator such as a Cube to Group Output is valid), and so are other unlinked inputs, which keep their defaults; a
  Group Output with no Geometry link is FAIL; node warnings from the modifier (warnings WARN, errors FAIL); the evaluated
  geometry after that modifier, measured with the later modifiers' viewport visibility temporarily off and restored
  (empty is FAIL, where empty means no mesh, curve, point cloud, volume or instance component; a curve-only or
  unrealized-instance output, each a fixture, is not empty); evaluation time from the modifier's own timing.
- **E4 `sculpting/scripts/sculpt_prep.py`** (new): duplicate the object (the original is never changed), apply its
  modifiers on the duplicate, voxel remesh at `voxel_size_m`, report vertex count and that the original is unchanged.

## Verification

Each batch: tests in `tests/blender/test_iter16_<batch>.py` (bad fixture FAIL, good fixture PASS, state restore; for
changes to existing scripts, a test seen failing on the old code). Every batch then goes through Seldon with Codex until
approved, each finding reproduced by a failing test first. Then all suites, docs (CHANGELOG, ROADMAP), and a PR.
