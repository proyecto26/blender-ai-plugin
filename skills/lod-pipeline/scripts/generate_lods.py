"""Generate LOD copies of a mesh with Decimate (collapse) at given ratios.
The source becomes/keeps LOD0; copies are named <base>_LOD1.. and placed in a
COL_LODs collection. Copies share nothing with the source (single-user data).

    import runpy
    result = runpy.run_path("<skill_dir>/scripts/generate_lods.py", init_globals={"ARGS": {
        "object": "SM_Crate_01", "ratios": [0.5, 0.25, 0.1]}})["result"]

ARGS:
    object   (str, required) source mesh (LOD0)
    ratios   (list[float])   decimate ratios for LOD1..N (default [0.5, 0.25, 0.12])
    apply    (bool) apply the Decimate modifier on copies (default True - engines need real geometry)
    rename_source (bool) rename source to <base>_LOD0 (default False)
    offset_x (float) spacing between LODs for side-by-side review (default 0 = stacked; stacked
                     copies get hide_render so renders show LOD0 only - exports are unaffected)
"""
import json
import sys

import bpy


def _cli_args():
    if "--" in sys.argv:
        raw = sys.argv[sys.argv.index("--") + 1:]
        if raw:
            return json.loads(raw[0])
    return {}


def _tris(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    ev.to_mesh_clear()
    return count


def main(object, ratios=(0.5, 0.25, 0.12), apply=True, rename_source=False, offset_x=0.0):
    src = bpy.data.objects.get(object)
    if src is None or src.type != "MESH":
        raise ValueError(f"mesh not found: {object}")
    base = src.name[:-5] if src.name.endswith("_LOD0") else src.name
    if rename_source and not src.name.endswith("_LOD0"):
        src.name = base + "_LOD0"
    col = bpy.data.collections.get("COL_LODs")
    if col is None:
        col = bpy.data.collections.new("COL_LODs")
        bpy.context.scene.collection.children.link(col)
    lods = [{"name": src.name, "ratio": 1.0, "tris": _tris(src)}]
    for i, ratio in enumerate(ratios, start=1):
        name = f"{base}_LOD{i}"
        old = bpy.data.objects.get(name)
        if old:
            data = old.data
            bpy.data.objects.remove(old, do_unlink=True)
            if data.users == 0:
                bpy.data.meshes.remove(data)
        lod = src.copy()
        lod.data = src.data.copy()
        lod.name = lod.data.name = name
        lod.location.x += offset_x * i
        lod.hide_render = offset_x == 0  # stacked LODs export with LOD0 but must not render over it
        col.objects.link(lod)
        dec = lod.modifiers.new("LOD_Decimate", "DECIMATE")
        dec.decimate_type = "COLLAPSE"
        dec.ratio = ratio
        dec.use_collapse_triangulate = True
        if apply:
            with bpy.context.temp_override(object=lod, active_object=lod,
                                           selected_objects=[lod], selected_editable_objects=[lod]):
                bpy.ops.object.modifier_apply(modifier=dec.name)
        lods.append({"name": lod.name, "ratio": ratio, "tris": _tris(lod)})
    base_tris = lods[0]["tris"] or 1
    for entry in lods:
        entry["percent_of_lod0"] = round(100 * entry["tris"] / base_tris, 1)
    return {"lods": lods, "collection": col.name}


ARGS = globals().get("ARGS") or _cli_args()
result = main(**ARGS)
if bpy.app.background and __name__ == "__main__":
    print(json.dumps(result, indent=2))
