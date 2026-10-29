# Agent export procedure — reuse upstream capability 15

Read `upstream/references/capabilities/15-export.md`, accessibility-controls.md and
keyboard-shortcuts.md first. Those describe a demonstrated single-project procedure, not
an executable batch program. Upstream baseline 9.4.0.4015, English Windows, 1920px/125%.
Coordinates in that document are historical observations, never blind replay targets.

- Run detect. Stop if the running version is not the baseline or if multiple CapCut instances
  are visible. Desktop must be active/unlocked. Never use an agent on somebody else's session.
- Prepare one exact project folder. Record the reserved `output`. Inspect summary, expected
  duration/resolution/audio and original file hashes. Confirm ready project and all media available.
- Using upstream windows/tree and a fresh screenshot, select the project card from Home.
  There is no proven automatic project-by-path open command. Do not guess the card coordinates.
  Confirm the exact project name and timeline against the read-only summary. Do not edit anything.
- Use original `cc focus --maximize`, `cc key ctrl+e`, then
  `cc wait-for --id ExportWindow_Container --depth 3`. Screenshot and examine the dialog.
  Stop if any expected field cannot be confidently identified or a new dialog appears.
- Match H.264 / MP4 / source canvas and timeline duration. Check cloud Sync exported videos to
  space is already OFF. If ON, stop without clicking Export or changing settings. Stop on Pro,
  credits, purchases, missing media or cloud prompts. No share/upload operations authorized.
- Use the fresh screenshot folder icon to open the native picker. Reuse upstream
  `cc act set-value --type Edit --id 1152 --value "<reserved job folder>"` then
  `cc act invoke --type Button --id 1 --name "Select Folder"` ONLY after confirming that picker
  and controls in a fresh tree. Use screenshot-reviewed Name field to set `export`.
- Screenshot again: verify entire destination is `<reserved job folder>/export.mp4`, folder is
  empty, cloud sync OFF, correct codec/resolution/duration. Only then click the actual Export
  button using coordinates from this live screenshot. Never click again on timeout/ambiguity.
- Poll original windows and screenshots at sensible intervals plus output size. Stable file
  alone is insufficient. Wait for the actual saved/completion message. Never use share controls.
  Unexpected dialogs stop the batch. Operator can stop observing without cancelling the export.
- Visually confirm completion, then `verify --completion-seen` using CapCut's bundled ffmpeg.
  Verification must pass before any next job. Read failure details; no blind retry or automatic
  recovery. Only Close on the reviewed completion screen, never Share. Navigate to Home only
  through a live screenshot-reviewed control, without save/edit dialogs, then repeat preparation.

External visual agent/operator is essential for selection, every screenshot-only field, cloud
state, completion, dialog handling and safe return to Home. This toolkit does not supply that
agent. Sequential progression can be supervised with these tools; overnight autonomy has not
been demonstrated and is not enabled. One export at a time across all sessions/batch folders.
