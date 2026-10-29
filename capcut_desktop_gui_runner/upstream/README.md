# CapCut Desktop Editing

An agent skill that edits video in the **real CapCut desktop app on Windows** — driving the
application the way a person does, instead of generating video from code.

The agent looks at CapCut, operates its real controls, verifies what actually changed, and keeps a
written record of the exact route that worked. It was built one capability at a time: for each one
the agent worked out the native CapCut procedure, ran it on real footage, verified the result, and
wrote the procedure back into the skill. Nothing advanced until the previous capability was
demonstrated and approved.

**Status: rungs 0–17 approved.** Everything in the table below is a procedure that has been
executed on real footage and verified, not a guess.

![The agent editing an 8-minute talking-head take in CapCut, from import to export](docs/demo.gif)

*Rung 16, the end-to-end YouTube edit: an 8:04 raw take cut down, captioned, graded and exported
without a human touching the mouse. These are real screenshots captured during that run — faces in
the preview and the clip thumbnails are blurred for privacy.*

Modelled on [astra-premiere-editing](https://github.com/per-simmons/astra-premiere-editing)
(Premiere Pro on macOS), rebuilt from scratch for CapCut, Windows, Claude Code and Codex.

---

## Why this is harder than it sounds

Premiere publishes a rich macOS accessibility tree, so an agent can ask for a control by name.
CapCut 9.x is **Qt 6 (Qt Quick/QML + Widgets) with CEF web panels**, and on 9.4.0.4015 the home
window exposes *only its root element* to Windows UI Automation — no child controls are reachable
through any walker, hit-testing or MSAA.

So the skill uses a layered control stack and assumes an area is screenshot-driven until
`references/accessibility-controls.md` records otherwise:

| Layer | Used for | Command |
|---|---|---|
| UI Automation tree | Named buttons, tabs, menus, dialogs, fields, toggles and their state — wherever CapCut exposes them | `cc.py tree` / `find` / `act` |
| Keyboard shortcuts & menus | Split, undo, play, import, export — stable across layouts | `cc.py key` |
| Grid screenshots | Timeline clips, waveforms, playhead, preview canvas, thumbnails, icon-only buttons | `cc.py screenshot --grid`, `click`, `drag` |
| Project JSON (**read-only**) | Proving what an edit changed: segments, timings, texts, keyframes, effects | `draft_inspect.py summary` / `diff` |

Tree indices and rectangles are transient, so the tree is re-read after every action batch rather
than cached. Pixel coordinates are never stored in the references — only names, AutomationIds,
control types, menu routes, shortcuts and visual landmarks.

## Safety rules the agent follows

These are baked into `SKILL.md`, not optional:

- **Never writes CapCut project files.** `draft_content.json` and friends are read-only, used
  purely for verification. Every edit goes through CapCut's own UI.
- **Works on a duplicate.** Projects are duplicated through CapCut itself before editing, so your
  original is untouched unless you explicitly ask for it.
- **Stops before anything that costs money or can't be undone** — purchases, upgrades, upsell
  dialogs, account or settings changes, cloud upload, publishing, deleting media, and any AI
  feature that spends credits.
- **Labels its evidence honestly.** Every claim is `observed`, `executed`, `agent-verified` or
  `user-approved`, and a label is never upgraded without earning it.
- **Warns you before it takes the keyboard and mouse,** because input goes to the foreground
  window.

## What it can do

Each row is an approved procedure with the exact controls, shortcuts, wait conditions, parameters
and failure modes written down.

| # | Capability | Procedure |
|---|---|---|
| 0 | Environment + accessibility/control map | [`accessibility-controls.md`](references/accessibility-controls.md), [`keyboard-shortcuts.md`](references/keyboard-shortcuts.md), [`pro-features.md`](references/pro-features.md) |
| 1 | Duplicate a project, open the copy, split at an exact time, undo, save | [`01-single-split.md`](references/capabilities/01-single-split.md) |
| 2 | Timeline basics: select, delete/ripple, trim, move, add media, lock/mute tracks | [`02-timeline-basics.md`](references/capabilities/02-timeline-basics.md) |
| 3 | Transcript editing: remove pauses, silences and filler words | [`03-transcript-pauses.md`](references/capabilities/03-transcript-pauses.md) |
| 4 | Bad-take removal via transcript | [`04-bad-takes.md`](references/capabilities/04-bad-takes.md) |
| 5 | Waveform / manual cleanup pass | [`05-waveform-cleanup.md`](references/capabilities/05-waveform-cleanup.md) |
| 6 | Jump cuts with scale/position punch-in | [`06-jump-cuts.md`](references/capabilities/06-jump-cuts.md) |
| 7 | Keyframed, eased push-ins | [`07-push-ins.md`](references/capabilities/07-push-ins.md) |
| 8 | Auto captions + styling (incl. speaker-ID captions) | [`08-auto-captions.md`](references/capabilities/08-auto-captions.md) |
| 9 | Animated text: word-by-word, titles, text templates | [`09-text-animations.md`](references/capabilities/09-text-animations.md) |
| 10 | B-roll / overlay track (picture-in-picture) | [`10-b-roll.md`](references/capabilities/10-b-roll.md) |
| 11 | Audio Pro: vocal isolation, enhance voice, noise reduction, music + ducking | [`11-audio-pro.md`](references/capabilities/11-audio-pro.md) |
| 12 | Vertical: 9:16 canvas, auto reframe, beat-synced cuts | [`12-vertical.md`](references/capabilities/12-vertical.md) |
| 13 | Visual Pro AI: remove background, stabilization, camera tracking | [`13-visual-ai.md`](references/capabilities/13-visual-ai.md) |
| 14 | Promo polish: transitions, filters/adjust/colour, logo overlay, templates | [`14-promo-polish.md`](references/capabilities/14-promo-polish.md) |
| 15 | Export up to 4K — fps, bitrate, codec — and verify the output file | [`15-export.md`](references/capabilities/15-export.md) |
| 16 | End-to-end talking-head YouTube edit | [`16-e2e-youtube.md`](references/capabilities/16-e2e-youtube.md) |
| 17 | End-to-end vertical short | [`17-e2e-short.md`](references/capabilities/17-e2e-short.md) |

Live status for every rung is in [`references/capability-ladder.md`](references/capability-ladder.md).

## Requirements

- **Windows 10 or 11**
- **CapCut desktop** — mapped against **9.4.0.4015**. CapCut auto-updates and moves things around;
  the skill checks the running version on startup and tells you to re-verify if it drifted.
- **[uv](https://docs.astral.sh/uv/)** for the bundled Python 3.12 venv
- **Claude Code or Codex.** Claude Code on Windows has no desktop computer-use tool, so everything
  goes through this skill's scripts. On Codex, desktop input may need approval to run outside the
  sandbox.
- A CapCut **Pro** subscription only for the rungs marked Pro (11, 13, parts of 14).

## Install

```powershell
# 1. Clone to the canonical location (Codex user scope)
git clone https://github.com/yousefomar724/capcut-desktop-editing.git "$env:USERPROFILE\.agents\skills\capcut-desktop-editing"

# 2. Let Claude Code see the same folder through a junction, so write-backs land in one place
New-Item -ItemType Junction `
  -Path   "$env:USERPROFILE\.claude\skills\capcut-desktop-editing" `
  -Target "$env:USERPROFILE\.agents\skills\capcut-desktop-editing"

# 3. Create the private venv (uiautomation, comtypes, mss, pillow)
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.agents\skills\capcut-desktop-editing\scripts\setup.ps1"
```

Prefer to keep it under `~/.claude/skills` instead? Clone there and point the junction the other
way. Just don't install two copies — the skill writes procedures back into itself, and two copies
drift apart.

Verify the install with CapCut open:

```powershell
$S = "$env:USERPROFILE\.agents\skills\capcut-desktop-editing"
& "$S\scripts\.venv\Scripts\python.exe" "$S\scripts\cc.py" version
& "$S\scripts\.venv\Scripts\python.exe" "$S\scripts\cc.py" windows
```

## Using it

Open CapCut, then ask your agent in plain language:

- *"Edit the talk footage in CapCut: remove the pauses and bad takes, add jump cuts and captions, then export 1080p."*
- *"Cut a 45-second vertical short out of this project with a hook title."*
- *"Add my logo top-right for the first 30 seconds and a cross fade on the 00:15 cut."*
- *"Continue the CapCut capability ladder."* — to teach it something new.

The agent reads its platform file, reads the ladder, checks the CapCut version, tells you before it
takes over the keyboard and mouse, works in small batches, and verifies each step against a
screenshot and a read-only project diff.

### The scripts, directly

`cc.py` drives CapCut; `draft_inspect.py` verifies. Both print what they did and fail loudly if
Windows blocked `SendInput`.

```
cc.py version | windows | launch | focus --maximize
cc.py tree --filter interactive        # named controls; --depth, --root, --json
cc.py find --contains Export           # --name/--regex/--type/--id
cc.py act invoke --name "Export"       # invoke|toggle|select|expand|collapse|set-value|click|double|right|hover
cc.py screenshot --grid --scale 0.6    # grid labels are SCREEN coordinates
cc.py click X Y | drag | scroll | key ctrl+b | type "…" | paste "…"
cc.py wait-for --contains "Export" --timeout 30 [--gone]
cc.py evidence <tag> --project "<name>"

draft_inspect.py list
draft_inspect.py summary "<project>" [--json out.json]
draft_inspect.py diff before.json after.json
draft_inspect.py words "<project>" --around 295 --window 8   # caption word timings
draft_inspect.py gaps  "<project>" --min 0.6 --keep 0.125    # silences + proposed cuts
draft_inspect.py keyframes "<project>"                       # keyframes with curve/Bezier data

tighten_gaps.py --project "<project>" --dry-run              # plan silence tightening
```

## Repo layout

```
SKILL.md                      the skill itself: rules, the capability loop, control stack, cheat sheet
agents/openai.yaml            Codex interface + policy metadata
references/
  capability-ladder.md        the gate: status of every rung
  house-style.md              approved editing defaults
  capabilities/NN-*.md        one file per demonstrated capability
  accessibility-controls.md   the control map, with tree coverage per area
  control-strategy.md         tree/screenshot technique, DPI, Qt quirks, timeline positioning
  keyboard-shortcuts.md       CapCut shortcuts
  pro-features.md             Pro/AI routes, tier badges, credit cost, verification status
  project-safety.md           duplicating, backups, recovering from a bad edit
  capability-template.md      the shape of a written-back procedure
  platform-claude-code.md     how to run this from Claude Code
  platform-codex.md           how to run this from Codex
scripts/
  cc.py                       CapCut driver: tree, find, act, screenshot, input, wait-for, evidence
  draft_inspect.py            read-only project inspector: summary, diff, words, gaps, keyframes
  tighten_gaps.py             native silence tightening (exact splits, verified per cut)
  tooltip_sheet.py            hover-tooltip contact sheets for icon-only controls
  setup.ps1                   creates scripts/.venv via uv
docs/demo.gif                 the README demo, built from rung 16 evidence frames
```

`evidence/` (screenshots, trees, draft summaries from each run) is gitignored — it's local proof,
not something to ship.

## Making it yours

Two things in here are personal and you should expect to change them:

1. **`references/house-style.md`** holds one editor's approved defaults — for example Arabic-only
   auto captions with the "Classic: black box" template in the lower third. Tell your agent your
   own preferences and have it log them there.
2. **Absolute paths inside the capability records** (footage folders, a CapCut install on `D:`)
   are historical notes from the machine this was built on, not instructions. Your agent should use
   your paths. The skill folder itself is always resolved from where the skill was loaded.

To add a capability, use the same loop that built the existing ones: add a row to the ladder,
describe the edit you want, let the agent reproduce it in CapCut and verify it, approve it, and the
agent writes the exact working procedure back into `references/capabilities/`. Procedures are
written so a fresh agent with no memory of the session can repeat them.

Contributions are welcome — especially control-map updates for newer CapCut builds, or procedures
for rungs that don't exist yet. Say which CapCut version you verified against.

## Known limits

- Windows only. CapCut **web and mobile** are out of scope, and so is code-rendered video
  (Remotion, ffmpeg pipelines, HyperFrames).
- Mapped against CapCut **9.4.0.4015**. Later builds move controls; re-verify before trusting the
  control map.
- Input goes to the foreground window, so the machine isn't usable while the agent edits. Remote
  sessions and locked screens won't work.
- Multi-monitor and non-100% DPI setups are handled but only verified at 125% DPI on a single
  display.

## Credits

The capability-ladder approach, and the idea of writing verified procedures back into the skill,
come from [per-simmons/astra-premiere-editing](https://github.com/per-simmons/astra-premiere-editing).

## License

[MIT](LICENSE).
