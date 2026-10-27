// Z Studio - "Open in CapCut": turns the Video Editor timeline into a CapCut desktop project (a "draft") and opens CapCut.
//
// How it works (the same mechanism CapCut itself uses): CapCut keeps every project as a folder of JSON files inside its drafts folder
// (%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft by default, or the folder chosen in CapCut's settings). We write a new project
// folder there - timeline (draft_content.json), media copied next to it, and the small side files CapCut expects - and then start CapCut.
// The new project shows at the top of CapCut's Projects list. CapCut has no command line / URL to open one specific draft, so Z Studio does
// not click anything for you: you open the project from CapCut's Home screen.
//
// This module is pure Node (no Electron) so it can be tested without CapCut. The field layout follows a project written by CapCut 9.4;
// other CapCut versions may read it differently - check() reports what was detected and whatever cannot be verified.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const cp = require('child_process');

const US = 1e6;
const PHOTO_MATERIAL_US = 10800000000;          // CapCut gives a still picture a 3 hour "material length"
const uid = () => crypto.randomUUID().toUpperCase();
const hex16 = () => crypto.randomBytes(16).toString('hex');
const us = s => Math.max(0, Math.round((+s || 0) * US));
const slash = p => String(p).replace(/\\/g, '/');
const r6 = v => Math.round(v * 1e6) / 1e6;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ---------------------------------------------------------------- where CapCut lives
function capcutRoot(env) {
  env = env || process.env;
  if (env.ZS_CAPCUT_ROOT) return env.ZS_CAPCUT_ROOT;           // tests / unusual installs
  return env.LOCALAPPDATA ? path.join(env.LOCALAPPDATA, 'CapCut') : '';
}
function highestVersionDir(appsDir) {
  try {
    const v = fs.readdirSync(appsDir, { withFileTypes: true }).filter(d => d.isDirectory() && /^\d+(\.\d+)+$/.test(d.name)).map(d => d.name);
    v.sort((a, b) => { const x = a.split('.').map(Number), y = b.split('.').map(Number); for (let i = 0; i < Math.max(x.length, y.length); i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) - (y[i] || 0); } return 0; });
    return v.length ? v[v.length - 1] : '';
  } catch (_) { return ''; }
}
function detect(env) {
  const root = capcutRoot(env), out = { installed: false, root, exe: '', version: '', draftsRoot: '', draftsFromSettings: false };
  if (!root || !fs.existsSync(root)) return out;
  const apps = path.join(root, 'Apps'), exe = path.join(apps, 'CapCut.exe');
  out.exe = fs.existsSync(exe) ? exe : '';
  out.version = highestVersionDir(apps);
  let drafts = path.join(root, 'User Data', 'Projects', 'com.lveditor.draft');
  try { // the user can move the drafts folder in CapCut: the choice is stored in its globalSetting file
    const s = fs.readFileSync(path.join(root, 'User Data', 'Config', 'globalSetting'), 'utf8');
    const m = s.match(/^currentCustomDraftPath=(.+)$/m);
    if (m) { const p = m[1].trim().replace(/\\\\/g, '\\'); if (p && fs.existsSync(p)) { drafts = p; out.draftsFromSettings = true; } }
  } catch (_) {}
  out.draftsRoot = drafts;
  out.installed = !!out.exe || fs.existsSync(drafts);
  return out;
}
// What we can and cannot promise for this CapCut. The layout written here is the one of CapCut 9.4.
function compat(d) {
  const notes = [];
  if (!d.installed) return { level: 'none', notes: ['CapCut is not installed (or its folder was not found).'] };
  if (!d.exe) notes.push('CapCut.exe was not found, so Z Studio cannot start CapCut for you. The project is still written to the drafts folder.');
  if (!d.version) notes.push('The CapCut version could not be read. The project layout was written for CapCut 9.4 and has not been verified against this version.');
  else if (parseInt(d.version, 10) !== 9) notes.push(`CapCut ${d.version} was detected. The project layout was written for CapCut 9.4 and has not been verified against ${d.version}. If CapCut does not list the project or reports a problem, use "Media folder + SRT" instead.`);
  return { level: notes.length ? 'warn' : 'ok', notes };
}
function isRunning() {
  return new Promise(res => {
    if (process.platform !== 'win32') return res(false);
    let out = ''; const c = cp.spawn('tasklist', ['/FI', 'IMAGENAME eq CapCut.exe', '/NH'], { windowsHide: true });
    c.stdout.on('data', x => { out += x; }); c.on('error', () => res(false)); c.on('close', () => res(/CapCut\.exe/i.test(out)));
  });
}
function launch(exe) {
  if (!exe || !fs.existsSync(exe)) return false;
  try { const c = cp.spawn(exe, [], { detached: true, stdio: 'ignore', windowsHide: false }); c.on('error', () => {}); c.unref(); return true; } catch (_) { return false; }
}
const safeName = (s, fb) => String(s || fb || 'Z Studio').replace(/[<>:"/\\|?*\x00-\x1f]+/g, ' ').replace(/\s+/g, ' ').replace(/[. ]+$/, '').trim().slice(0, 60) || fb || 'Z Studio';
function uniqueFolder(root, base) { const clean = safeName(base, 'Z Studio Project'); let n = clean; for (let i = 2; fs.existsSync(path.join(root, n)); i++) n = `${clean} (${i})`; return n; }

// ---------------------------------------------------------------- motion: Z Studio zoom / keyframes -> CapCut keyframes
// Z Studio units: kf scale 'sc' (1 = picture fitted to the frame), px/py = shift as a fraction of frame width/height (+x right, +y DOWN),
// rot degrees, op 0..1. CapCut units: scale (1 = fitted), x/y = half-frame units (+x right, +y UP), rotation degrees, alpha 0..1.
const EASE = { in: p => p * p, out: p => p * (2 - p), inout: p => p * p * (3 - 2 * p) };
function sampleTrack(points, dur) {          // [[t,v,ease],...] -> dense linear points CapCut can interpolate
  const pts = points.map(p => [clamp(+p[0], 0, dur), +p[1], p[2]]).sort((a, b) => a[0] - b[0]);
  const out = [];
  for (let i = 0; i < pts.length; i++) {
    out.push([pts[i][0], pts[i][1]]);
    const n = pts[i + 1];
    if (n && EASE[pts[i][2]] && n[0] - pts[i][0] > 0.05) for (let k = 1; k < 8; k++) { const p = k / 8; out.push([pts[i][0] + (n[0] - pts[i][0]) * p, pts[i][1] + (n[1] - pts[i][1]) * EASE[pts[i][2]](p)]); }
  }
  return out;
}
function motionOf(c, dur, zoomMin) {
  const tr = c.transform || {};
  const base = { scale: tr.scale != null ? +tr.scale : 1, x: (tr.x || 0) * 2, y: -(tr.y || 0) * 2, rotation: tr.rot || 0, alpha: tr.opacity != null ? +tr.opacity : 1, flipH: !!tr.flipH, flipV: !!tr.flipV, kf: {} };
  const kfs = c.kfs;
  if (kfs && Object.keys(kfs).some(p => (kfs[p] || []).length)) {
    const map = { sc: ['scale', v => v], px: ['x', v => v * 2], py: ['y', v => -v * 2], rot: ['rotation', v => v], op: ['alpha', v => v] };
    for (const p of Object.keys(map)) {
      const list = (kfs[p] || []).filter(k => k && isFinite(+k.t) && isFinite(+k.v)).map(k => [+k.t, map[p][1](+k.v), k.ease]);
      if (!list.length) continue;
      const dense = sampleTrack(list, dur).map(([t, v]) => [t, r6(v)]);
      base[map[p][0]] = dense[0][1];
      if (dense.length > 1 && dense.some(d => Math.abs(d[1] - dense[0][1]) > 1e-6)) base.kf[map[p][0]] = dense;
    }
    return base;
  }
  if (c.kind === 'video') return base;
  const amt = c.zoomAmt != null ? clamp(+c.zoomAmt, 0.01, 0.4) : 0.08;
  const z = (c.zoom === 'auto' || !c.zoom) ? (dur >= zoomMin ? 'in' : 'none') : c.zoom;
  if ((z === 'in' || z === 'out') && dur >= (c.zoom === 'auto' ? zoomMin : 0.3)) {
    const a = z === 'in' ? 1 : 1 + amt, b = z === 'in' ? 1 + amt : 1;
    base.scale = base.scale * a; base.kf.scale = [[0, r6(a * (tr.scale != null ? +tr.scale : 1))], [dur, r6(b * (tr.scale != null ? +tr.scale : 1))]];
  } else if (z === 'pan') {                 // fixed 1.12 zoom, window travels left -> right: the picture moves from +0.06 to -0.06 of the frame width
    const s = 1.12 * (tr.scale != null ? +tr.scale : 1); base.scale = s; base.x = 0.12; base.kf.x = [[0, 0.12], [dur, -0.12]];
  }
  return base;
}

// ---------------------------------------------------------------- the plan: what goes where (order, start, duration) - the single source of truth
// payload: { name, aspect, W, H, fps, zoomMinSec, images:[{image,kind,trimStart,start,end,zoom,zoomAmt,kfs,transform,volume,muted,hasAudio,transOut,filter,effects,adjust,crop}],
//            captions:[{text,start,end,...style}], titles:[...], voice, sfx[], music[], stickers[] }
// media = { [file]: { w, h, duration, hasAudio } }
function makePlan(payload, media) {
  const notes = [], warn = m => { if (!notes.includes(m)) notes.push(m); };
  const W = payload.W || 1920, H = payload.H || 1080, zoomMin = payload.zoomMinSec || 5;
  const plan = { name: payload.name || 'Z Studio Project', W, H, fps: +payload.fps || 30, images: [], voice: [], music: [], sfx: [], captions: [], titles: [], notes, gaps: 0, separateLayers: payload.separateLayers === true };
  let prev = 0;
  const imgs = (payload.images || []).filter(c => c && c.image).slice().sort((a, b) => a.start - b.start);
  imgs.forEach((c, i) => {
    const start = Math.max(c.start, prev); if (start >= c.end) { warn(`Clip ${i + 1} overlaps the previous one completely and was skipped.`); return; }
    const dur = +(c.end - start).toFixed(3), info = media[c.image] || {};
    if (start - prev > 0.05) plan.gaps++;
    const m = motionOf(c, dur, zoomMin);
    plan.images.push({ n: plan.images.length + 1, file: c.image, kind: c.kind === 'video' ? 'video' : 'photo', start, dur, trimStart: c.trimStart || 0, w: info.w || 0, h: info.h || 0, mediaDur: info.duration || 0, hasAudio: c.kind === 'video' && c.hasAudio !== false && info.hasAudio !== false,
      volume: c.kind === 'video' ? (c.muted ? 0 : (c.volume != null ? +c.volume : 1)) : 0, m, transOut: c.transOut || null, filter: c.filter, effects: c.effects, adjust: c.adjust, crop: c.crop });
    prev = c.end;
  });
  const aud = (a, label) => { const info = media[a.file] || {}; let dur = +a.dur || 0; if (info.duration) dur = Math.min(dur || info.duration, Math.max(0.04, info.duration - (a.trimStart || 0))); if (dur <= 0) { warn(`${label}: could not read the length of ${path.basename(a.file)}.`); return null; } return { file: a.file, start: a.start || 0, dur, trimStart: a.trimStart || 0, volume: a.volume != null ? +a.volume : 1, fadeIn: a.fadeIn || 0, fadeOut: a.fadeOut || 0, mediaDur: info.duration || 0 }; };
  if (payload.voice && payload.voice.file) { const a = aud(payload.voice, 'Voiceover'); if (a) plan.voice.push(a); }
  (payload.music || []).forEach(x => { const a = aud(x, 'Music'); if (a) plan.music.push(a); });
  (payload.sfx || []).forEach(x => { const a = aud(x, 'Sound effect'); if (a) plan.sfx.push(a); });
  const txt = (list, into) => (list || []).forEach(t => { if (t && String(t.text || '').trim() && t.end > t.start) into.push(t); });
  txt(payload.captions, plan.captions); txt(payload.titles, plan.titles);
  plan.captions.sort((a, b) => a.start - b.start); plan.titles.sort((a, b) => a.start - b.start);
  plan.total = Math.max(0, ...plan.images.map(c => c.start + c.dur), ...plan.voice.concat(plan.music, plan.sfx).map(a => a.start + a.dur), ...plan.captions.concat(plan.titles).map(t => t.end));
  // what CapCut cannot receive from here (CapCut has its own versions: re-apply them there)
  const n = (f) => plan.images.filter(f).length;
  const tN = n(c => c.transOut), fN = n(c => c.filter && c.filter.id), eN = n(c => (c.effects || []).some(e => e && !e.off)), aN = n(c => c.adjust && Object.values(c.adjust).some(v => v)), cN = n(c => c.crop && (c.crop.l || c.crop.t || c.crop.r || c.crop.b));
  if (tN) warn(`${tN} transition${tN > 1 ? 's' : ''} not sent: CapCut transitions need CapCut's own effect files, which Z Studio cannot write. Add them in CapCut.`);
  if (fN) warn(`${fN} colour filter${fN > 1 ? 's' : ''} not sent (CapCut has its own filters).`);
  if (eN) warn(`Effects on ${eN} clip${eN > 1 ? 's' : ''} not sent (blur, RGB split, shake, vignette, bars, scanlines, flicker are Z Studio effects).`);
  if (aN) warn(`Colour Adjust on ${aN} clip${aN > 1 ? 's' : ''} not sent.`);
  if (cN) warn(`Crop on ${cN} clip${cN > 1 ? 's' : ''} not sent.`);
  if ((payload.stickers || []).length) warn(`${payload.stickers.length} sticker${payload.stickers.length > 1 ? 's' : ''} not sent.`);
  if (plan.captions.some(t => t.hl && t.hl !== 'none') || plan.captions.some(t => t.anim && t.anim !== 'none')) warn('Caption word highlight / animation is not sent: captions arrive as plain editable CapCut text with the colours, outline, box and position of the chosen style.');
  if (plan.gaps) warn(`${plan.gaps} gap${plan.gaps > 1 ? 's' : ''} between pictures (Z Studio shows black there). The gap is kept in CapCut.`);
  return plan;
}

// ---------------------------------------------------------------- CapCut project JSON (field layout of CapCut 9.4)
const speedM = () => ({ id: uid(), type: 'speed', mode: 0, speed: 1, curve_speed: null });
const placeholderM = () => ({ id: uid(), type: 'placeholder_info', meta_type: 'none', res_path: '', res_text: '', error_path: '', error_text: '' });
const canvasM = () => ({ id: uid(), type: 'canvas_color', color: '', blur: 0, image: '', album_image: '', image_id: '', image_name: '', source_platform: 0, team_id: '' });
const animM = () => ({ id: uid(), type: 'sticker_animation', animations: [], multi_language_current: 'none' });
const soundMapM = () => ({ id: uid(), type: 'none', audio_channel_mapping: 0, is_config_open: false });
const colorM = () => ({ id: uid(), is_color_clip: false, is_gradient: false, solid_color: '', gradient_colors: [], gradient_percents: [], gradient_angle: 90, width: 0, height: 0 });
const vocalM = () => ({ id: uid(), type: 'vocal_separation', choice: 0, removed_sounds: [], time_range: null, production_path: '', final_algorithm: '', enter_from: '' });
const beatM = () => ({ id: uid(), type: 'beats', mode: 404, gear: 404, gear_count: 0, enable_ai_beats: false, user_beats: [], user_delete_ai_beats: null, ai_beats: { melody_url: '', melody_path: '', beats_url: '', beats_path: '', melody_percents: [0.0], beat_speed_infos: [] } });
const MAT_KEY = { speed: 'speeds', placeholder_info: 'placeholder_infos', canvas_color: 'canvases', sticker_animation: 'material_animations', none: 'sound_channel_mappings', vocal_separation: 'vocal_separations', beats: 'beats' };

function videoMaterial(file, kind, info) {
  const photo = kind === 'photo';
  return { id: uid(), unique_id: hex16(), type: photo ? 'photo' : 'video', duration: photo ? PHOTO_MATERIAL_US : us(info.mediaDur), path: slash(file), media_path: '', local_id: '', has_audio: !photo && info.hasAudio !== false,
    reverse_path: '', intensifies_path: '', reverse_intensifies_path: '', intensifies_audio_path: '', cartoon_path: '', width: info.w || 0, height: info.h || 0, category_id: '', category_name: 'local', material_id: '', material_name: path.basename(file), material_url: '',
    crop: { upper_left_x: 0, upper_left_y: 0, upper_right_x: 1, upper_right_y: 0, lower_left_x: 0, lower_left_y: 1, lower_right_x: 1, lower_right_y: 1 }, crop_ratio: 'free', audio_fade: null, crop_scale: 1, extra_type_option: 0,
    stable: { stable_level: 0, matrix_path: '', time_range: { start: 0, duration: 0 } },
    matting: { flag: 0, path: '', interactiveTime: [], has_use_quick_brush: false, strokes: [], has_use_quick_eraser: false, expansion: 0, feather: 0, reverse: false, custom_matting_id: '', enable_matting_stroke: false, is_clould: false, mask_video_path: '', cloud_product_fps: 0 },
    source: 0, source_platform: 0, formula_id: '', check_flag: 62978047,
    video_algorithm: { algorithms: [], time_range: null, path: '', gameplay_configs: [], ai_in_painting_config: [], complement_frame_config: null, motion_blur_config: null, deflicker: null, noise_reduction: null, quality_enhance: null, super_resolution: null, ai_background_configs: [], smart_complement_frame: null, aigc_generate: null, aigc_generate_list: [], mouth_shape_driver: null, ai_expression_driven: null, ai_motion_driven: null, image_interpretation: null, story_video_modify_video_config: { task_id: '', is_overwrite_last_video: false, tracker_task_id: '', generate_id: '', generate_card_id: '' }, skip_algorithm_index: [] },
    is_unified_beauty_mode: false, is_set_beauty_mode: false, object_locked: null, smart_motion: null, multi_camera_info: null, freeze: null, picture_from: 'none', picture_set_category_id: '', picture_set_category_name: '', team_id: '', local_material_id: '', origin_material_id: '',
    request_id: '', has_sound_separated: false, is_text_edit_overdub: false, is_ai_generate_content: false, aigc_type: 'none', is_copyright: false, aigc_history_id: '', aigc_item_id: '', local_material_from: '', smart_match_info: null, beauty_face_preset_infos: [], beauty_body_preset_id: '',
    beauty_face_auto_preset: { preset_id: '', name: '', rate_map: '', scene: '' }, beauty_face_auto_preset_infos: [], beauty_body_auto_preset: null, live_photo_timestamp: -1, live_photo_cover_path: '', content_feature_info: null, corner_pin: null, surface_trackings: [],
    video_mask_stroke: { resource_id: '', path: '', type: '', color: '', size: 0, alpha: 0, distance: 0, texture: 0, horizontal_shift: 0, vertical_shift: 0 }, video_mask_shadow: { resource_id: '', path: '', color: '', alpha: 0, blur: 0, distance: 0, angle: 0 }, pre_applied_vip_materials: [], workflow_node_id: '' };
}
function audioMaterial(file, info) {
  return { id: uid(), unique_id: hex16(), type: 'extract_music', name: path.basename(file), duration: us(info.mediaDur), path: slash(file), category_name: 'local', wave_points: [], music_id: crypto.randomUUID(), app_id: 0, text_id: '', tone_type: '', source_platform: 0, video_id: '', effect_id: '', resource_id: '', third_resource_id: '', category_id: '', intensifies_path: '',
    formula_id: '', check_flag: 1, team_id: '', local_material_id: '', tone_speaker: '', mock_tone_speaker: '', tone_effect_id: '', tone_effect_name: '', tone_platform: '', cloned_model_type: '', tone_category_id: '', tone_category_name: '', tone_second_category_id: '', tone_second_category_name: '',
    tone_emotion_name_key: '', tone_emotion_style: '', tone_emotion_role: '', tone_emotion_selection: '', tone_emotion_scale: 0, moyin_emotion: '', request_id: '', query: '', search_id: '', sound_separate_type: '', is_text_edit_overdub: false, is_ugc: false, is_ai_clone_tone: false, is_ai_clone_tone_post: false,
    source_from: '', copyright_limit_type: 'none', aigc_history_id: '', aigc_item_id: '', music_source: '', pgc_id: '', pgc_name: '', similiar_music_info: { original_song_id: '', original_song_name: '' }, ai_music_type: 0, ai_music_enter_from: '', lyric_type: 0, tts_task_id: '', tts_generate_scene: '', ai_music_generate_scene: 0,
    tts_benefit_info: { benefit_type: 'none', benefit_log_id: '', benefit_log_extra: '', benefit_amount: -1 } };
}
const hexRgb = (c, fb) => { const m = String(c || '').trim().match(/^#?([0-9a-f]{6})$/i), v = m ? m[1] : fb; return [0, 2, 4].map(i => Math.round(parseInt(v.slice(i, i + 2), 16) / 255 * 1000) / 1000); };
const rgbHex = a => '#' + a.map(c => Math.round(c * 255).toString(16).padStart(2, '0')).join('');
// Z Studio text size is pixels at 1080 high; CapCut text size is relative to the canvas WIDTH (about 7 for text 3.3 % of the width wide).
const capSize = (t, W, H) => Math.round(clamp(((t.size || 48) / 1080 * H / W) * 212, 1, 60) * 10) / 10;
function textMaterial(t, W, H, sub) {
  const fill = hexRgb(t.color, 'ffffff'), size = capSize(t, W, H), outW = t.outline ? clamp(t.outline / 100 * 2, 0.02, 0.2) : 0, stroke = hexRgb(t.outlineColor, '000000');
  const content = { text: String(t.text), styles: [{ fill: { alpha: 1, content: { render_type: 'solid', solid: { alpha: 1, color: fill } } }, font: { id: '', path: '' }, size, bold: (t.weight || 'bold') === 'bold', strokes: outW ? [{ alpha: 1, content: { render_type: 'solid', solid: { alpha: 1, color: stroke } }, width: outW }] : [], range: [0, String(t.text).length], useLetterColor: true }] };
  const align = t.align === 'left' ? 0 : t.align === 'right' ? 2 : 1, box = !!t.box && (t.boxOpacity == null || t.boxOpacity > 0);
  return { recognize_task_id: '', id: uid(), name: '', recognize_text: '', recognize_model: '', punc_model: '', type: sub ? 'subtitle' : 'text', content: JSON.stringify(content), base_content: '', words: { start_time: [], end_time: [], text: [] }, current_words: { start_time: [], end_time: [], text: [] },
    global_alpha: 1, combo_info: { text_templates: [] }, caption_template_info: { resource_id: '', third_resource_id: '', resource_name: '', category_id: '', category_name: '', effect_id: '', request_id: '', path: '', is_new: false, source_platform: 0 },
    layer_weight: 1, letter_spacing: 0, text_curve: null, text_loop_on_path: false, offset_on_path: 0, enable_path_typesetting: false, text_exceeds_path_process_type: 0, text_typesetting_paths: null, text_typesetting_paths_file: '', text_typesetting_path_index: 0,
    line_spacing: 0.02, has_shadow: !!t.shadow, shadow_color: t.shadow ? '#000000' : '', shadow_alpha: 0.9, shadow_smoothing: 0.45, shadow_distance: 5, shadow_point: { x: 0.6363961030678928, y: -0.6363961030678928 }, shadow_angle: -45, shadow_thickness_projection_enable: false, shadow_thickness_projection_angle: 0, shadow_thickness_projection_distance: 0,
    border_alpha: 1, border_color: outW ? rgbHex(stroke) : '', border_width: outW, border_mode: 0, style_name: '', text_color: rgbHex(fill), text_alpha: 1, font_name: '', font_title: 'none', font_size: size, font_path: '', font_id: '', font_resource_id: '', initial_scale: 1, font_url: '',
    typesetting: 0, alignment: align, line_feed: 1, use_effect_default_color: false, is_rich_text: false, shape_clip_x: false, shape_clip_y: false, ktv_color: '', text_to_audio_ids: [], bold_width: 0.008, italic_degree: 0, underline: false, underline_width: 0.05, underline_offset: 0.22, sub_type: 0, check_flag: 7, text_size: 30,
    font_category_name: '', font_source_platform: 0, font_third_resource_id: '', font_category_id: '', add_type: 0, operation_type: 0, recognize_type: 0, fonts: [],
    background_color: box ? rgbHex(hexRgb(t.boxColor, '000000')) : '', background_alpha: box ? clamp(t.boxOpacity != null ? +t.boxOpacity : 0.5, 0, 1) : 1, background_style: 0, background_round_radius: 0.15, background_width: 0.14, background_height: 0.14, background_vertical_offset: 0, background_horizontal_offset: 0, background_fill: box ? rgbHex(hexRgb(t.boxColor, '000000')) : '',
    single_char_bg_enable: false, single_char_bg_color: '', single_char_bg_alpha: 1, single_char_bg_round_radius: 0.3, single_char_bg_width: 0, single_char_bg_height: 0, single_char_bg_vertical_offset: 0, single_char_bg_horizontal_offset: 0, font_team_id: '', tts_auto_update: false, text_preset_resource_id: '', group_id: '', preset_id: '', preset_name: '', preset_category: '', preset_category_id: '', preset_index: 0, preset_has_set_alignment: false,
    force_apply_line_max_width: false, language: '', relevance_segment: [], original_size: [], fixed_width: -1, fixed_height: -1, autoAdaptCanvasEnabled: false, line_max_width: 0.82, oneline_cutoff: false, cutoff_postfix: '', subtitle_template_original_fontsize: 0, subtitle_keywords: null, inner_padding: -1, multi_language_current: 'none', source_from: '', is_lyric_effect: false, lyric_group_id: '',
    lyrics_template: { resource_id: '', resource_name: '', panel: '', effect_id: '', path: '', category_id: '', category_name: '', request_id: '' }, is_batch_replace: false, is_words_linear: false, ssml_content: '', subtitle_keywords_config: null, sub_template_id: -1, translate_original_text: '' };
}
const KF_TYPE = { scale: 'KFTypeScaleX', x: 'KFTypePositionX', y: 'KFTypePositionY', rotation: 'KFTypeRotation', alpha: 'KFTypeAlpha' };
function commonKeyframes(kf, durUs) {
  const out = [];
  for (const prop of Object.keys(KF_TYPE)) {
    const pts = kf && kf[prop]; if (!Array.isArray(pts) || pts.length < 2) continue;
    out.push({ id: uid(), material_id: '', property_type: KF_TYPE[prop], keyframe_list: pts.map(([t, v]) => ({ id: uid(), curveType: 'Line', time_offset: Math.min(Math.max(0, durUs - 1), us(t)), left_control: { x: 0, y: 0 }, right_control: { x: 0, y: 0 }, values: [+v || 0], string_value: '', graphID: '' })) });
  }
  return out;
}
function segment(f) {
  const visual = f.kind !== 'audio';
  return { id: uid(), source_timerange: f.source || null, target_timerange: f.target, render_timerange: { start: 0, duration: 0 }, desc: '', state: 0, speed: 1, is_loop: false, is_tone_modify: false, reverse: false, intensifies_audio: false, cartoon: false, volume: f.volume != null ? f.volume : 1, last_nonzero_volume: 1,
    clip: visual ? { scale: { x: f.scale != null ? f.scale : 1, y: f.scale != null ? f.scale : 1 }, rotation: f.rotation || 0, transform: { x: f.x || 0, y: f.y || 0 }, flip: { vertical: !!f.flipV, horizontal: !!f.flipH }, alpha: f.alpha != null ? f.alpha : 1 } : null,
    uniform_scale: visual ? { on: true, value: 1 } : null, material_id: f.materialId, extra_material_refs: f.refs, render_index: f.renderIndex || 0, keyframe_refs: [], enable_lut: f.kind === 'video', enable_adjust: f.kind === 'video', enable_hsl: false, visible: true, group_id: '', enable_color_curves: true, enable_hsl_curves: true,
    track_render_index: f.trackIndex || 0, hdr_settings: f.kind === 'video' ? { mode: 1, intensity: 1, nits: 1000 } : null, enable_color_wheels: true, track_attribute: f.main ? 1 : 0, is_placeholder: false, template_id: '', enable_smart_color_adjust: false, template_scene: 'default',
    common_keyframes: commonKeyframes(f.kf, f.target.duration), caption_info: null, responsive_layout: { enable: false, target_follow: '', size_layout: 0, horizontal_pos_layout: 0, vertical_pos_layout: 0 }, enable_color_match_adjust: false, enable_color_correct_adjust: false, enable_adjust_mask: false, raw_segment_id: '',
    lyric_keyframes: null, enable_video_mask: true, digital_human_template_group_id: '', color_correct_alg_result: '', source: 'segmentsourcenormal', enable_mask_stroke: false, enable_mask_shadow: false, enable_color_adjust_pro: false, segment_color_tag: '' };
}
const trackOf = (type, name) => ({ id: uid(), type, segments: [], flag: 0, attribute: 0, name: name || '', is_default_name: !name });
function emptyMaterials() {
  return Object.fromEntries(['flowers', 'videos', 'tail_leaders', 'audios', 'images', 'texts', 'effects', 'stickers', 'canvases', 'transitions', 'audio_effects', 'audio_fades', 'beats', 'material_animations', 'placeholders', 'placeholder_infos', 'speeds', 'common_mask', 'chromas', 'text_templates', 'realtime_denoises', 'audio_pannings', 'audio_pitch_shifts', 'video_trackings', 'hsl', 'drafts', 'color_curves', 'hsl_curves', 'primary_color_wheels', 'log_color_wheels', 'video_effects', 'ai_text_effects', 'audio_balances', 'handwrites', 'manual_deformations', 'manual_beautys', 'plugin_effects', 'sound_channel_mappings', 'green_screens', 'shapes', 'material_colors', 'digital_humans', 'digital_human_model_dressing', 'smart_crops', 'ai_translates', 'audio_track_indexes', 'loudnesses', 'vocal_beautifys', 'vocal_separations', 'smart_relights', 'time_marks', 'multi_language_refs', 'video_shadows', 'video_strokes', 'video_radius'].map(k => [k, []]));
}
const platform = () => ({ os: 'windows', os_version: '10.0.19045', app_id: 359289, app_version: '9.4.0', app_source: 'cc', device_id: '', hard_disk_id: '', mac_address: '' });
const yFor = pos => pos === 'top' ? 0.78 : pos === 'center' ? 0 : -0.78;

// plan (media paths already point at the copies inside the project folder: plan.files[original] = copy) -> draft_content.json object
function buildContent(plan, files, timelineId) {
  const M = emptyMaterials(), tracks = [], matFor = new Map();
  const refs = list => list.map(m => { M[MAT_KEY[m.type] || 'material_colors'].push(m); return m.id; });
  // Z Builder fixed arrangement: base still-image track BELOW overlay video track.
  // Every clip keeps its original target timestamp, even when its track has gaps.
  // Legacy Z Studio still uses its single mixed main track by default.
  let ti = 0;
  const visualGroups = plan.separateLayers
    ? [{ clips: plan.images.filter(c => c.kind === 'photo'), name: 'Images - Lower Layer' },
       { clips: plan.images.filter(c => c.kind === 'video'), name: 'Videos - Upper Layer' }]
    : [{ clips: plan.images, name: '' }];
  // Avoid an empty base track when a project contains only one media kind.
  for (const group of visualGroups) {
    if (!group.clips.length) continue;
    const main = trackOf('video', group.name);
    const baseTrack = ti === 0;
    for (const c of group.clips) {
      const f = files[c.file] || c.file; let mat = matFor.get(f);
      if (!mat) { mat = videoMaterial(f, c.kind, c); M.videos.push(mat); matFor.set(f, mat); }
      main.segments.push(segment({ kind: 'video', main: baseTrack, materialId: mat.id, refs: refs([speedM(), placeholderM(), canvasM(), animM(), soundMapM(), colorM(), vocalM()]), trackIndex: ti, renderIndex: ti,
        source: { start: c.kind === 'photo' ? 0 : us(c.trimStart), duration: us(c.dur) }, target: { start: us(c.start), duration: us(c.dur) }, volume: c.volume, scale: c.m.scale, x: c.m.x, y: c.m.y, rotation: c.m.rotation, alpha: c.m.alpha, flipH: c.m.flipH, flipV: c.m.flipV, kf: c.m.kf }));
    }
    tracks.push(main); ti++;
  }
  const audio = (list, name) => {
    if (!list.length) return; const t = trackOf('audio', name);
    for (const a of list) {
      const f = files[a.file] || a.file; let mat = matFor.get(f); if (!mat) { mat = audioMaterial(f, a); M.audios.push(mat); matFor.set(f, mat); }
      t.segments.push(segment({ kind: 'audio', materialId: mat.id, refs: refs([speedM(), placeholderM(), beatM(), soundMapM(), vocalM()]), trackIndex: ti, source: { start: us(a.trimStart), duration: us(a.dur) }, target: { start: us(a.start), duration: us(a.dur) }, volume: a.volume }));
    }
    tracks.push(t); ti++;
  };
  audio(plan.voice, 'Voiceover'); audio(plan.music, 'Music'); audio(plan.sfx, 'Sound effects');
  const text = (list, name, sub) => {
    if (!list.length) return; const t = trackOf('text', name);
    for (const x of list) {
      const m = textMaterial(x, plan.W, plan.H, sub); M.texts.push(m);
      t.segments.push(segment({ kind: 'text', materialId: m.id, refs: refs([animM()]), trackIndex: ti, renderIndex: 14000 + ti, target: { start: us(x.start), duration: us(x.end) - us(x.start) }, scale: 1, x: 0, y: yFor(x.pos) }));
    }
    tracks.push(t); ti++;
  };
  text(plan.captions, 'Z Studio Captions', true); text(plan.titles, 'Z Studio Titles', false);
  const total = tracks.reduce((m, t) => Math.max(m, ...t.segments.map(s => s.target_timerange.start + s.target_timerange.duration)), 0);
  return { id: timelineId, version: 360000, new_version: '185.0.0', name: '', duration: total, create_time: 0, update_time: 0, fps: plan.fps, is_drop_frame_timecode: false, color_space: 0,
    config: { video_mute: false, record_audio_last_index: 1, extract_audio_last_index: 1, original_sound_last_index: 1, subtitle_recognition_id: '', subtitle_taskinfo: [], lyrics_recognition_id: '', lyrics_taskinfo: [], subtitle_sync: true, lyrics_sync: true, voice_change_sync: false, sticker_max_index: 1, adjust_max_index: 1, material_save_mode: 0, export_range: null, maintrack_adsorb: !plan.gaps && !plan.separateLayers, combination_max_index: 1, attachment_info: [], zoom_info_params: null, system_font_list: [], multi_language_mode: 'none', multi_language_main: 'none', multi_language_current: 'none', multi_language_list: [], subtitle_keywords_config: null, use_float_render: false, hdr_vivid: false },
    canvas_config: { ratio: 'original', width: plan.W, height: plan.H, background: null }, tracks, group_container: null, materials: M, keyframes: { videos: [], audios: [], texts: [], stickers: [], filters: [], adjusts: [], handwrites: [], effects: [] }, keyframe_graph_list: [], platform: platform(), last_modified_platform: platform(),
    mutable_config: null, cover: null, retouch_cover: null, extra_info: null, relationships: [], mixed_track_mode_on: false, render_index_track_mode_on: true, free_render_index_mode_on: false, static_cover_image_path: '', source: 'default', time_marks: null, path: '', lyrics_effects: [], uneven_animation_template_info: { composition: '', content: '', order: '', sub_template_info_list: [] },
    draft_type: 'video', smart_ads_info: { page_from: '', routine: '', draft_url: '' },
    function_assistant_info: { smart_rec_applied: false, fixed_rec_applied: false, auto_adjust: false, auto_adjust_segid_list: [], color_correction: false, color_correction_segid_list: [], enhance_quality: false, smooth_slow_motion: false, deflicker_segid_list: [], video_noise_segid_list: [], enhance_quality_segid_list: [], smart_segid_list: [], retouch: false, retouch_segid_list: [], enhande_voice: false, enhance_voice_segid_list: [], audio_noise_segid_list: [], auto_caption: false, auto_caption_segid_list: [], auto_caption_template_id: '', caption_opt: false, caption_opt_segid_list: [], eye_correction: false, eye_correction_segid_list: [], normalize_loudness: false, normalize_loudness_segid_list: [], normalize_loudness_audio_denoise_segid_list: [], auto_adjust_fixed: false, auto_adjust_fixed_value: 50.0, color_correction_fixed: false, color_correction_fixed_value: 50.0, normalize_loudness_fixed: false, enhande_voice_fixed: false, retouch_fixed: false, enhance_quality_fixed: false, smooth_slow_motion_fixed: false, fps: { num: 0, den: 1 } } };
}

// ---------------------------------------------------------------- write the project folder (staged, then renamed into place so CapCut never sees a half-written project)
const wj = (file, v) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify(v), 'utf8'); };
const orderedName = (i, file, kind) => `${kind}${String(i).padStart(4, '0')} ${safeName(path.basename(file, path.extname(file)), 'media')}${path.extname(file).toLowerCase()}`;
function copyMedia(plan, mediaDir) {
  const files = {}; let ni = 0, na = 0; fs.mkdirSync(mediaDir, { recursive: true });
  const put = (file, label, n) => { if (files[file]) return; const dest = path.join(mediaDir, orderedName(n, file, label)); fs.copyFileSync(file, dest); files[file] = dest; };
  for (const c of plan.images) put(c.file, c.kind === 'video' ? 'video ' : 'image ', c.n);
  for (const a of plan.voice.concat(plan.music, plan.sfx)) put(a.file, 'audio ', ++na);
  return files;
}
function writeProject({ plan, drafts, folderName }) {
  if (!plan.images.length && !plan.voice.length) throw new Error('There is nothing to send: add pictures or a voiceover to the timeline first.');
  fs.mkdirSync(drafts, { recursive: true });
  const name = uniqueFolder(drafts, folderName || plan.name), stage = path.join(drafts, '.zs-staging-' + crypto.randomBytes(4).toString('hex')), finalDir = path.join(drafts, name);
  const timelineId = uid(), draftId = uid(), nowUs = Date.now() * 1000, nowS = Math.floor(Date.now() / 1000);
  try {
    const files = copyMedia(plan, path.join(stage, 'Z Studio Media'));
    // the draft must point at the FINAL location of the copies
    const finalFiles = Object.fromEntries(Object.entries(files).map(([o, c]) => [o, path.join(finalDir, 'Z Studio Media', path.basename(c))]));
    const content = buildContent(plan, finalFiles, timelineId);
    const tdir = path.join(stage, 'Timelines', timelineId);
    for (const d of [stage, tdir]) {
      wj(path.join(d, 'draft_content.json'), content); wj(path.join(d, 'draft_content.json.bak'), content);
      wj(path.join(d, 'common_attachment', 'attachment_id_mapping.json'), { id_mapping: { mapping: [], next_index: 1001, version: '1.0.0' } });
      wj(path.join(d, 'common_attachment', 'attachment_pc_timeline.json'), { reference_lines_config: { horizontal_lines: [], is_lock: false, is_visible: false, vertical_lines: [] }, safe_area_type: 0 });
      const rep = { caption_id_list: [], commercial_material: '', material_source: '', method: '', page_from: '', style: '', task_id: '', text_style: '', tos_id: '', video_category: '' };
      wj(path.join(d, 'attachment_pc_common.json'), { ai_packaging_infos: [], ai_packaging_report_info: rep, broll: { ai_packaging_infos: [], ai_packaging_report_info: rep }, commercial_music_category_ids: [], pc_feature_flag: 0, recognize_tasks: [], reference_lines_config: { horizontal_lines: [], is_lock: false, is_visible: false, vertical_lines: [] }, safe_area_type: 0, template_item_infos: [], unlock_template_ids: [] });
    }
    wj(path.join(tdir, 'common_attachment', 'attachment_action_scene.json'), { action_scene: { removed_segments: [], segment_infos: [] } });
    wj(path.join(tdir, 'common_attachment', 'attachment_plugin_draft.json'), { plugin_draft: { plugin_segments: [], version: '1.0.0' } });
    const project = { config: { color_space: -1, hdr_vivid: false, mixed_track_mode_on: false, render_index_track_mode_on: false, use_float_render: false }, create_time: nowUs, id: uid(), main_timeline_id: timelineId, timelines: [{ create_time: nowUs, id: timelineId, is_marked_delete: false, name: 'Timeline 01', update_time: nowUs }], update_time: nowUs, version: 0 };
    wj(path.join(stage, 'Timelines', 'project.json'), project); wj(path.join(stage, 'Timelines', 'project.json.bak'), project);
    wj(path.join(stage, 'timeline_layout.json'), { dockItems: [{ dockIndex: 0, ratio: 1, timelineIds: [timelineId], timelineNames: ['Timeline 01'] }], layoutOrientation: 1 });
    fs.writeFileSync(path.join(stage, 'draft_biz_config.json'), JSON.stringify({ timeline_settings: { [timelineId]: { linkage_enabled: false } } }, null, 4), 'utf8');
    wj(path.join(stage, 'draft_agency_config.json'), { is_auto_agency_enabled: false, is_auto_agency_popup: false, is_single_agency_mode: false, marterials: null, use_converter: false, video_resolution: 720 });
    wj(path.join(stage, 'performance_opt_info.json'), { manual_cancle_precombine_segs: null, need_auto_precombine_segs: null });
    wj(path.join(stage, 'draft_virtual_store.json'), { draft_materials: [], draft_virtual_store: [{ type: 0, value: [{ creation_time: 0, display_name: '', filter_type: 0, id: '', import_time: 0, import_time_us: 0, material_color_tag: '', sort_sub_type: 0, sort_type: 0, subdraft_filter_type: 0 }] }, { type: 1, value: [] }, { type: 2, value: [] }] });
    fs.writeFileSync(path.join(stage, 'draft_settings'), `[General]\ndraft_create_time=${nowS}\ndraft_last_edit_time=${nowS}\nreal_edit_seconds=0\nreal_edit_keys=0\n`, 'utf8');
    const meta = { cloud_draft_cover: false, cloud_draft_sync: false, cloud_package_completed_time: '', draft_cloud_capcut_purchase_info: '', draft_cloud_last_action_download: false, draft_cloud_package_type: '', draft_cloud_purchase_info: '', draft_cloud_template_id: '', draft_cloud_tutorial_info: '', draft_cloud_videocut_purchase_info: '', draft_cover: 'draft_cover.jpg', draft_deeplink_url: '',
      draft_enterprise_info: { draft_enterprise_extra: '', draft_enterprise_id: '', draft_enterprise_name: '', enterprise_material: [] }, draft_fold_path: slash(finalDir), draft_has_unfinished_aigc_video_effect: false, draft_id: draftId, draft_is_ae_produce: false, draft_is_ai_packaging_used: false, draft_is_ai_shorts: false, draft_is_ai_translate: false,
      draft_is_article_video_draft: false, draft_is_cloud_temp_draft: false, draft_is_from_deeplink: 'false', draft_is_infinite_canvas_draft: false, draft_is_invisible: false, draft_is_pippit_draft: false, draft_is_web_article_video: false,
      draft_materials: [{ type: 0, value: [] }, { type: 1, value: [] }, { type: 2, value: [] }, { type: 3, value: [] }, { type: 6, value: [] }, { type: 7, value: [] }, { type: 8, value: [] }], draft_materials_copied_info: [], draft_name: name, draft_need_rename_folder: false, draft_new_version: '', draft_removable_storage_device: '',
      draft_root_path: drafts.replace(/\//g, '\\'), draft_segment_extra_info: [], draft_timeline_materials_size_: 0, draft_type: '', draft_web_article_video_enter_from: '', pippit_avatar_url: '', pippit_extra_info: '', pippit_id: '', pippit_user_name: '', tm_draft_cloud_completed: '', tm_draft_cloud_entry_id: -1, tm_draft_cloud_modified: 0,
      tm_draft_cloud_parent_entry_id: -1, tm_draft_cloud_space_id: -1, tm_draft_cloud_user_id: -1, tm_draft_create: nowUs, tm_draft_modified: nowUs, tm_draft_removed: 0, tm_duration: content.duration };
    wj(path.join(stage, 'draft_meta_info.json'), meta);
    fs.renameSync(stage, finalDir);
    return { name, folder: finalDir, draftId, timelineId, duration: content.duration / US, tracks: content.tracks.length, segments: content.tracks.reduce((n, t) => n + t.segments.length, 0), files: finalFiles };
  } catch (err) { try { fs.rmSync(stage, { recursive: true, force: true }); } catch (_) {} throw err; }
}

// ---------------------------------------------------------------- read the written project back and compare it with the plan (never trust "it was written")
function verifyProject(folder, plan) {
  const issues = [];
  let c; try { c = JSON.parse(fs.readFileSync(path.join(folder, 'draft_content.json'), 'utf8')); } catch (e) { return ['draft_content.json cannot be read back: ' + e.message]; }
  let meta; try { meta = JSON.parse(fs.readFileSync(path.join(folder, 'draft_meta_info.json'), 'utf8')); } catch (e) { issues.push('draft_meta_info.json cannot be read back: ' + e.message); }
  const tl = c.id && path.join(folder, 'Timelines', c.id, 'draft_content.json');
  if (!tl || !fs.existsSync(tl)) issues.push('The timeline copy inside Timelines/ is missing.');
  const byId = new Map(); for (const k of ['videos', 'audios', 'texts']) for (const m of c.materials[k] || []) byId.set(m.id, m);
  const visualTracks = c.tracks.filter(t => t.type === 'video');
  if (plan.separateLayers) {
    const kinds = plan.images.map(x => x.kind);
    if (kinds.includes('photo') && kinds.includes('video')) {
      if (visualTracks.length !== 2 || visualTracks[0].name !== 'Images - Lower Layer' || visualTracks[1].name !== 'Videos - Upper Layer') issues.push('Fixed image/video track order is wrong.');
      for (const [index, kind] of ['photo', 'video'].entries()) {
        const expected = plan.images.filter(x => x.kind === kind).length;
        if ((visualTracks[index]?.segments?.length || 0) !== expected) issues.push(`${kind} track segment count mismatch.`);
      }
    }
  }
  // The reference array is chronological; a multi-layer draft has two visual
  // tracks. Compare all clips sorted by original timeline time, not track order.
  const pic = { segments: visualTracks.flatMap(t => t.segments)
    .sort((a, b) => a.target_timerange.start - b.target_timerange.start) };
  if (pic.segments.length !== plan.images.length) issues.push(`Picture count differs: plan ${plan.images.length}, project ${pic.segments.length}.`);
  pic.segments.forEach((s, i) => {
    const p = plan.images[i], m = byId.get(s.material_id);
    if (!m) { issues.push(`Picture ${i + 1}: material missing.`); return; }
    if (!fs.existsSync(m.path)) issues.push(`Picture ${i + 1}: media file missing (${m.path}).`);
    if (p && (s.target_timerange.start !== us(p.start) || s.target_timerange.duration !== us(p.dur))) issues.push(`Picture ${i + 1}: timing differs from the timeline (${s.target_timerange.start}/${s.target_timerange.duration} us).`);
    const first = p && plan.images.find(q => q.file === p.file);
    if (first && m.material_name && !m.material_name.includes(String(first.n).padStart(4, '0'))) issues.push(`Picture ${i + 1}: file order does not match (${m.material_name}).`);
    if (i && s.target_timerange.start < pic.segments[i - 1].target_timerange.start + pic.segments[i - 1].target_timerange.duration) issues.push(`Picture ${i + 1}: overlaps the previous one.`);
  });
  for (const t of c.tracks) for (const s of t.segments) { if (!byId.has(s.material_id)) issues.push(`A ${t.type} segment has no material.`); else if (t.type === 'audio' && !fs.existsSync(byId.get(s.material_id).path)) issues.push('An audio file is missing.'); }
  const nTxt = c.tracks.filter(t => t.type === 'text').reduce((n, t) => n + t.segments.length, 0);
  if (nTxt !== plan.captions.length + plan.titles.length) issues.push(`Caption/title count differs: plan ${plan.captions.length + plan.titles.length}, project ${nTxt}.`);
  const nAud = c.tracks.filter(t => t.type === 'audio').reduce((n, t) => n + t.segments.length, 0);
  if (nAud !== plan.voice.length + plan.music.length + plan.sfx.length) issues.push('Audio clip count differs from the timeline.');
  if (meta && meta.draft_fold_path !== slash(folder)) issues.push('draft_meta_info.json points at a different folder.');
  return issues;
}

// ---------------------------------------------------------------- fallback: ordered media folder + SRT (opens in any editor, CapCut included)
const srtTime = s => { const ms = Math.round(s * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000), sec = Math.floor(ms % 60000 / 1000); return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`; };
function toSrt(list) { return list.map((t, i) => `${i + 1}\n${srtTime(t.start)} --> ${srtTime(t.end)}\n${String(t.text).trim()}\n`).join('\n'); }
function writeFolder({ plan, dest }) {
  fs.mkdirSync(dest, { recursive: true });
  const root = path.join(dest, uniqueFolder(dest, plan.name + ' - CapCut media')); fs.mkdirSync(root);
  const files = copyMedia(plan, root);
  if (plan.captions.length) fs.writeFileSync(path.join(root, 'captions.srt'), toSrt(plan.captions), 'utf8');
  const lines = ['Z Studio timeline (import the numbered pictures into CapCut in this order and place each at its start time)', ''];
  plan.images.forEach(c => lines.push(`${String(c.n).padStart(4, '0')}  ${srtTime(c.start).replace(',', '.')} -> ${srtTime(c.start + c.dur).replace(',', '.')}  (${c.dur.toFixed(3)} s)  ${path.basename(files[c.file])}`));
  plan.voice.forEach(a => lines.push('', `Voiceover: ${path.basename(files[a.file])} starts at ${srtTime(a.start).replace(',', '.')}`));
  fs.writeFileSync(path.join(root, 'timing.txt'), lines.join('\r\n'), 'utf8');
  return { folder: root, images: plan.images.length, srt: plan.captions.length > 0 };
}

module.exports = { detect, compat, isRunning, launch, makePlan, motionOf, buildContent, writeProject, verifyProject, writeFolder, toSrt, capSize, us, uniqueFolder, safeName, capcutRoot };
