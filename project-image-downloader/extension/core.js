export const uid = () => crypto.randomUUID();
export const blankState = () => ({version: 1, projects: [], bindings: {}});
export function safeName(value, fallback = 'Untitled') {
  let s = String(value || '').normalize('NFC').replace(/[<>:"/\\|?*\x00-\x1f]/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/g, '').slice(0, 80).trim();
  if (!s || /^\.+$/.test(s)) s = fallback;
  if (/^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)/i.test(s)) s = '_' + s;
  return s;
}
export function imageURL(value, base) {
  try {
    const u = new URL(value, base);
    if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password) return null;
    const h = u.hostname.toLowerCase();
    if (h === 'localhost' || h.endsWith('.localhost') || h.endsWith('.local') || h.includes(':') || /^(0|10|127)\./.test(h) || /^169\.254\./.test(h) || /^192\.168\./.test(h) || /^172\.(1[6-9]|2\d|3[01])\./.test(h)) return null;
    u.hash = '';
    return u.href;
  } catch { return null; }
}
export function searchURL(query, source) {
  if (source === 'getty') return 'https://www.gettyimages.com/search/2/image?family=editorial&phrase=' + encodeURIComponent(query.trim()) + '&sort=mostpopular';
  return 'https://www.google.com/search?tbm=isch&q=' + encodeURIComponent(query.trim());
}
export function newProject(name) {
  const id = uid();
  return {id, name: safeName(name), folder: safeName(name) + ' [' + id.slice(0, 8) + ']', created: new Date().toISOString(), rows: [], candidates: [], jobs: [], counters: {}, paused: true,
    settings: {source: 'google-first', minWidth: 1280, minHeight: 720, landscape: true, subfolders: false}};
}
export function normalizeRow(r) {
  const query = String(r.query || '').trim().slice(0, 500);
  const prefix = String(r.prefix || '').trim().slice(0, 80);
  const qty = Number(r.qty);
  if (!query || !prefix || !Number.isInteger(qty) || qty < 1 || qty > 1000) throw Error('Each row needs a search keyword, image name and quantity from 1 to 1000.');
  const source = ['google', 'getty', 'google-first'].includes(r.source) ? r.source : '';
  return {id: r.id || uid(), query, prefix, qty, source};
}
export function counts(p, rowId) {
  const jobs = p.jobs.filter(j => !rowId || j.rowId === rowId);
  const target = p.rows.filter(r => !rowId || r.id === rowId).reduce((n,r) => n + r.qty, 0);
  const downloaded = jobs.filter(j => j.status === 'complete').length;
  const queued = jobs.filter(j => ['pending', 'validating', 'dispatching', 'downloading'].includes(j.status)).length;
  const found = p.candidates.filter(c => !rowId || c.rowId === rowId).length;
  const selected = p.candidates.filter(c => c.selected && (!rowId || c.rowId === rowId)).length;
  return {target, downloaded, queued, found, selected, remaining: Math.max(0, target-downloaded)};
}
export function nextFilename(p, row, ext) {
  const prefix = safeName(row.prefix, 'Image');
  const key = prefix.toLocaleLowerCase('en-US');
  const number = (p.counters[key] || 0) + 1;
  p.counters[key] = number;
  return `Video Image Projects/${p.folder}/${p.settings.subfolders ? prefix + '/' : ''}${prefix} ${number}.${ext}`;
}
export function sniffImage(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const ascii = (a,z) => String.fromCharCode(...b.slice(a,z));
  if (b[0] === 255 && b[1] === 216 && b[2] === 255) return {ext:'jpg', mime:'image/jpeg'};
  if (b[0] === 137 && ascii(1,4) === 'PNG' && b[4] === 13 && b[5] === 10 && b[6] === 26 && b[7] === 10) return {ext:'png', mime:'image/png'};
  if (['GIF87a','GIF89a'].includes(ascii(0,6))) return {ext:'gif', mime:'image/gif'};
  if (ascii(0,4) === 'RIFF' && ascii(8,12) === 'WEBP') return {ext:'webp', mime:'image/webp'};
  if (ascii(4,8) === 'ftyp' && /avif|avis/.test(ascii(8,32))) return {ext:'avif', mime:'image/avif'};
  throw Error('Response is not a supported JPG, PNG, WebP, GIF or AVIF image.');
}
export function meetsQuality(p, c) {
  return c.width >= p.settings.minWidth && c.height >= p.settings.minHeight && (!p.settings.landscape || c.width >= c.height);
}
export function enqueueSelected(p) {
  let added = 0;
  for (const row of p.rows) {
    let remaining = Math.max(0, row.qty-counts(p,row.id).downloaded-counts(p,row.id).queued);
    for (const c of p.candidates.filter(c => c.rowId === row.id && c.selected)) {
      if (!remaining) break;
      if (c.licenseRequired || p.jobs.some(j => j.url === c.url && !['failed','cancelled','duplicate'].includes(j.status))) continue;
      p.jobs.push({id:uid(), candidateId:c.id, rowId:row.id, url:c.url, sourcePage:c.sourcePage, source:c.source, title:c.title, status:'pending', created:new Date().toISOString(), error:''});
      c.selected = false; remaining--; added++;
    }
  }
  return added;
}
// Auto mode replenishes target slots with untried originals after failures/duplicates.
// Unknown sizes are allowed into validation; actual decoded dimensions remain mandatory.
export function refillAuto(p) {
  if(p.paused)return 0;
  let added=0;
  for(const [rowId,mode] of Object.entries(p.autoRows || {})) {
    if(!mode.enabled)continue;
    const row=p.rows.find(r=>r.id===rowId);if(!row){mode.enabled=false;continue;}
    const n=counts(p,rowId);
    if(n.downloaded>=row.qty){mode.enabled=false;mode.status='Target complete';continue;}
    let slots=Math.max(0,row.qty-n.downloaded-n.queued);
    const tried=new Set(p.jobs.map(j=>j.url));
    const candidates=p.candidates.filter(c=>c.rowId===rowId && c.original && !c.licenseRequired && (!c.width || !c.height || meetsQuality(p,c)) && !tried.has(c.url))
      .sort((a,b)=>b.width*b.height-a.width*a.height);
    for(const c of candidates) {
      if(!slots)break;
      if(tried.has(c.url))continue;
      p.jobs.push({id:uid(),candidateId:c.id,rowId,url:c.url,sourcePage:c.sourcePage,source:c.source,title:c.title,status:'pending',created:new Date().toISOString(),error:'',auto:true});
      c.selected=false;tried.add(c.url);slots--;added++;
    }
    const now=counts(p,rowId);
    const getty=p.candidates.filter(c=>c.rowId===rowId && c.licenseRequired).length;
    mode.status=now.queued?`Auto running · ${now.downloaded}/${row.qty} saved · ${now.queued} queued`:
      getty && !p.candidates.some(c=>c.rowId===rowId && c.original && !c.licenseRequired)?`${getty} Getty previews; open Google search for downloadable originals`:
      `Need ${now.remaining} more · open previews or scroll results; new originals collect automatically`;
  }
  return added;
}
export function parseCSV(text) {
  text = text.replace(/^\uFEFF/, '');
  const first = text.split(/\r?\n/)[0] || '';
  const delim = first.includes('\t') ? '\t' : ',';
  const lines = []; let row = [], cell = '', quote = false;
  for (let i=0;i<text.length;i++) {
    const c = text[i];
    if (c === '"') { if (quote && text[i+1] === '"') {cell += '"';i++;} else quote = !quote; }
    else if (c === delim && !quote) {row.push(cell.trim());cell='';}
    else if ((c === '\n' || c === '\r') && !quote) { if(c === '\r' && text[i+1] === '\n') i++; row.push(cell.trim()); if(row.some(Boolean)) lines.push(row); row=[];cell=''; }
    else cell += c;
  }
  if (quote) throw Error('CSV contains an unclosed quoted field.');
  row.push(cell.trim()); if(row.some(Boolean)) lines.push(row);
  if (lines.length && /^(search[ _]?keyword|query)$/i.test(lines[0][0])) lines.shift();
  if (!lines.length || lines.length > 500) throw Error('Paste 1–500 rows: Search Keyword, Image Name, Qty, optional Source.');
  return lines.map((r,i) => {try {return normalizeRow({query:r[0],prefix:r[1],qty:r[2],source:r[3]});} catch(e) {throw Error(`Row ${i+1}: ${e.message}`);} });
}
export const csvCell = value => '"' + String(value ?? '').replaceAll('"','""') + '"';
export function keywordCSV(p) {
  return ['Search Keyword,Image Name,Qty,Source', ...p.rows.map(r => [r.query,r.prefix,r.qty,r.source].map(csvCell).join(','))].join('\r\n');
}
export function reports(p) {
  const c = counts(p);
  const complete = p.jobs.filter(j => j.status === 'complete');
  const txt = [`PROJECT IMAGE DOWNLOADER — MEDIA SUMMARY`, `Project: ${p.name}`, `Generated: ${new Date().toISOString()}`, `Downloaded: ${c.downloaded} / ${c.target}`, `Still required: ${c.remaining}`, '', ...p.rows.flatMap(r => {
    const n=counts(p,r.id);
    return [`${r.prefix} | Search: ${r.query}`, `Found ${n.found} | Downloaded ${n.downloaded}/${r.qty} | Remaining ${n.remaining}`, ...complete.filter(j=>j.rowId===r.id).map(j=>'  '+(j.actualFilename || j.filename)), ''];
  }), 'Downloaded filenames reflect Chrome confirmation. Missing targets are not marked complete.'].join('\r\n');
  const csv = [['Search Keyword','Image Name','Filename','Status','Image URL','Source Page','Source','Width','Height','SHA256','Error'], ...p.jobs.map(j => {
    const r=p.rows.find(r=>r.id===j.rowId)||{};
    return [r.query,r.prefix,j.actualFilename||j.filename||'',j.status,j.url,j.sourcePage,j.source,j.width,j.height,j.hash,j.error];
  })].map(row=>row.map(csvCell).join(',')).join('\r\n');
  return {txt,csv};
}
