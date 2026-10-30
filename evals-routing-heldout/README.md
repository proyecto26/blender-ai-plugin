# Held-out routing eval set
Frozen held-out set: 95 per-skill cases, 6 negatives (neg-*) and 9 near-miss cases (near-*).
Written independently of the skill descriptions and of evals-routing/, in natural user voice.
It exists only to measure routing, never to tune descriptions or prompts.
Do not edit these cases to fit results; if a case is wrong, record it and add a new set instead.
Each case: prompt.md, graders/*.md (tool_used on Skill), expect.json (expected, cluster, forbidden).
Run with: --eval-dir evals-routing-heldout --ablation none --keep-temp --json <out>
Clusters: core, delivery, genre, world, mood, style, discipline, negative, near-miss.
