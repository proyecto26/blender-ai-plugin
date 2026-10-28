"""Render the plugin icon (.claude-plugin/icon.png, 1024x1024) from the video's neon hero shot.

    blender -b --factory-startup --python docs/video/icon.py
"""
import os
import runpy
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))

video = runpy.run_path(os.path.join(HERE, "build_video.py"), init_globals={"ARGS": {"shots": ["__none__"]}})
video["look"]("neon", 1, 64)
scene = bpy.context.scene
scene.render.resolution_x = scene.render.resolution_y = 1024
scene.render.resolution_percentage = 100
cam = bpy.data.objects["CAM_Hero"]
cam.parent = None
video["skill"]("camera-cinematography", "camera_rig.py", name="CAM_Hero", target="SM_SupplyCrate", lens_mm=50,
               azimuth_deg=30, elevation_deg=22, fill=0.8, aspect="1:1")
scene.frame_set(1)
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.join(REPO, ".claude-plugin", "icon.png")
bpy.ops.render.render(write_still=True)
result = {"icon": scene.render.filepath}
print(result)
