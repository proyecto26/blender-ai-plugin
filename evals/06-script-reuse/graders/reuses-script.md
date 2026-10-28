---
type: llm
---

PASS if the response runs (or tells me to run) the plugin's tested `scatter_points.py` script with arguments that fit the request (surface GEO_Terrain, collection COL_Rocks, random scale/rotation or seed), e.g. via runpy with an ARGS dict, and does not ALSO hand-build an equivalent node tree as the primary solution.
FAIL if it only hand-writes a geometry-nodes or particle setup from scratch, or calls the script with arguments that do not match the request.
