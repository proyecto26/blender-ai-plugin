"""Apply a render preset (engine, samples, denoise, resolution, color management).
Returns the previous values so the change can be reverted: `previous` holds the engine, resolution percentage,
view transform and look, plus one `"<group>.<property>"` entry (e.g. `cycles.denoising_quality`) for every
eevee/cycles/shading property the preset changed, read before it was set.

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/render_preset.py",
                            init_globals={"ARGS": {"preset": "cycles_final"}})["result"]

ARGS:
    preset (str) eevee_preview | eevee_final | cycles_preview | cycles_final | workbench_clay | stylized_flat
                 | denoise_draft | denoise_final_still | denoise_animation | denoise_viewport | denoise_off
                 (the denoise_* presets are Cycles use-case presets; see the table in the rendering SKILL.md)
    resolution_percentage (int|None) override, e.g. 50 for quick tests
    device (str|None) Cycles device "GPU" or "CPU" (default: leave unchanged)
"""
import json
import sys

import bpy

PRESETS = {
    "eevee_preview": {"engine": "BLENDER_EEVEE", "eevee": {"taa_render_samples": 16, "taa_samples": 8, "use_raytracing": False},
                      "view": ("AgX", "AgX - Base Contrast"), "pct": 50},
    "eevee_final": {"engine": "BLENDER_EEVEE", "eevee": {"taa_render_samples": 128, "taa_samples": 16, "use_raytracing": True,
                                                          "use_fast_gi": True, "use_shadows": True},
                    "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    "cycles_preview": {"engine": "CYCLES", "cycles": {"samples": 64, "preview_samples": 32, "use_denoising": True,
                                                       "denoiser": "OPENIMAGEDENOISE", "adaptive_threshold": 0.05},
                       "view": ("AgX", "AgX - Base Contrast"), "pct": 50},
    "cycles_final": {"engine": "CYCLES", "cycles": {"samples": 1024, "use_denoising": True, "denoiser": "OPENIMAGEDENOISE",
                                                     "adaptive_threshold": 0.01, "max_bounces": 12},
                     "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    # Denoiser use-case presets (Cycles, OpenImageDenoise). Every key is a real scene.cycles property in 5.2.
    "denoise_draft": {"engine": "CYCLES", "cycles": {"samples": 32, "use_denoising": True, "denoiser": "OPENIMAGEDENOISE",
                                                      "denoising_input_passes": "RGB_ALBEDO", "denoising_prefilter": "FAST",
                                                      "denoising_quality": "FAST", "adaptive_threshold": 0.05},
                      "view": ("AgX", "AgX - Base Contrast"), "pct": 50},
    "denoise_final_still": {"engine": "CYCLES", "cycles": {"samples": 1024, "use_denoising": True,
                                                            "denoiser": "OPENIMAGEDENOISE",
                                                            "denoising_input_passes": "RGB_ALBEDO_NORMAL",
                                                            "denoising_prefilter": "ACCURATE", "denoising_quality": "HIGH",
                                                            "adaptive_threshold": 0.01},
                            "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    "denoise_animation": {"engine": "CYCLES", "cycles": {"samples": 512, "use_denoising": True,
                                                          "denoiser": "OPENIMAGEDENOISE",
                                                          "denoising_input_passes": "RGB_ALBEDO_NORMAL",
                                                          "denoising_prefilter": "ACCURATE", "denoising_quality": "BALANCED",
                                                          "use_animated_seed": False, "adaptive_threshold": 0.02},
                          "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    "denoise_viewport": {"engine": "CYCLES", "cycles": {"use_preview_denoising": True, "preview_denoiser": "AUTO",
                                                         "preview_denoising_input_passes": "RGB_ALBEDO",
                                                         "preview_denoising_prefilter": "FAST",
                                                         "preview_denoising_quality": "FAST",
                                                         "preview_denoising_start_sample": 1},
                         "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    "denoise_off": {"engine": "CYCLES", "cycles": {"use_denoising": False, "use_preview_denoising": False},
                    "view": ("AgX", "AgX - Base Contrast"), "pct": 100},
    "workbench_clay": {"engine": "BLENDER_WORKBENCH", "view": ("Standard", "None"), "pct": 100},
    "stylized_flat": {"engine": "BLENDER_EEVEE", "eevee": {"taa_render_samples": 32, "use_raytracing": False},
                      "view": ("Standard", "None"), "pct": 100},
}


def _cli_args():
    """ARGS after `--`: one JSON object, or `--args-file <path.json>` (quoting-proof on every shell)."""
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not raw:
        return {}
    if raw[0] == "--args-file":
        with open(raw[1], encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"ARGS after '--' must be one JSON object, got {raw[0]!r}; "
                         "cmd/PowerShell mangle JSON quotes, so pass --args-file <path.json> instead") from exc


def _plain(value):
    """JSON-safe copy of a property value (enums are already strings)."""
    return value if isinstance(value, (bool, int, float, str)) or value is None else list(value)


def main(preset="eevee_preview", resolution_percentage=None, device=None):
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    cfg = PRESETS[preset]
    scene = bpy.context.scene
    r, vs = scene.render, scene.view_settings
    previous = {"engine": r.engine, "resolution_percentage": r.resolution_percentage,
                "view_transform": vs.view_transform, "look": vs.look}
    r.engine = cfg["engine"]
    applied, skipped = {}, []
    for group in ("eevee", "cycles"):
        target = getattr(scene, group, None)
        for key, value in cfg.get(group, {}).items():
            if target is not None and hasattr(target, key):
                previous[f"{group}.{key}"] = _plain(getattr(target, key))
                setattr(target, key, value)
                applied[f"{group}.{key}"] = value
            else:
                skipped.append(f"{group}.{key}")
    if device and cfg["engine"] == "CYCLES":
        scene.cycles.device = device
    vs.view_transform, vs.look = cfg["view"]
    r.resolution_percentage = resolution_percentage or cfg["pct"]
    if cfg["engine"] == "BLENDER_WORKBENCH":
        shading = scene.display.shading
        for key, value in (("light", "STUDIO"), ("color_type", "SINGLE"), ("show_cavity", True)):
            previous[f"display.shading.{key}"] = _plain(getattr(shading, key))
            setattr(shading, key, value)
            applied[f"display.shading.{key}"] = value
    return {"preset": preset, "engine": r.engine, "applied": applied, "skipped": skipped,
            "view_transform": vs.view_transform, "look": vs.look,
            "resolution": [r.resolution_x, r.resolution_y, r.resolution_percentage], "previous": previous}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
