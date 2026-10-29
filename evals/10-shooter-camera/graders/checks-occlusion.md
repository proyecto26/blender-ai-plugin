---
type: llm
---

PASS if the response checks the camera_rig result's `occluded_by` (expects an empty list) and/or `visible_fraction`, and says what to change (for example a nearer `max_distance`, different angle or moving cover) when it is not empty.
FAIL if it never checks for objects between the camera and the subject.
