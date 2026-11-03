---
name: qa-review
description: "Final QA gate for Blender assets: screenshots, checklists, naming and topology audit, ship/no-ship verdict. Use for 'is this ready to ship' or a last check before export. Not for fixes (use blender-mcp-workflow fix_asset, asset-optimization)."
license: MIT
metadata:
  author: https://github.com/arjun988
  version: "1.0.0"
  domain: blender
  role: specialist
  category: core
  stage: validate
  triggers: QA, quality assurance, review, validation, checklist, screenshot review, ship check, art review
  related-skills: asset-optimization, export-pipeline, blender-director, lookdev
---

# QA Review

Screenshot-backed review. Checklist gate. Explicit ship / no-ship.

## When to Use

- Before export or handoff
- After major modeling/lookdev milestones
- Reference-match final compare
- Periodic scene health checks

## Workflow

```
Gather brief budgets → Screenshot key angles → Run checklists
  → List defects (severity) → Fix or reject → Re-verify → Verdict
```

## Required Screenshots

1. 3/4 hero angle
2. Ortho or profile if proportion-critical
3. Wireframe or poly overview (optional but useful)
4. Material/light beauty
5. Vs reference (if reference task)

Use `get_screenshot_of_area_as_image("VIEW_3D")` via MCP when connected.

## Checklists (load as needed)

- `blender-mcp-workflow` skill → `references/validation-checklist.md`
- `blender-mcp-workflow` skill → `references/visual-match-checklist.md` (reference tasks)
- `blender-mcp-workflow` skill → `references/naming-conventions.md`
- `blender-mcp-workflow` skill → `references/polycount-budgets.md`

## Scripted Checks

For a multi-object asset or scene, run the `blender-mcp-workflow` skill's `clash_audit.py` script next to the checklists.
It reports penetrating pairs with an estimated depth, objects hidden inside others, and floating parts, on the evaluated
meshes (modifiers count; touching faces do not clash). Any clash, contained object or floating part is a defect: a clash
or containment is a Major (Blocker when it breaks a mechanism or an export), a floating part is a Major unless the brief
says it floats. A `not_measured` entry (an open mesh has no inside) is never a pass: close the mesh or say what was not
checked. When a run folder exists, pass `evidence_path` inside it so the verdict is backed by the script's own result file.

## Defect Severity

| Level | Meaning |
|-------|---------|
| Blocker | Wrong scale, broken normals, fails budget badly |
| Major | Silhouette/readability issues, bad pivots |
| Minor | Naming, minor shading, small gaps |
| Note | Optional polish |

## Verdict Template

```markdown
## QA Verdict: [Asset]

**Result:** SHIP / SHIP WITH NOTES / NO-SHIP
**Budgets:** [tris/textures] vs target
**Screenshots:** [listed]
**Blockers:** ...
**Majors:** ...
**Minors:** ...
**Next actions:** ...
```

## Constraints

### MUST DO
- Give explicit verdict
- Attach or capture screenshots for visual claims
- Re-check after fixes before flipping to SHIP

### MUST NOT DO
- Rubber-stamp without screenshots on visual tasks
- Ignore budget overruns without approval

## Reference Guide

| Topic | Reference | Load When |
|-------|-----------|----------|
| Qa Verdict Template | `references/qa-verdict-template.md` | When needed |
| Screenshot Angles | `references/screenshot-angles.md` | When needed |
