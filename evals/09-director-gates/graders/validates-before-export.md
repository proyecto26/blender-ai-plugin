---
type: llm
---

PASS if the response runs (or tells me to run) the plugin's `validate_asset.py` BEFORE the export step and states that the export happens only when validation has no FAIL.
FAIL if export comes first, validation is skipped, or the response exports regardless of validation FAIL.
