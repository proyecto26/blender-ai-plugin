# Strategy: where the agent runs Blender work (live window, background, isolated)

## Decision

Users want to watch the agent work in the Blender window they have open, so **bounded work runs live by default**.
Long or batch work runs in a background process from a saved snapshot. Automated tests never touch the user's window.

| Work | Where |
|---|---|
| Modelling, materials, lights, camera, inspection, captures | Live |
| Short, bounded previews and exports | Live, saying first if the window will freeze for more than a few seconds |
| Destructive steps | Live on a disposable copy (`work_copy.py`) |
| Final renders, video, handoff, batches | Background process, from a snapshot saved first |
| Automated tests | Isolated, never the user's window |
| Live acceptance | The user's window, a disposable file, the user watching and agreeing |

## Live rules, each from a measured result

Measured on Windows 11, Microsoft Store Blender 5.2.3, blender-mcp 1.0.3, and re-tested by an independent agent.

1. **Check the window before trusting a screenshot.** Minimized, the screenshot tool returns a black image, or corrupt
   colours if a render window is open, with no error. A partly covered window captured correctly; a fully covered one
   is untested. Judge the image, and ask the user to restore the window.
2. **Checkpoint before editing.** Python-run edits add no undo steps, so one undo can jump past all of them, even past
   the last save (`ed.redo` recovered it). `bpy.ops.ed.undo_push` before and after a phase makes one undo revert only
   that phase. Saving a uniquely named copy with `save_as_mainfile(copy=True)` is the recovery boundary for bigger steps.
   What the user's own Ctrl+Z restores is unmeasured.
3. **`is_dirty` is not evidence.** It stays false after agent edits, so `*_for_cli` tools would read the older file on
   disk (read from source, not run). `undo_push` sets it true. Save a snapshot before any background work.
4. **Synchronous renders block everything.** 25 s of render blocked the call and every other request, and Windows
   flagged the window as not responding from about 8 s. Long renders go to a background process.
5. **After a timeout, do not retry or edit.** The client gives up at 300 s live too; the code keeps running and abandoned
   requests still execute. An answer to a small call only shows the main thread is free: a tool's render may still be a
   running job, and `deferred_tool.poll` drops a disconnected client before its checker restores `render.filepath` (read
   from source, not run). Wait for `bpy.app.is_job_running` to be false, reconcile the settings, check the outputs.
6. **Framing changes state.** `jump_to_view3d_object_by_name` changes selection and active object, leaves Edit Mode and
   camera view. Use it between phases only.
7. **Render tools choose their own folder.** `render_viewport_to_path` writes to a Blender temp folder and reports it.
   Use the returned path and copy the file out.

The live run also showed the core scripts work there without any setup: validate, capture, shot list, preview, export.

## Background on Windows

`execute_blender_code_for_cli` cannot return results on Microsoft Store installs: the launcher runs the code but drops
stdout, and `blender.exe` under `WindowsApps` gives access denied (reported upstream as lab/blender_mcp#69). So:

- The launcher is never a valid `BLENDER_PATH` for `*_for_cli` tools.
- `No result marker` means **outcome unknown**: the code may have run. Check outputs before running anything again.
- `*_for_cli` tools give up at 120 s (through the launcher Blender kept running to at least 150 s) with no override (`_CLI_TIMEOUT`), so long work on every platform uses a direct
  `-b file.blend --python script.py` process with a script that writes JSON, as the tests do; Store users run it through
  the launcher.
- Other installs: set `BLENDER_PATH` to `blender.exe`. Upstream #42 reports a hang on Windows; untested here. macOS and
  Linux keep the existing guidance.

## Contributor-only: isolated MCP instance

To test skills through the real MCP tools unattended:
`blender-launcher.exe --background scratch.blend --online-mode --command blender_mcp --port 9877`, with
`BLENDER_MCP_PORT=9877` on the server. Tested through a JSON-RPC client, not yet a Claude session. It needs discipline:
check the port is free, since Windows allows a second bind without error; guard `revert_mainfile` and `os._exit(0)` in
the same call with `bpy.app.background` and the scratch file's absolute path, since the client may have reached another
Blender; revert first, since a fresh instance has no window context and export scripts fail; one instance per test, since
state leaks. It stays out of user docs.

## Doc changes (no new scripts)

- `skills/blender-mcp-workflow/references/mcp-tools.md`: fix the `print` claim, the launcher advice; add `undo_push`
  and the unknown-outcome rule.
- `skills/blender-mcp-workflow/SKILL.md`: a short live section with the rules above; probe step not tied to `*_for_cli`.
- `agents/blender-design-orchestrator.md`: same rules for choosing where work runs.
- `docs/BLENDER_MCP_SETUP.md`, `README.md`: install table; live is the default.
- `AGENTS.md`, `docs/local_skill_development.md`: automated tests stay isolated; allow one attended live acceptance on a
  disposable file; document the isolated instance.

## Not yet validated

A full orchestrator run from a real Claude session, what Ctrl+Z restores, a real job past 300 s, zip or MSI installs,
and a fully covered window. The docs must not claim these.
