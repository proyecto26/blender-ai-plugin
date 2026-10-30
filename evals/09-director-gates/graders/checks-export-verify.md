---
type: llm
---

PASS if, after the export (export_godot.py or export_asset.py), the response reads the returned `verify` result (ok true, no missing, no leaked) and treats `checked: false` as NOT_CHECKED rather than as success.
FAIL if it reports success from the file merely existing, or never mentions the export's verify result.
