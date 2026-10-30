# Routing eval (DEV set)
Measures whether a request routes to the right Blender skill via the Skill tool, with no Blender connection.
- 95 per-skill cases (one per skill), 6 negatives (`neg-*`, must trigger no skill), 9 near-miss pairs (`near-*`).
- 15 symptom-worded delivery cases (`deliv-*`): the user describes what went wrong in the engine ("tiny in
  Unreal", "players walk through walls") without naming the skill's terms. Added after held-out delivery
  routing lagged; written from the skills' jobs, never from the held-out prompts.
- Prompts were written from skill bodies only, never from frontmatter descriptions, to avoid wording leakage.
- `expect.json` holds `expected`, `cluster`, `also_ok` and `forbidden`; it drives the primary-route scorer.
- The first Skill call is the primary route; a `forbidden` sibling chosen first counts as a confusion.
- `graders/*.md` are plain `tool_used` checks (regex on the Skill input; negatives require zero Skill calls).
- Run: `claude plugin eval . --eval-dir evals-routing --ablation none --keep-temp --json <out>`
- This is the DEV set for tuning descriptions; keep a separate held-out set for final validation.
- Clusters: core, delivery, genre, world, mood, style, discipline, near-miss, negative.
- Add a case by creating `<name>/prompt.md`, `graders/*.md` and `expect.json`.
