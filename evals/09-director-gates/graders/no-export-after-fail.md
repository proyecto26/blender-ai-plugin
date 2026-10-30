---
type: llm
---

PASS if the response never proceeds to export after a FAIL verdict: it fixes and re-validates, or stops and reports when the same check fails twice (naming a cause such as geometry, materials or export) instead of retrying blindly or exporting anyway.
FAIL if it says to export despite a FAIL, or to keep retrying the same failing step without classifying the cause.
