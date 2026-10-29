# CapCut Desktop Keyboard Shortcuts (Windows)

Shortcuts are the most stable way to operate CapCut: they don't care about layout, DPI or tree
coverage. They do care about **focus**. Most editing shortcuts act on the timeline only when the
timeline (not a text field or the inspector) has focus. Click an empty timeline area first when in
doubt. CapCut's own UI isn't in the UIA tree, so you can't query focus.

## Source

- **Transcribed from CapCut's own list:** Menu ▸ Help ▸ **Shortcuts** (CapCut 9.4.0.4015,
  2026-09-14). Evidence: `evidence/2026-09-14/cap0/shortcuts/`.
- **Status labels:**
  - `listed`: shown in CapCut's dialog, not yet exercised
  - `agent-verified`: exercised and confirmed (screenshot/draft diff)
- **Keymap preset:** "Shortcut 1" (dropdown at the dialog's top right).
- **The dialog is a named UIA window** (`Window "Shortcuts"`, id `HelpDialog`). It has tabs
  **Timeline / Player / Basic / Other** and buttons **Reset / Save / Cancel**. **Close it with
  Cancel (or ✕), never Save or Reset.** Those change the user's keymap.
- **Custom mappings** are stored in `%LOCALAPPDATA%\CapCut\User Data\Config\keymapSettings`.
  Re-check the dialog if a shortcut misbehaves.

## Timeline tab

| Action | Shortcut | Status | Notes |
|---|---|---|---|
| Split | Ctrl+B | **agent-verified 2026-09-14** | With the clip selected, it splits exactly at the playhead (draft: segment ends at 10.000 s, new one starts at 10.000 s) |
| Split all | Ctrl+Shift+B | **agent-verified 2026-09-14** | With nothing selected, it splits every track that **crosses** the playhead. Tracks in a gap at that time are untouched (rung 12: only the main track split at 35.533 s; captions, title and PiP were unaffected). Per-clip audio materials (loudness/denoise/enhance) are duplicated onto the new piece, pointing at the same processed source range. |
| Select mode | A | listed | selection tool |
| Split mode | B | listed | blade tool: clicking a clip splits it |
| Select leftward | [ | **tool mode (by analogy with `]`, verified 2026-09-14 via the tool ▾ menu)** | Listed in the toolbar tool ▾ menu as "Select leftward [". It switches the click tool; clicks then select everything leftward on all tracks. Return with **A**. |
| Select rightward | ] | **agent-verified 2026-09-14: a tool mode, not an action** | `]` switches the timeline click tool to **Select rightward** (toolbar tool icon becomes a double arrow). Nothing is selected until you click. Every later click then selects everything from the click point rightward **on all tracks**. The mode **persists** and silently turns ordinary clicks into range selections (rung 12). Switch back with **A** (Select) or the tool ▾ menu ≈(111,596) ▸ Select. `[` is the leftward twin. |
| Main track magnet | P | **agent-verified 2026-09-14** | toggles the first cyan toggle in the right-hand timeline group: cyan = on, grey = off, no toast. When on, deleting on the main track ripples and dropped clips snap flush |
| Auto snapping | N | listed | |
| Linkage switch | ~ | listed | |
| Preview axis switch | S | listed | |
| Zoom in | Ctrl++ | **agent-verified 2026-09-14** | send as `cc.py key ctrl+=` (the =/+ key). ×6 took ≈1.05 → ≈67.4 px/s (about 64×), centred on the playhead |
| Zoom out | Ctrl+- | listed | |
| Zoom in/out | Ctrl+Scroll | listed | `cc.py scroll x y ±n --mod ctrl` |
| Scroll up/down | Scroll | listed | |
| Scroll left/right | Alt+Scroll | listed | |
| Activate/Deactivate clip | V | listed | |
| Extract/Restore audio | Ctrl+Shift+S | listed | |
| Add marker | M | listed | |
| Add marker with new color | Alt+M | listed | |
| Go to next marker | Shift+M | listed | |
| Go to previous marker | Alt+Shift+M | listed | |
| Previous frame | ← | listed | |
| Next frame | → | **agent-verified 2026-09-14** | one press moved 00:00:09:29 → 00:00:10:00 (timeline focused) |
| Shuttle stop | K | listed | |
| Shuttle right | L | listed | (Shuttle left presumably J; see rest of list) |
| Delete left | Q | listed | trims the selected clip's part left of the playhead |
| Delete right | W | **agent-verified 2026-09-14** | with the segment selected and the playhead at 15.000 s inside it, the segment now ends at 15.000 s (start and source start unchanged) |
| Show/Hide keyframe panel | Alt+K | **agent-verified 2026-09-14** | with a keyframed clip selected, it opens an inline graph panel above that clip on the timeline ("Transform ▴ / Scale ▴", curve-preset icons, ‹◆›, a value axis). The track shifts down about 60 px while it's open, so re-measure clip y before clicking. Draft unchanged. Also in the keyframe right-click menu as "Show variable speed animation" |
| Add keyframe on keyframe panel | Shift+Click | listed | |
| Add keyframe | Shift+Alt+K | listed | |
| Ease in / Ease out / Easing / Linear / Adjust properties | (unassigned) | listed | no default key |
| Step forward many frames | Shift+← | listed | **dialog labels look swapped** (forward shown with ←). Verify by timecode |
| Step back many frames | Shift+→ | listed | see above |
| Zoom to fit timeline | Shift+Z | **agent-verified 2026-09-14** | Fits the whole timeline in the track area (8:43 clip → x 230–1527). Also resets a scrolled view. Click empty timeline space first |
| Freeze / Reverse / Mirror / Rotate / Crop / Trim clip | (unassigned) | listed | use the timeline toolbar icons |
| Generate captions / Don't isolate voice / Keep vocal / Remove vocal | (unassigned) | listed | |
| Sync video and audio / Transcript / Open file location / Link to media | (unassigned) | listed | |
| Separate / Split scenes / Replace clip / Image to video | (unassigned) | listed | |
| Locate to first frame | Home | **agent-verified 2026-09-14** | timecode read 00:00:00:00, with the timeline focused (click empty timeline space first) |
| Locate to last frame | End | listed | |
| Last cut point | ↑ | listed | jump the playhead to the previous edit point |
| Next cut point | ↓ | **agent-verified 2026-09-14** | from 00:00:00:00, jumped exactly to the next segment boundary (00:00:54:23). Useful for spot-checking cuts. **Also stops at caption/text segment starts and ends** (rung 8: Home + ↓ → 00:00:00:18, the first caption's start), so with captions present expect many more stops |
| In point | I | listed | |
| Out point | O | listed | |
| Select by clip | Shift+X | listed | |
| Deselect | Alt+X | listed | |
| Group | Ctrl+G | listed | |
| Ungroup | Ctrl+Shift+G | listed | |
| Show speed panel | Ctrl+R | listed | |
| Curve speed | Shift+B | listed | |
| Create compound clip (subproject) | Alt+G | listed | |
| Undo compound clip (subproject) | Alt+Shift+G | listed | |
| Volume +0.1dB | Ctrl+. | listed | |
| Volume -0.1dB | Ctrl+, | listed | |
| In | Shift+Enter | listed | (label as shown; purpose to verify) |
| Shuttle left | J | listed | |
| Record screen | Ctrl+Alt+P | listed | |
| Export selected clips / Apply as a LIVE photo / Create multi-camera clip / Save preset | (unassigned) | listed | |
| Pre-process compound clip (subproject) / Clear beats / Voiceover | (unassigned) | listed | |

This completes the Timeline tab (7 scroll pages).

## Player tab

| Action | Shortcut | Status |
|---|---|---|
| Play/Pause | Space | listed |
| Enter/Exit full screen | Ctrl+Shift+F | listed |
| Cancel player alignment | Long press Ctrl | listed |
| Zoom in player | Alt+Shift++ | listed |
| Zoom out player | Alt+Shift+- | listed |
| Zoom to fit player | Alt+Shift+Z | listed |
| Show/hide rulers | Ctrl+Alt+R | listed |
| Show/hide guides | Ctrl+; | listed |

## Basic tab

| Action | Shortcut | Status | Notes |
|---|---|---|---|
| Copy | Ctrl+C | listed | |
| Cut | Ctrl+X | listed | |
| Paste | Ctrl+V | listed | |
| Copy attributes | Ctrl+Shift+C | listed | copies effects/adjustments between clips |
| Paste attributes | Ctrl+Shift+V | listed | |
| Delete | Backspace | **agent-verified 2026-09-14** | deletes the selected timeline segment; with the main track magnet on it ripples. ⚠ On the home screen Backspace deletes a selected project card — check the tree root is `MainWindow` first |
| Undo | Ctrl+Z | **agent-verified 2026-09-14** | reverted a split completely (draft diff: No differences) |
| Redo (labelled "Reset") | Ctrl+Shift+Z | **agent-verified 2026-09-14** | CapCut's label is "Reset", but it redoes: re-applied an undone split identically. **Ctrl+Y is NOT redo** (2026-09-15, rung 13): it did nothing and left the redo arrow lit, so always use Ctrl+Shift+Z |
| Import media | Ctrl+I | **agent-verified 2026-09-14** | in the editor it opens the native Windows file dialog ("From device") directly. Detect it with `cc.py wait-for --type Edit --id 1148 --depth 30` (about 2 s), then `act set-value --id 1148` + `act invoke --id 1 --name Open` |
| Export still frames | (unassigned) | listed | |
| Export | Ctrl+E | listed | opens the export dialog |
| New project | Ctrl+N | listed | creates a project, a side effect |
| Switch material panel | Tab | listed | |
| Back to edit | Ctrl+Alt+Q | listed | |
| Quit | Ctrl+Q | listed | **closes CapCut**. Never send it by accident |
| Full screen | Ctrl+F | listed | |
| Exit full screen | Esc | listed | |

## Other tab

| Action | Shortcut | Status |
|---|---|---|
| Resize the text box from the center | Alt+Drag | listed |

## Shortcuts to avoid sending casually
- **Ctrl+Q** (quit CapCut)
- **Ctrl+N** (new project)
- **Ctrl+Shift+B** (split *all* tracks)
- **P** (toggles main-track magnet, which silently changes ripple behaviour for later edits)
- **V** (deactivates a clip)

Single-letter shortcuts fire whenever the timeline has focus. **Never `cc.py type` text unless a
text field is confirmed focused.** Otherwise the letters become edit commands.

## How to verify a shortcut (during any rung)

1. Screenshot before, with CapCut focused and the correct panel focused.
2. Send `cc.py key <combo>` (e.g. `cc.py key ctrl+b`, `cc.py key shift+z`).
3. Confirm the effect with a screenshot and, for edits, `draft_inspect.py diff`.
4. Change the row to `agent-verified` with the date.
