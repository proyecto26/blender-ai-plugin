# Working Live in the Open Blender Window

Users like to watch the agent work, so bounded work runs live by default. Results below were measured on Blender 5.2.3
on Windows through the official MCP server.

## Where Work Runs

| Work | Where |
|------|-------|
| Modelling, materials, lights, camera, inspection, captures | Live |
| Short previews and exports | Live; say first if the window will freeze for more than a few seconds |
| Apply, join, boolean apply, remesh, decimate | Live on a disposable copy (`scripts/work_copy.py`) |
| Final renders, video, handoff, batches | Background process, from a snapshot saved first |
| Automated tests | Never in the user's window |

Plugin scripts run in the window with no extra setup and restore the settings they touch.

## Before Editing: a Checkpoint

Code run through MCP adds no undo steps, so one undo can jump past all of it, even past the last save. Push a step
before and after each phase; one undo then reverts only that phase:

```python
import bpy
bpy.ops.ed.undo_push(message="before: add crate")
# ... the phase's edits ...
bpy.ops.ed.undo_push(message="after: add crate")
result = {"ok": True}
```

Run `bpy.ops.ed.undo()` in a later call to go back; `bpy.ops.ed.redo()` recovers an undo that went too far. Python
references to objects are invalid after either, so look objects up again by name. What the user's own Ctrl+Z restores is
not measured: do not promise it.

For a larger step, save a uniquely named copy first with `bpy.ops.wm.save_as_mainfile(filepath=..., copy=True)`. Files
already written or overwritten on disk are not covered by either.

## Traps

- **Screenshots can lie.** With the window minimized the screenshot tools return a black image, or corrupt colours if a
  render window is open, and no error. Ask the user to restore the window; do not judge the scene from such an image. A
  partly covered window captures correctly.
- **`bpy.data.is_dirty` is not evidence.** It can stay false after edits made through MCP, so it does not prove the file
  on disk is current. An `undo_push` sets it true. Save a snapshot before background work, because a background process
  reads the disk, and the `*_for_cli` tools skip their own save when the flag is false.
- **Renders block everything.** Code runs on Blender's main thread: during a synchronous render the window freezes and
  other requests wait. Windows may show "not responding" after several seconds. Long renders belong in a background process.
- **A timeout is not a failure.** The client gives up after 300 s, but the code keeps running, and requests left behind
  still execute. Do not retry, and do not edit yet. See "After a Timeout".
- **Framing changes state.** `jump_to_view3d_object_by_name` selects only the target, makes it active, and leaves Edit
  Mode and camera view. Use it between phases, not during one.
- **Render tools pick the folder.** `render_viewport_to_path` and `render_thumbnail_to_path` keep only the file name and
  write to a Blender temp folder. Use the returned path and copy the file out.

## After a Timeout

A reply to a small inspection call only shows that Blender's main thread is free. A render started by a tool can still
be running as a job, and a render tool whose client has gone never puts `scene.render.filepath` back. So before the next
edit:

1. Check that no job is running, and repeat until this is false:
   `any(bpy.app.is_job_running(j) for j in ("RENDER", "RENDER_PREVIEW", "OBJECT_BAKE", "COMPOSITE"))`
2. Compare `scene.render.filepath` and the settings the step touched with the values you read before it, and restore
   any that differ.
3. Check the scene and the output files, and tell the user what you found. Only then decide whether to run it again.

## Background Work

Use a separate process for long work, on every platform: run `blender -b file.blend --python script.py` and have the
script write its result to a JSON file. Save the file first, and tell the user the process's output path.

- `execute_blender_code_for_cli` opens a file on disk in a separate process and needs `BLENDER_PATH` set to a Blender
  executable. It stops the process after 120 s, with no option to extend that, so keep it to short checks.
- **Microsoft Store installs cannot use it:** the launcher runs the code but drops its output, and `blender.exe` in
  `WindowsApps` cannot be started. Use `blender-launcher.exe` in the command above.
- **`No result marker in Blender output` means the outcome is unknown,** because the code may have run. Check for its
  outputs before running anything again.
