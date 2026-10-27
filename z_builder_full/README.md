# Z Builder — full web-source integration (corrected scope)

**Scope is exactly:**
1. The complete original Scene Builder web application, including its Media Library,
   Director V25, render worker, queue, UI, settings, effects and existing behavior.
2. Only the existing Z Studio "Create / Open in CapCut" project draft logic, imported
   from the original Z Studio module. No other Z Studio features.
3. A new **standalone Windows Z Builder**, preserving the existing web UI rather than
   a cut-down Qt rewrite. No .exe unless explicitly requested.

The previous \`z_builder/\` v1 is a limited Director-to-draft prototype and **does
not satisfy this scope**.

## Confirmed upstream source boundaries

- \`apps/scene-builder/part01/\`: actual FastAPI web server, templates, CSS/JS, Media
  Library, Director V25 interface, projects and queue.
- \`apps/scene-builder/part02/\`: rendering, captions, media retrieval, effects,
  timing and worker.
- \`z_builder/capcut-draft.js\`: existing Z Studio CapCut writer.

The parity assembler takes **all files** from both original parts (except hidden
rollbacks, databases and secrets), records SHA-256 digests and attaches the original
Z Studio CapCut writer. It makes no changes to the VPS and does not fabricate a
replacement for the original web frontend.

**Implementation status:** This workbench bundles/verifies real complete source;
it is **not yet a usable combined Windows application**. Running the original
Linux/VPS pipeline on Windows, mapping its job outputs and media into CapCut drafts,
preserving authentication and external services, and validating CapCut on a real
Windows installation must be solved before this can be called complete.
Do not distribute the bundle as a ready-to-run application.

## Non-negotiable acceptance checks for the final app

- Dashboard, queue, Scene Plan, presets, visual selection/audit, original render,
  captions, audio, animations, LUTs, settings and history behave as in upstream.
- Media Library's import, images/videos, clean control, auto approval and catalog
  remain intact; both Library Only and Library First/Pexels Fallback remain.
- Add only a CapCut handoff to the **same rendered/reviewed project** with
  actual selected footage, exact timing and audio. Do not export a new rough cut.
- Handle unsupported CapCut-only effects explicitly without changing the
  standard Scene Builder rendering/output.
- Original VPS_1 production, Z Studio and old desktop app remain unchanged.
