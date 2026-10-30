---
type: llm
---

PASS if the response sets the camera at a human eye height of about 1.6 m (1.5 to 1.7 m), preferably via camera_rig's `eye_height` argument (for example `"eye_height": 1.6`).
FAIL if the camera height is left at the default, is not set, or is far from eye height (for example overhead or at 5 m).
