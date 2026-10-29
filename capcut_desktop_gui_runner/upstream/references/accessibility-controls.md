# CapCut Accessibility and Control Map (Windows)

- **CapCut version mapped:** 9.4.0.4015 (Capability 0 in progress)
- **OS / scale:** Windows 10 Pro, English UI. Display at 125% (DPI 120). CapCut maximized, window
  rect 0,0 → 1920,1030 physical px.
- **UI framework:** Qt 6.2.2 (window class `Qt622QWindowIcon`; Qt Quick/QML + Qt Widgets) with CEF
  web panels (from the DLLs in the install folder)
- **Mapped by / date:** Claude Code, 2026-09-14 (home screen only so far)

This is an audit of what the Windows UI Automation (UIA) tree exposes. It isn't an exhaustive
manual. Every row carries an evidence label (`observed` / `executed` / `agent-verified` /
`user-approved`). Don't record pixel coordinates. Record names, control types, AutomationIds,
routes and visual landmarks. Re-verify after CapCut updates.

## Contents

1. **Headline finding.** CapCut is invisible to UIA/MSAA, so work screenshot-first.
2. **Coverage summary.** Per-area tree coverage.
3. **Method notes.** Probes, DPI, sandbox, foreground stealing.
4. **Areas**
   - Home / project list
   - Editor top bar · Asset toolbar · Media panel (import popup, file dialog)
   - Player (tree-exposed geometry)
   - Inspector (Details) · Timeline toolbar (tooltips) · Timeline tracks
   - Inspector: clip selected (Video → Basic)
   - Inspector: other clip tabs (Audio, Speed, Animation, Adjust, AI stylize)
   - Asset panels (Audio, Text, Stickers, Effects, Transitions, Captions, Filters, Adjustment,
     Templates, AI avatar)
   - Menu (File, Edit, More, Help, Account ⚠)
   - Inspector: Video and Audio sub-tabs (Remove BG, Mask, Retouch, Voice changer)
   - Context menus (clip, empty timeline; tooltip windows)
   - Menu ▸ Layout
   - Settings dialog
   - Transcript editor (deferred)
   - Export dialog (sync-to-space ⚠)

Search this file for a control name before taking a screenshot. If a control isn't here, map it
and add it.

## Headline finding (observed, 2026-09-14)

**The CapCut home window exposes only its root element to UI Automation.** With CapCut verified in
the foreground:

| Probe | Result |
|---|---|
| Root element | `Window "CapCut"`, AutomationId `HomeWindow`, ClassName `HomePageX_QMLTYPE_186`, FrameworkId `Qt`, Value pattern = "CapCut" |
| RawViewWalker / ControlViewWalker from root | 1 element (root only) |
| `FindAll(TreeScope_Descendants, TrueCondition)` | 0 |
| `ElementFromPoint` on a 60 px grid over the window (CapCut-owned elements only) | 1 distinct element: the root |
| MSAA `AccessibleObjectFromWindow(OBJID_CLIENT).accChildCount` | 0 |
| Focused element | the root window |

The Qt UIA bridge is loaded and answers, but CapCut's QML item tree isn't published through it:
the items have no accessible roles, or are marked ignored. Until a later probe finds otherwise, **the
home screen is screenshot-driven**: landmarks + grid coordinates + keyboard.

**Relaunched with `QT_ACCESSIBILITY=1`** (graceful close, env var for that launch only, user
approved 2026-09-14): **no change**. The home window was still root only on every probe (walkers
1, FindAll 0, hit-test 1, MSAA 0). This environment variable doesn't unlock CapCut's tree.

Still to probe:
- the **editor** window (a different QML root, may differ)
- popups, menus and dialogs (separate top-level windows)
- CEF web panels

The probe script is kept at `evidence/2026-09-14/cap0/uia_probe.py` (gitignored).

## Coverage summary

| Area | How to reach it | Tree coverage | Named controls worth knowing | Needs screenshots for |
|---|---|---|---|---|
| Home / project list | App launch | **none** (observed) | root `Window` id `HomeWindow` only | everything |
| Editor top bar (menu, project name, Export, account/Pro) | Open a project | ? | | |
| Asset toolbar (Media, Audio, Text, Stickers, Effects, Transitions, Captions, Filters, Adjustment, Templates, AI…) | Top-left of editor | ? | | |
| Media panel (import, local/library items) | Media tab | ? | | |
| Player (play/pause, timecode, ratio, fullscreen, quality) | Centre | ? | | |
| Inspector (right panel: Video/Audio/Text/Speed/Animation/Adjust tabs, AI tools) | Select a clip | ? | | |
| Timeline toolbar (select/split/delete/freeze/reverse/mirror/crop, magnet, linkage, preview axis, zoom) | Above the tracks | ? | | |
| Timeline tracks (clips, waveforms, playhead, ruler) | Bottom | ? | | |
| Transcript / text-based editing panel | ? | ? | | |
| Context menus (right-click clip/track) | Right-click | ? | | |
| Export dialog | Export button / Ctrl+E | ? | | |
| Settings / Shortcut list | Menu | ? | | |
| Modals: upsells, login, update prompts | Spontaneous | ? | | |

Coverage levels:
- `full`: every control needed is named in the tree
- `partial`: some controls are named, others need screenshots
- `none`: the area is custom-drawn and needs screenshots

## Method notes

- **Tree size:** home = 1 node.
- **Qt lazy activation:** a retry after 1.2 s and again after 3 s changed nothing. It's not a
  timing issue on the home screen.
- **Icon-only buttons:** can't tell from the tree; nothing is exposed. Use hover tooltips plus
  screenshots.
- **Popups/menus as separate windows:** not yet checked.
- **CEF:** not yet checked.
- **DPI: agent-verified 2026-09-14 at 125%.** Grid-label screen coordinates hit their targets:
  the Create project banner, Import, From device, the file dialog's Open (via UIA), and a
  media-card → timeline drag that the draft diff confirmed. The window rect from DWM matches the
  screenshot layout. Home is 1920×1030 maximized; the editor window is 1920×1080.
- **Agent sandbox:** Claude Code (desktop app, Windows) ran UIA queries, `SetForegroundWindow` and
  screen capture without any escalation.
- **Editor MSAA:** `AccessibleObjectFromWindow` on the editor showed 2 children, but a full walk
  (47 objects) contained **only generic Windows frame parts** (system menu bar, title bar with
  IME/Minimize/Maximize/Context help/Close, application menu bar, vertical/horizontal scroll bars,
  grip), duplicated for two nested windows. **No CapCut content is exposed through MSAA either.**
  Script: `evidence/2026-09-14/cap0/msaa_probe.py`.
- **Conclusion for 9.4.0.4015:** CapCut's own UI (home and editor) is invisible to every Windows
  accessibility API. Operate it by **grid screenshots + visual landmarks + keyboard shortcuts**.
  Use the tree only for native Windows dialogs CapCut opens (e.g. the file picker) and for window
  management.
- **Foreground stealing:** the Claude desktop app re-raised itself during a probe, and a
  point-sweep sampled the Claude window instead. Always verify the foreground and the element's
  `ProcessId`. `cc.py` screenshots now refocus CapCut and report `foreground_ok`.

## Areas

For each area add a table:

| Control | ControlType | Name / AutomationId | Patterns / state | Context landmark | Evidence |
|---|---|---|---|---|---|

### Home / project list

**Tree:** root only (see Headline finding). **Visual landmarks** (observed from a screenshot at
125%, maximized; positions are descriptive, not coordinates):

| Control | Landmark | Evidence |
|---|---|---|
| Account card | Top of left sidebar: avatar, account name, **Pro** badge with "View details", renewal date, "Create with Teams" button | observed |
| Sidebar nav | Left sidebar below the account card: Home, Templates. "Create with AI" group: Video Studio, Design Studio. "More tools" (expandable): Create with AI, Marketing tools. "Management": Library. Invite friends | observed |
| **Create project** | Large full-width cyan banner button at the top of the main area, "+" icon | observed |
| AI tool cards | Row under Create project: AI video, AI image, Extend video, AI edit, Enhance quality, AI remove | observed |
| AI-powered creative suite | Carousel: Video Studio, Design Studio, AI ad maker, Long video to shorts, with a ">" arrow at its right | observed |
| Projects section | "Projects" heading with search icon, grid/list toggle, **Trash**, **Project sync** buttons on the right; project thumbnail cards below (scroll down for more) | observed |
| Title bar | Top-right icon row before the minimize/maximize/close controls (purpose to confirm by hover tooltips) | observed |
| Project card | In the Projects row: thumbnail, then the **name** and "size \| duration" below it (e.g. `0914` / `18.8M \| 00:24`). The newest project comes first. **The page must be scrolled down** (wheel over the main area) to see names | observed |
| Card "…" button | Appears in the thumbnail's **bottom-right corner on hover** | observed |
| Project grid wrapping | With 10 projects (2026-09-14) the Projects grid shows **8 cards per row** and wraps to a second row. The newest project is always the first card; your own projects move right and down as agent practice projects are added. **Always read card names before clicking a card:** a stale card position can open, or worse delete, the user's own project | observed |
| Card right-click menu | Right-click the thumbnail. A menu opens **inside the home window** (no new UIA window) with **Upload**, **Rename**, **Duplicate**, **Delete** (Backspace). ⚠ Delete is the row directly below Duplicate (about 40 px); Upload is a cloud side effect | observed |

> **Editor window (observed 2026-09-14, blank project):**
> - root `Window "CapCut"`, AutomationId `MainWindow`, ClassName `MainWindow_QMLTYPE_498`
> - UIA walkers 1, FindAll 0, hit-test root only
> - MSAA reports 2 child objects (see Method notes)
>
> Opening a blank project: home → click the **Create project** banner. The project is auto-named
> with the date (`MMDD`, e.g. `0914`) and saved in the default draft root. The editor window
> replaces the home window (a new hwnd).

### Editor top bar
Visual landmarks (observed, 125%, blank project), left to right:
- CapCut logo
- **Menu** dropdown
- project name centred (`0914`)
- layout-switcher icon with dropdown
- **Pro** badge
- **Share** button
- cyan **Export** button
- minimize / restore / close

### Asset toolbar
A tab row across the top-left: **Media, Audio, Text, Stickers, Effects, Transitions, Captions,
F(ilters)…**, with a ">" arrow that scrolls to more tabs (Adjustment, Templates, AI… to confirm).
The active tab is cyan. (observed)

### Media panel
Left sub-navigation under Media:
- **Import** (expanded)
- **Media**
- **Subprojects**
- **Yours** ▾
- **Generate** ▾ (AI badge)
- **Spaces** ▾
- **Library** ▾
- **Dreamina**

Main area:
- A large **Import** drop zone ("+ Import"; "Drag and drop videos, photos, and audio files
  here").
- Under "No media? Create with these tools": **Generate**, **AI avatars**, **Record**.

(observed)

**Import popup** (executed 2026-09-14):
- Clicking the **+ Import** drop zone opens a small dark popup under the cursor with **From
  device** (monitor icon) and **From library** (folder icon).
- The popup is a separate top-level CapCut window: `cls=MenuWindow`, a full-screen transparent
  overlay rect, title "CapCut". Its tree is root only.
- **A CapCut popup or menu is open when `cc.py windows` lists a `MenuWindow`.** Press Esc or
  click outside it to dismiss.

**From device → native Windows file dialog** (executed 2026-09-14). Tree coverage is **full**: it's
a standard Win32 `#32770` dialog titled "Select a media resource", owned by CapCut.

| Control | ControlType | Name / AutomationId | Patterns | Evidence |
|---|---|---|---|---|
| File name box | Edit | "File name:" / `1148` | Value | executed |
| Open | Button | "Open" / `1` | Invoke | executed |
| Cancel | Button | "Cancel" / `2` | Invoke | observed |
| Search box | Edit | "Search Box" / `SearchEditBox` | Value | observed |

**Route:**

```
cc.py act set-value --type Edit --id 1148 --value "E:\videos\clip.mp4"
cc.py act invoke --type Button --id 1 --name Open
```

The dialog also appears inside the main window's UIA subtree, so older `cc.py` builds listed every
match twice.

**After import** (observed 2026-09-14):
- The Media panel switches to a grid with an **Import** button, a **Record** button,
  sort/filter icons and an "All" label.
- The imported clip is a thumbnail-strip card labelled with its filename, and a duration badge
  sits on the card.
- The player title changes to **Previewing — video**. It shows the clip, and the timecode reads
  `00:00:00:00 / <clip duration>` (e.g. `00:00:23:13`).
- The top bar shows **Auto saved: HH:MM:SS** next to Menu. Use it as the autosave indicator before
  running `draft_inspect.py`.
- Importing alone does not put anything on the timeline.

### Player
**The tree exposes the player's geometry** (observed 2026-09-14, clip loaded). Under the
`MainWindow` root:
- `Window` id `editPanelLoader.editWin` (cls `EditPanel_QMLTYPE_618`): the player panel
- `Window` id `MainWindow.surface_main` (cls `QQuickWindow`): the video render surface

They have no children, but their rects are exact. Use
`cc.py find --id MainWindow.surface_main` to get a precise crop region for preview checks
(`cc.py screenshot --region l,t,r,b`). Not present on an empty project before import.

Panel titled **Player-Timeline 01**:
- a timecode readout `00:00:00:00 / 00:00:00:00` at the bottom left
- play button in the centre
- on the bottom right: quality, fit/zoom, **Ratio**, and fullscreen icons

(observed; greyed out while empty)

### Inspector
Right panel. With nothing selected it shows **Details**:
- Name
- Path
- Imported media ("Stay in original location")
- Arrange layers ("Turned on")
- Proxy ("Turned off")
- Timeline name ("Timeline 01")
- Aspect ratio ("Original")
- Resolution ("Adapted")
- Frame rate ("30.00fps")
- **Modify** button

A yellow onboarding tooltip ("Layers can be reordered in…") may cover its bottom. (observed)

### Timeline toolbar
The row above the tracks.

Left group:
- add-track/"+" (with a blue dot)
- **selection tool** with a ▾ dropdown
- undo
- redo
- split
- split-left / split-right (trim to playhead)
- delete
- a shield/marker icon (to confirm by tooltip)

Right group:
- microphone (record voiceover)
- four toggles (main-track magnet, auto snapping, linkage, preview axis; confirm by tooltip),
  one with a ▾
- a split/compare icon ▾
- a preview/monitor icon
- zoom **−** / slider / **+**

(observed)

**With a clip selected** (observed 2026-09-14): extra clip tools appear after the shield icon,
ending in a "<" that collapses the run.

**Layout offset when maximized.** The tooltip x positions below were measured with the editor at
1920×1080 (not maximized), where the toolbar row sat at y≈623. After `cc.py focus --maximize`
the window is 1920×1030 and the **toolbar row moves up to y≈598**. The x positions stayed the
same: Transcript ≈592, AI extend ≈637, AI edit ≈680, Split scenes ≈725, Remove background ≈770,
Auto adjust ≈815, Enhance visuals ≈860, Extract audio ≈902. Always read y from a fresh
screenshot.

**Tooltips seen by hovering** (observed 2026-09-14, `evidence/2026-09-14/cap0/toolbar-tooltips.png`).
Tooltips appear just **below** the icon.

Order left → right after crop:

| Icon (landmark) | Tooltip | Badge |
|---|---|---|
| film-frame with bars | **Freeze** | — |
| document with sound waves | **Transcript** | Pro diamond |
| clip with arrow | **AI extend** ("Drag to extend your clip from…") | — |
| magic wand | **AI edit** ("Edit images and videos just by…") | — |
| split-screen square | **Split scenes** | "Free" |
| person with sparkle | **Remove background** ("Automatically detect huma…") | Pro diamond |
| wand with sparkles | **Auto adjust** | Pro diamond |
| "HD" | **Enhance visuals** | — |
| page with arrow | **Extract audio** | — |

**No tooltip on hover** (observed 2026-09-14): the basic group shows only a hover highlight and no
tooltip within 1.8 s, even with a capture 120 px above and below. The basic group is "+",
selection ▾, undo, redo, `][` split, split-left `][`-left, split-right, trash delete, shield,
crop. The right-hand group (mic, the four cyan toggles, the compare ▾ and preview icons, zoom −/+)
behaves the same.

Identify these by:
- **Icon shape**, a strong convention: `][` = split, trash = delete, curved arrows = undo/redo,
  magnifier ± = zoom.
- **The shortcut list** (Menu → see the Menu section).
- **Behaviour tests in rungs 1–2**, confirmed by draft diff.

Hovering the compare/preview icon around x≈1745 opened a small phone-style preview popover.

**Right-hand toggle group, re-read at full resolution** (observed 2026-09-14, maximized, 125%).
Left to right:
- mic (≈1363)
- **three cyan toggle icons** at ≈1422, ≈1477 and ≈1525. The third has a ▾ (≈1550).
- a split/compare icon with ▾ (≈1590)
- a monitor icon (≈1655)
- zoom − (≈1710), slider, + (≈1885)

All three toggles are drawn in cyan. The middle one (≈1477) also has a **filled cyan
background**, while the outer two are cyan outlines on dark. The fill likely marks a different
on/off state, but that isn't confirmed yet.

The shortcut list names four timeline switches:
- Main track magnet **P**
- Auto snapping **N**
- Linkage switch **~**
- Preview axis switch **S**

Which icon is which gets established by behaviour in rung 2, then recorded here.

**Identified 2026-09-14 (agent-verified):**
- **The first toggle (≈1422) is the Main track magnet.**
  - Pressing **P** turned it from cyan to grey, and pressing P again turned it back to cyan.
  - **Cyan = on, grey = off.**
  - With it on, deleting a main-track segment ripples (rung 2, Op 2).
- The middle toggle (≈1477, filled cyan) and the third (≈1525 ▾) are still unidentified. The
  candidates are Auto snapping **N**, Linkage **~** and Preview axis **S**.
- **No toast** appears when toggling with P. Confirm the state from the icon colour alone
  (zoom `--region 1340,560,1920,620`).

### Timeline tracks
- **Empty timeline:** a drop row reads "Drag material here and start to create". (observed)
- **Adding a clip** (executed + agent-verified 2026-09-14):
  - Route: drag the clip card from the Media panel onto the drop row (`cc.py drag` with
    `--steps 30 --hold 0.3`).
  - Result: the clip lands at 00:00 on the main video track and is auto-selected (white border).
  - Draft diff: 1 video track, 1 segment 0 → clip duration.
  - **The canvas follows the first clip:** a vertical clip set the project to 1080×1920 ("Aspect
    ratio: Original").
- **Track header** (left of the track): video/track icon, **lock**, **eye** (hide), **speaker**
  (mute), "…" menu, then a **Cover** button. (observed)
- **Clip body:** thumbnail strip labelled `<filename>  <duration>`. It isn't in the UIA tree, so
  locate it by screenshot. (observed)
- **Ruler and playhead:** the ruler runs above the tracks with 00:00, 00:10, 00:20… labels. The
  playhead is a vertical line with a handle on the ruler. (observed)

### Inspector: clip selected (Video)
- **Tab row:** **Video, Audio, Speed, Animation, Adjust, A…** with a ">" for more.
- **Video sub-tabs:** **Basic, Remove BG, Mask, Retouch**.
- **Basic → Transform** (collapsible, with reset and keyframe-diamond icons):
  - **Scale** slider + stepper (100%)
  - **Uniform scale** toggle (on)
  - **Position** X / Y steppers
  - **Rotate** (0.00°) with a dial
  - a row of 6 alignment buttons
- **Keyframe controls** (agent-verified 2026-09-14, rung 7): every Transform row ends in `‹ ◇ ›`,
  meaning previous keyframe / add or remove keyframe / next keyframe.
  - The ◇ is **hollow** off a keyframe and **filled cyan** on one.
  - Once a property has a keyframe, typing a new value (Enter) **auto-adds a keyframe** at the
    playhead.
  - Between keyframes the value box shows the **interpolated** value, rounded to 1%.
  - A selected clip shows white diamond markers on its strip. Right-click one for Ease in / Ease
    out / Easing / Linear (see Context menus).
- **Blend:** checkbox (checked by default), with reset and keyframe icons.
- **Stabilize:** checkbox with a **purple Pro diamond badge**.

(observed)

### Inspector: caption selected (agent-verified 2026-09-14, rung 8)
- **Timeline:** after Auto captions, a **TT** caption row (lock, eye) sits above the video track
  (y≈763 at the default layout). Zoom in (Ctrl+= ×4 ≈ 46 px/s) to see clickable orange pills
  with text and an A☰ icon. **↓ stops at caption boundaries.**
- **Tabs:** **Captions · Text · Animation · Tracking · Text to speech ›**. Text ▸ **Basic ·
  Templates · Bubble · Effects**.
- **Text ▸ Basic, from the top:**
  - **Apply to all main captions** ✓ (default). Applies style only, never text.
  - Text box (edit a caption's words; focus stays there until you click elsewhere)
  - Font "System" ▾
  - Font size slider + value box (default 7; type + Enter)
  - Pattern B / U / I
  - Case TT / tt / Tt
  - **Preset style** "Aa" tile grid (⊘ none, white-black outline, black-white outline, white,
    white on dark, yellow, red, …)
  - Transform (Scale, keyframe)
  - Checkbox sections Background / Glow / Shadow / Curve
  - **Save as preset** stays pinned at the bottom.
- **Bilingual captions** (rung 8 round 2): two caption rows, speech ("main captions") at y≈731
  and translation ("sub captions") at y≈763. A translation caption's checkbox reads **Apply to all
  sub captions**. Style, template and Transform edits apply per track only.
- **Text ▸ Templates** (inspector): Apply to all ✓, "Search for text templates", a chip row
  **★ · Trending · Classic (≈1653,271) · NEW · H…**, then a 4-wide tile grid from ≈(1495,355),
  ≈97 px pitch. Footer: Save as preset · **Reset**.
  - **Clicking a tile applies it** (saved in 2–3 s).
  - With a template applied, the Text sub-tabs become **Basic · Templates · Effects** (Bubble is
    hidden).
  - It may show "Loading…" until the left panel's Captions ▸ Templates has been opened once.
- **Captions ▸ Templates** (left asset panel): categories Favorites / Trending / Classic / NEW /
  Hits / Word / Glow / Lyrics.
  - Clicking a tile **only previews** it ("Previewing — Templates" in the player) and deselects the
    caption.
  - Its **+** and **Generate captions** (Pro) have no tooltips.
- **Text ▸ Basic ▸ Transform** for a caption: Scale ≈(1790,271), Uniform scale, **Position X
  ≈(1650,367) / Y ≈(1770,367)** (`clip.transform.x = X / 1920`, `clip.transform.y = Y / 1080`;
  transform 1.0 = **half** the canvas, so one typed unit ≈ ½ canvas px, verified in rung 10), Plane rotation,
  alignment row. Reach it with `scroll 1480 440 -4`, `-4`, `+2`.
- **Scroll the inspector** with the pointer over its label column (x≈1480). All of these are
  screenshot-only (not in the UIA tree).

### Inspector: other clip tabs (observed 2026-09-14, video clip selected)
The tab row is **Video, Audio, Speed, Animation, Adjust**, then **AI stylize**, reached with ">".
The row scrolls, so after ">" the positions shift. Take a new screenshot before clicking.
Tabs switch on a single click.

- **Audio.** Sub-tabs: **Basic | Voice changer**.
  - Basic section (checkbox, reset, keyframe):
    - **Volume** slider + dB stepper (0.0dB)
    - **Fade in** / **Fade out** sliders + seconds steppers
  - Below it:
    - **Normalize loudness** (Pro), described as "Normalize the loudness of the selected clip or
      clips to a target level"
    - **Enhance voice** (Pro, ▾)
    - **Video translator** (Pro, ▾)
- **Speed.** Sub-tabs: **Standard | Curve | Velocity effects** (Pro).
  - Standard has:
    - **Speed** slider with detents + stepper (1.00x)
    - **Duration** (source → result, stepper)
    - **Change audio pitch** toggle
    - **Smooth slow-mo** (Pro; disabled with "Only slow-speed videos are supported.")
  - A **Reset** button at the bottom.
- **Animation.** Shows "Loading…" for about 1 s on first open. Wait before the screenshot.
- **Adjust.** Sub-tabs: **Basic | HSL | Curves | Color wheel | Mask**.
  - Basic has:
    - **Auto adjust** (Pro)
    - **Color match** (Pro)
    - **Color correction** (Pro)
    - **LUT** (checked; Name dropdown "None", Intensity 100)
    - "Protect skin tone…" below
  - Bottom buttons: **Save as preset** (cyan), **Apply to all**.

### Asset panels (observed 2026-09-14)
The tab row is **Media, Audio, Text, Stickers, Effects, Transitions, Captions, Filters,
Adjustment, Templates, AI avatar**:
- The row scrolls. The ">" arrow at its right end reveals the later tabs, and "<" at the left end
  scrolls back.
- **Clicking where "Filters" was can hit the arrow instead.** Take a new screenshot after
  scrolling.
- Library panels share one layout: a left category list, a search box ("People are searching
  …"), a filter icon, and thumbnail cards with a download arrow. **A purple diamond on a card
  means Pro.**

| Tab | Left list | Main area |
|---|---|---|
| Audio | Import, Yours ▾, **Music ▾** (Summer, Phonk, Vlog, Tense, …), Sounds effects ▾ | track rows: title, artist · duration, ☆ favourite, ⬇ download |
| Text | **Add text**, Yours ▾, Text effects ▾, Text template ▾, **Auto captions**, **Local captions** | "Default text" card |
| Stickers | Yours ▾, Stickers ▾ (Trending, Whimsical, Classic, NEW, Hits, Shapes…) | cards, many Pro |
| Effects | Favorites, **Video effects ▾** (Trending, Classic, … Intro & Outro, Party), Body effects ▾ | named cards (e.g. "Club Mood"), many Pro |
| Transitions | Favorites, Transitions ▾ (Trending, Classic, Overlay, Light, Camera, 3D…) | named cards (e.g. "Slight Jitter"), some Pro |
| Captions | **Auto captions**, Templates ▾, **Auto lyrics**, **Add captions** | Auto captions form: **Spoken language** dropdown (Auto detect), **Bilingual captions** (Pro) dropdown (None), **Identify filler words** (Pro) toggle (on by default), **Delete current captions** checkbox, cyan **Generate** button with a **Pro** tag |
| AI avatar | Avatar library, Photo to avatar, Fashion model…, Video translator, AI dialogue sce… (all Pro) | 2-step wizard: 1 Choose avatar → 2 Add speech; avatar cards; **Next** |

**More asset panels** (observed 2026-09-14, after scrolling the tab row with ">"):

| Tab | Left list | Main area |
|---|---|---|
| Filters | Favorites, **Filters ▾** (Featured, NEW, Hits, CCD, Life, Photo Booth, Pet, Landscape, Movies, Mono…) | named cards (e.g. "Bold Saturation"), some Pro |
| Adjustment | **Add adjustment**, Yours ▾, **LUT** | "Custom adjustment" card (adds an adjustment layer) |
| Templates | Yours ▾, **Templates ▾** (For you, then categories in the system/region language, here Arabic) | search "Search for templates". Loads slowly ("Loading……"), so wait before screenshotting |

**Inspector → Animation** (after about 1–3 s of "Loading…"):
- sub-tabs **In | Out | Combo**
- a search box
- category chips: ★, Trending, Basic, Light, Glitch, Mask…
- cards: **None** (selected, cyan border), Zoom 2, Zoom In, Rock…, Fade In, Zoom Out, Swing Left,
  Swing Right… Many are Pro (purple diamond), and each has ☆ favourite and ⬇ download.

**Inspector → AI stylize** (reached via ">"):
- **AI effects** checkbox + Prompt box with **Showcase ›**, **Random**, **Generate**
  (disabled until a prompt is entered)
- **Style** checkbox + chips: Trending, AI painting, AI Photo, Particle, Expressions, Hair Salon,
  Motion, Split, Portrait, Face swap, Scene swap, Video effects. Pro cards below.

Credits are likely; confirm with the user before generating.

### Menu (observed 2026-09-14)
- **Menu ▾** (top-left, next to the logo) opens: **File ›, Edit ›, Layout ›, More ›, Help ›,
  Account ›, Settings, Back to home page, Quit**.
- Hovering a › entry opens its submenu to the right. No click is needed.

| Submenu | Items |
|---|---|
| File | New project, New timeline, Import, Export |
| Edit | Undo, Recovery (disabled), Copy, Cut, Paste (disabled when clipboard empty), Delete |
| Layout | (not yet opened) |
| More | Terms of Service, Privacy Policy, Third-party copyright, Environment Testing, **Version:9.4.0** |
| Help | Feedback, **Shortcuts**, Walkthrough, About |
| Account | ⚠ **Delete account**: never hover-and-click here. It is the only item and sits directly under the pointer path to Settings. |

- **Back to home page** is the clean way to leave the editor, and it forces the draft to save.
  Executed 2026-09-14: Menu (≈140,22) → Back to home page. About 5 s later the tree root was
  `HomeWindow` again, and the project list showed the edited project first (most recent). The
  home page is scrollable; the Projects row sits below the fold at 1920×1030, so scroll it into
  view before clicking cards.
- The top bar also shows **"Auto saved: HH:MM:SS"** with a cyan check next to Menu.
- **Esc does not reliably close the Menu.** After `key esc esc`, the UIA tree still listed a
  `MenuWindow`. Verify with `cc.py tree --depth 1` and a screenshot. Close it by clicking a neutral
  area (e.g. the empty timeline background) if it is still open.

### Inspector: Video and Audio sub-tabs (observed 2026-09-14)
- **Video ▸ Remove BG:**
  - **Auto removal** (Pro)
  - **Custom removal** ▾
  - **Chroma key** ▾ (with keyframe icons)
- **Video ▸ Mask:**
  - **Mask** checkbox + **Add mask**
  - shapes: Split, Filmstrip, Circle, Rectangle, Stars, Heart, Text, **Brush** (Pro), **Pen** (Pro)
  - The shapes are greyed out until Add mask is used.
- **Video ▸ Retouch:**
  - chips: Face, Body, Hair, Face presets, Body presets
  - "Single face" dropdown
  - **Auto styles** (loads for about 1 s), **Skin** (Clear, Smooth… sliders)
  - Save as preset
- **Audio ▸ Voice changer:**
  - Apply to all
  - search
  - chips: **Voice filters, Voice characters, Speech to song**
  - filter icon
  - The list loads for about 1 s.

### Context menus (observed 2026-09-14)
Right-click opens a CapCut menu window: an extra `Qt622QWindowIcon` in `cc.py windows`, and
`cls=MenuWindow` in the tree. **Close it by left-clicking empty space**, because Esc isn't
reliable. Greyed items are disabled in the current state.

**On a video clip** (full menu, `evidence/2026-09-14/cap0/gaps/ctx-clip-full.png`):

| Item | Notes |
|---|---|
| Copy | Ctrl+C |
| Cut | Ctrl+X |
| Copy attributes | Ctrl+Shift+C |
| Paste attributes | disabled until attributes are copied |
| Delete | Backspace |
| Edit › | submenu (not yet opened) |
| Split scenes | "Free" |
| Transcript | Pro |
| Isolate voice › | "Free" |
| Extract audio | Pro, Ctrl+Shift+S |
| Sync video and audio | disabled |
| Create compound clip (subproject) | Alt+G |
| Create multi-camera clip | "Free", disabled |
| Save preset | |
| Group / Ungroup | disabled with one clip |
| Export selected clips | |
| Deactivate clip | V |
| Trim clip | disabled |
| Replace clip | |
| Link to media | disabled |
| Open file location | |
| Edit effects / Show variable speed animation | disabled |
| Range › | |
| Render › | |

**On a keyframe marker** (small white diamond on a selected clip's thumbnail strip; executed
2026-09-14, `evidence/2026-09-14/cap7/kf-rightclick.png`):

| Item | Notes |
|---|---|
| Ease in | curve preset |
| Ease out | curve preset |
| Easing | ease in-out preset |
| Linear | ✓ by default |
| Show all presets | |
| Show variable speed animation | Alt+K |
| Copy | Ctrl+C |
| Delete | Backspace |

The first time a keyframe is added, a yellow tip says *"Right-click the keyframe to create
variable speed animations"*. Dismiss it with its **OK** button.

**On empty timeline space:**
- Close gap (disabled)
- Close all gaps (disabled)
- Select
- Paste (disabled)
- Range ›
- Render ›

**Tooltips in the tree:** while a CapCut tooltip is showing, a window with
`cls=LVToolTipWindow_QMLTYPE_*` appears in `cc.py tree`. It gives the tooltip's rect but not its
text. Use it to confirm a hover produced a tooltip, then crop that rect in a screenshot.

### Menu ▸ Layout (observed 2026-09-14)
- **Default** ✓
- Media
- Attributes
- Vertical
- **Reset current layout**

Every procedure in this skill assumes **Default**. If a screenshot shows panels in different
places, check this submenu first.

### Settings dialog (observed 2026-09-14; nothing changed)
- **How to open it:** Menu ▸ **Settings**.
- **Tree:** named window `Window "Settings"`, id `GlobalSettingsWindow`, rect about 640×823
  centred.
- **Tabs:** **Draft | Edit | Performance | General**.
- **Footer:** cyan **Save** and **Cancel**. **Close with Cancel. Never Save**, because changing
  settings is off-limits without the user.
- **Draft tab:**
  - **Save to** (draft root), **Screen recording** folder, **Download to** folder
  - **Cache:** Don't delete / Auto delete cache from N days ago
  - **Cache size** with a ⚠ trash button (clears cache; never click)
  - **Auto sync** toggle: **ON on this machine**, "upload your projects to space automatically"
  - **Synced items:** Projects ☐, **Exported videos ☑**
  - **Default space**
  - **Size limit** (500 MB)
  - **Preset save path**
- **Edit tab** (values as found):
  - **Image duration** 5.0 s
  - **Target loudness** Default (-23 LUFS)
  - **Play audio while scrubbing** off
  - **Linkage** → Settings button. Linked items: Text, Effects, Stickers, Filters, Adjust, Sound
    effects, Text to speech.
  - **Arrange layers** ☑
  - **Frame rate** 30.00 fps (default for new projects)
  - **Time code** `HH:MM:SS+frame`: the player timecode's last field is **frames**, not
    milliseconds
  - **Sound for export** ☐
  - **Dreamina sync** ☐
- **Performance tab:**
  - **Interface rendering** (GPU)
  - **Auto optimization** None
  - **Auto remux** off, with a save folder and file-size trash button
  - **Proxy** ☐, with a save folder and proxy-size trash button
  - **Sound output device**
  - **Rendering cache location**, rendering cache size with a trash button
  - **Auto clear** 10 GB
  - **Auto render** off
- **General tab:**
  - interface **language list** at the top (scrollable; hovering highlights rows, which isn't a
    selection)
  - **Notification** ☐
  - **Software update:** ● **Automatic updates** / ○ Get notified. **CapCut updates itself here**,
    so always run `cc.py version` at session start.
  - **Right-click menu:** "Add CapCut to Windows right-click menu" ☐
- **Closing:** Cancel discarded everything. The tree confirmed `GlobalSettingsWindow` was gone,
  and the draft diff showed no change.

### Transcript editor
Not opened in Capability 0. The Transcript tool (toolbar, and the clip right-click menu) is
**Pro** and may start cloud transcription that uses credits. Open it in rung 3, with the user's
confirmation.

### Export dialog
Opened via the cyan **Export** button (top-right) — shortcut **Ctrl+E**. Observed 2026-09-14 (opened and cancelled, nothing exported).

- **Tree:** named window `Window "Export-<project>"`, id `ExportWindow_Container`, cls `ExportWindow_QMLTYPE_2488`, rect ≈ 900×828 centred. Presence = dialog open; no child controls exposed.
- **Left:** cover preview with **Edit cover**.
- **Right, top:** Export timeline (Timeline 01) · **Name** field (project name) · **Export to** path field + folder icon (defaulted to the last-used folder, here `E:/videos/<name>.mp4`).
- **Video** section (checkbox, checked): **Resolution** ▾ (1080P) · **Bit rate** ▾ (Recommended) · **Codec** ▾ (H.264) · **Format** ▾ (mp4) · **Frame rate** ▾ (30fps) · Color space (Rec. 709 SDR, read-only).
- ⚠ **Sync exported videos to space** checkbox — **checked by default** (uploads to CapCut cloud). Must be unchecked before any export unless the user asks for sync.
- **Audio** section (checkbox, unchecked) · Format ▾ (MP3).
- **Footer:** "Duration: 24s | Size: about 23 MB" · cyan **Export** · **Cancel** (bottom-right, left of nothing; Export is to its left).
- The settings list scrolls (scrollbar on the right) — more options below Audio may exist; scroll inside the list before assuming.

### Settings / shortcuts
See **Settings dialog** above and `keyboard-shortcuts.md`. That file holds the full list,
transcribed from Menu ▸ Help ▸ Shortcuts.

### Modals
Seen so far (2026-09-14):
- **Onboarding tooltip.** A yellow "Layers can be reordered in…" bubble sits at the bottom of the
  Details inspector. It's harmless, but it can cover the **Modify** button.
- **CapCut popups/menus.** `MenuWindow` in the tree; close with a click on empty space.
- **Named dialogs.** `HelpDialog` (Shortcuts), `ExportWindow_Container` (Export),
  `GlobalSettingsWindow` (Settings). Their presence in `cc.py tree --depth 2` means they're open.

Not yet seen: upsell/subscription prompts, login prompts, update prompts, crash dialogs. When
one appears, screenshot it, record its landmarks and close route here, and never accept
purchases or updates.
