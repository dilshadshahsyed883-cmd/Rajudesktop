import {uid,counts,parseCSV,meetsQuality,imageURL} from './core.js';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state={projects:[]},currentId='',activeRowId='',dirty=false,transfers=[],refreshTask=null,toastTimer;
let activeTab='keywords';
function fitScrollAreas() {
  for(const id of ['gallery','jobs']){
    const area=$(id);if(!area || !area.getClientRects().length)continue;
    area.style.maxHeight=Math.max(100,window.innerHeight-area.getBoundingClientRect().top-55)+'px';
  }
}
window.addEventListener('resize',()=>requestAnimationFrame(fitScrollAreas));
function switchTab(name,remember=true) {
  if(!['keywords','images','queue','settings','files'].includes(name))name='keywords';
  activeTab=name;
  for(const panel of document.querySelectorAll('[data-tab-panel]'))panel.hidden=panel.dataset.tabPanel!==name;
  for(const button of document.querySelectorAll('[data-tab]')){const selected=button.dataset.tab===name;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;}
  if(remember)void chrome.storage.local.set({activeSection:name});
  requestAnimationFrame(fitScrollAreas);
}
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=()=>switchTab(button.dataset.tab);
document.querySelector('.workspace-tabs').onkeydown=e=>{
  const tabs=[...document.querySelectorAll('[data-tab]')];const i=tabs.indexOf(document.activeElement);
  if(i<0 || !['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
  e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  switchTab(tabs[next].dataset.tab);tabs[next].focus();
};
const current=()=>state.projects.find(p=>p.id===currentId);
async function send(type,data={}) {
  const result=await chrome.runtime.sendMessage({type,projectId:currentId,...data});
  if(!result?.ok)throw Error(result?.error || 'Extension worker is unavailable. Reload the extension.');return result;
}
function toast(text,error=false) {clearTimeout(toastTimer);$('toast').textContent=text;$('toast').className=error?'error':'';$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,error?10000:5000);}
async function action(fn) {try{await fn();}catch(e){toast(e.message,true);}}
function markDirty(){dirty=true;$('save').textContent='Save changes •';}
async function access() {
  const origins=['https://*/*','http://*/*'];
  if(!await chrome.permissions.contains({origins}) && !await chrome.permissions.request({origins}))throw Error('Page and image access is needed to collect and download. Try again and allow access.');
}
function readRows() {
  return [...$('rows').querySelectorAll('tr')].map(tr=>({id:tr.dataset.id,query:tr.querySelector('.query').value,prefix:tr.querySelector('.prefix').value,qty:Number(tr.querySelector('.qty').value),source:tr.querySelector('.source').value}));
}
async function saveChanges() {
  if(!current())return;
  await send('SAVE',{name:$('projectName').value,rows:readRows(),settings:{source:$('source').value,minWidth:Number($('minWidth').value),minHeight:Number($('minHeight').value),landscape:$('landscape').checked,subfolders:$('subfolders').checked}});
  dirty=false;await refresh(true);
}
function rowHTML(r) {
  return `<tr data-id="${esc(r.id)}"><td><input class="query" aria-label="Search keyword" value="${esc(r.query)}"></td><td><input class="prefix" aria-label="Image name keyword" value="${esc(r.prefix)}"></td><td><input class="qty" aria-label="Required count" type="number" min="1" max="1000" value="${r.qty}"></td><td><select class="source" aria-label="Source"><option value="">Project default</option><option value="google" ${r.source==='google'?'selected':''}>Google</option><option value="getty" ${r.source==='getty'?'selected':''}>Getty Editorial</option><option value="google-first" ${r.source==='google-first'?'selected':''}>Google → Editorial</option></select></td><td class="row-progress"></td><td><div class="row-actions"><button data-row-action="use" title="Use keyword in gallery">Use</button><button data-row-action="up" title="Move up">↑</button><button data-row-action="down" title="Move down">↓</button><button data-row-action="copy" title="Duplicate row">⧉</button><button data-row-action="remove" title="Remove row">×</button></div></td></tr>`;
}
async function refresh(full=false) {
  if(refreshTask){await refreshTask;return refresh(full);}
  refreshTask=(async()=>{
    const result=await send('STATE');state=result.state;transfers=result.transfers;
    if(!current())currentId=state.projects[0]?.id || '';
    render(full);
  })();
  try{await refreshTask;}finally{refreshTask=null;}
}
function render(full) {
  const p=current();
  $('empty').hidden=!!p;$('workspace').hidden=!p;
  $('projects').innerHTML=state.projects.map(x=>`<button class="project-link ${x.id===currentId?'active':''}" data-project="${x.id}">${esc(x.name)}<small>${counts(x).downloaded} / ${counts(x).target} images</small></button>`).join('');
  const projectOptions=state.projects.map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join('');
  if($('projectPicker').dataset.signature!==projectOptions){$('projectPicker').innerHTML=projectOptions;$('projectPicker').dataset.signature=projectOptions;}$('projectPicker').value=currentId;
  if(!p)return;
  const c=counts(p);
  $('keywordCount').textContent=p.rows.length;$('targetCount').textContent=c.target;$('downloadCount').textContent=c.downloaded;$('remainingCount').textContent=c.remaining;
  $('progressFill').style.width=(c.target?Math.min(100,c.downloaded/c.target*100):0)+'%';
  $('projectStatus').textContent=c.target && !c.remaining?'Complete · all targets downloaded':`${c.downloaded} of ${c.target} downloaded · ${c.remaining} still needed`;
  $('queueState').textContent=p.paused?'Paused':c.queued?'Running':'Ready';
  $('queueBadge').textContent=c.queued;
  switchTab(activeTab,false);
  $('save').textContent=dirty?'Save changes •':'Save changes';
  $('folderPath').textContent=`Downloads / Video Image Projects / ${p.folder}`;
  if(full && !dirty) {
    $('projectName').value=p.name;$('rows').innerHTML=p.rows.map(rowHTML).join('');
    for(const key of ['source','minWidth','minHeight'])$(key).value=p.settings[key];
    for(const key of ['landscape','subfolders'])$(key).checked=p.settings[key];
  }
  for(const tr of $('rows').querySelectorAll('tr')) {const n=counts(p,tr.dataset.id);tr.querySelector('.row-progress').innerHTML=`${n.downloaded}/${n.target} saved · ${n.remaining} needed<br>${n.found} found · ${n.selected} selected · ${n.queued} queued`;}
  if(!p.rows.some(r=>r.id===activeRowId))activeRowId=p.rows[0]?.id || '';
  const rowOptions=p.rows.map(r=>`<option value="${r.id}">${esc(r.prefix)} · ${esc(r.query)}</option>`).join('');
  if($('activeRow').dataset.signature!==rowOptions){$('activeRow').innerHTML=rowOptions;$('activeRow').dataset.signature=rowOptions;}$('activeRow').value=activeRowId;
  renderGallery(p);renderJobs(p);
  const mode=p.autoRows?.[activeRowId];
  $('stopAuto').hidden=!mode?.enabled;$('autoDownload').hidden=!!mode?.enabled;
  $('autoStatus').textContent=mode?(p.paused && mode.enabled?'Auto paused · press Resume in Queue':mode.status)+(mode.error?' · '+mode.error:''):'Select manually, or tick image permission and press Auto Download.';
  $('rights').checked=$('rights').checked || !!mode?.enabled;
  requestAnimationFrame(fitScrollAreas);
}
function renderGallery(p) {
  const all=p.candidates.filter(c=>c.rowId===activeRowId);
  const show=$('showAll').checked;
  const visible=all.filter(c=>show || c.licenseRequired || c.selected || (c.original && (!c.width || meetsQuality(p,c))));
  const selected=all.filter(c=>c.selected).length;
  const originals=all.filter(c=>c.original && !c.licenseRequired).length;
  const licensed=all.filter(c=>c.licenseRequired).length;
  $('galleryCount').textContent=`${all.length} found · ${originals} originals · ${selected} selected${licensed?' · '+licensed+' Getty previews':''}`;
  // Update only when the gallery changes; avoid reloading remote images every poll.
  const signature=JSON.stringify(visible.map(c=>[c.id,c.selected,p.jobs.filter(j=>j.url===c.url).map(j=>j.status)]))+show;
  if($('gallery').dataset.signature!==signature) {
    $('gallery').dataset.signature=signature;
    $('gallery').innerHTML=visible.slice(0,300).map(c=>{
      const used=p.jobs.some(j=>j.url===c.url && ['pending','validating','dispatching','downloading','complete'].includes(j.status));
      return `<article class="card ${c.selected?'selected':''}"><div class="thumb"><span class="failed-preview">Preview unavailable</span><img loading="lazy" referrerpolicy="no-referrer" src="${esc(c.preview)}" alt="${esc(c.title)}"><input type="checkbox" aria-label="Select image" data-candidate="${c.id}" ${c.selected?'checked':''} ${c.licenseRequired||used?'disabled':''}></div><div class="card-content"><div class="card-title">${esc(c.title || 'Image')}</div><div class="card-meta">${c.width?`${c.width} × ${c.height}`:'Size checked at download'} · ${c.original?'Original URL':'Thumbnail'}${used?' · Queued/saved':''}</div>${c.licenseRequired?'<div class="license">Getty preview · license required</div>':''}<a href="${esc(imageURL(c.sourcePage)||c.url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a> · <a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">Image ↗</a></div></article>`;
    }).join('');
    for(const img of $('gallery').querySelectorAll('img'))img.addEventListener('error',()=>img.style.visibility='hidden');
  }
  $('galleryHint').textContent=!all.length?'No images collected for this keyword yet. Open search, then collect from the active tab.':!visible.length?'No originals match this view. Open a Google image preview, collect again, or enable “Show thumbnails / below filter”.':`${visible.length} visible${visible.length>300?' (first 300 shown)':''}. Auto-select uses known original dimensions; manually selected images are validated before saving.`;
}
function renderJobs(p) {
  const jobs=p.jobs.slice().reverse();
  $('jobs').innerHTML=jobs.length?jobs.map(j=>{
    const r=p.rows.find(r=>r.id===j.rowId);const t=transfers.find(t=>t.id===j.id);
    const progress=t?.total>0?` · ${Math.floor(t.bytes/t.total*100)}%` : '';
    return `<div class="job"><div><strong>${esc(j.filename?.split('/').pop() || r?.prefix || 'Image')}</strong><small>${esc(j.error || (j.width?`${j.width} × ${j.height}`:j.url))}</small></div><span class="${esc(j.status)}">${esc(j.status)}${progress}${t?.paused?' · paused':''}</span></div>`;
  }).join(''):'<p class="hint">Selected images will appear here. Your project stays saved when Chrome closes.</p>';
}
async function switchProject(id) {
  if(dirty)await saveChanges();currentId=id;activeRowId='';dirty=false;
  await chrome.storage.local.set({activeProject:currentId});await refresh(true);
}
for(const id of ['newProject','newMobile','firstProject'])$(id).onclick=()=>{$('newName').value='';$('createDialog').showModal();$('newName').focus();};
$('closeDialog').onclick=()=>$('createDialog').close();
$('createForm').onsubmit=e=>{e.preventDefault();void action(async()=>{if(dirty)await saveChanges();const result=await send('CREATE',{name:$('newName').value});$('createDialog').close();switchTab('keywords');await switchProject(result.id);});};
$('wide').onclick=()=>chrome.tabs.create({url:chrome.runtime.getURL('panel.html')});
$('save').onclick=()=>action(async()=>{await saveChanges();toast('Project saved.');});
$('projectName').oninput=markDirty;$('rows').oninput=markDirty;$('rows').onchange=markDirty;
for(const id of ['source','minWidth','minHeight','landscape','subfolders'])$(id).onchange=markDirty;
$('projects').onclick=e=>{const b=e.target.closest('[data-project]');if(b)void action(()=>switchProject(b.dataset.project));};
$('projectPicker').onchange=()=>action(()=>switchProject($('projectPicker').value));
$('addRow').onclick=()=>{$('rows').insertAdjacentHTML('beforeend',rowHTML({id:uid(),query:'',prefix:'',qty:5,source:''}));markDirty();$('rows').lastElementChild.querySelector('input').focus();};
$('rows').onclick=e=>{
  const b=e.target.closest('[data-row-action]');if(!b)return;const tr=b.closest('tr');
  if(b.dataset.rowAction==='use'){void action(async()=>{if(dirty)await saveChanges();activeRowId=tr.dataset.id;switchTab('images');render(false);});return;}
  if(b.dataset.rowAction==='up' && tr.previousElementSibling)tr.previousElementSibling.before(tr);
  if(b.dataset.rowAction==='down' && tr.nextElementSibling)tr.nextElementSibling.after(tr);
  if(b.dataset.rowAction==='remove')tr.remove();
  if(b.dataset.rowAction==='copy') {const r=readRows().find(r=>r.id===tr.dataset.id);r.id=uid();tr.insertAdjacentHTML('afterend',rowHTML(r));}
  markDirty();
};
async function importText(text) {
  const rows=parseCSV(text);if(readRows().length+rows.length>500)throw Error('Maximum 500 rows.');
  $('rows').insertAdjacentHTML('beforeend',rows.map(rowHTML).join(''));markDirty();$('bulk').value='';toast(`${rows.length} keyword rows added. Save changes to keep them.`);
}
$('importPaste').onclick=()=>action(()=>importText($('bulk').value));
$('csvFile').onchange=()=>action(async()=>{const file=$('csvFile').files[0];if(file){if(file.size>1000000)throw Error('CSV must be under 1 MB.');await importText(await file.text());}$('csvFile').value='';});
$('activeRow').onchange=()=>{activeRowId=$('activeRow').value;render(false);};
$('showAll').onchange=()=>renderGallery(current());
async function search(source,rowId=activeRowId) {await access();if(dirty)await saveChanges();rowId ||= activeRowId;if(!rowId)throw Error('Add a keyword row first.');await send('SEARCH',{rowId,source});toast('Search opened. Browse results, then press Collect from active tab.');}
$('search').onclick=()=>action(()=>search($('searchSource').value || undefined));
$('fallback').onclick=()=>action(()=>search('getty'));
$('nextSearch').onclick=()=>action(async()=>{await access();if(dirty)await saveChanges();const p=current();const i=p.rows.findIndex(r=>r.id===activeRowId);const ordered=[...p.rows.slice(i+1),...p.rows.slice(0,i+1)];const row=ordered.find(r=>counts(p,r.id).downloaded<r.qty);if(!row)throw Error('All keyword targets are complete.');activeRowId=row.id;render(false);await search(undefined,row.id);});
$('collect').onclick=()=>action(async()=>{await access();if(dirty)await saveChanges();const result=await send('COLLECT',{rowId:activeRowId});await refresh();toast(`${result.added} new image candidates collected.`);});
$('addUrl').onclick=()=>action(async()=>{if(dirty)await saveChanges();await send('ADD_URL',{rowId:activeRowId,url:$('manualUrl').value});$('manualUrl').value='';await refresh();toast('Image URL added. Its actual quality will be checked at download.');});
$('autoSelect').onclick=()=>action(async()=>{if(dirty)await saveChanges();await send('AUTOSELECT',{rowId:activeRowId});await refresh();toast('Suitable originals selected up to the remaining target. Review them before downloading.');});
$('gallery').onchange=e=>{if(e.target.dataset.candidate)void action(async()=>{await send('SELECT',{candidateId:e.target.dataset.candidate,selected:e.target.checked});await refresh();});};
$('download').onclick=()=>action(async()=>{if(!$('rights').checked)throw Error('Confirm image usage permission first.');await access();if(dirty)await saveChanges();const result=await send('ENQUEUE',{rightsConfirmed:true});await refresh();toast(result.added?`${result.added} images added to the download queue.`:'No new images queued. Select images and check the remaining target.');});
$('autoDownload').onclick=()=>action(async()=>{
  if(!$('rights').checked)throw Error('Tick the image usage permission checkbox, then press Auto Download.');
  await access();if(dirty)await saveChanges();
  const result=await send('AUTO_START',{rowId:activeRowId,rightsConfirmed:true});await refresh();toast(result.status);
});
$('stopAuto').onclick=()=>action(async()=>{await send('AUTO_STOP',{rowId:activeRowId});await refresh();toast('Auto stopped for this keyword. Completed files are kept.');});
for(const [id,type] of [['pause','PAUSE'],['resume','RESUME'],['retry','RETRY'],['cancel','CANCEL']])$(id).onclick=()=>action(async()=>{if(type==='RETRY')await access();await send(type);await refresh();toast(type==='CANCEL'?'Pending downloads cancelled. Completed files are kept.':type==='PAUSE'?'Queue paused.':type==='RESUME'?'Queue resumed.':'Failed or cancelled downloads rechecked for retry.');});
for(const [id,kind] of [['summary','summary'],['sources','sources'],['exportKeywords','keywords']])$(id).onclick=()=>action(async()=>{if(dirty)await saveChanges();await send('REPORT',{kind});toast('Report sent to Downloads.');});
$('backup').onclick=()=>action(async()=>{if(dirty)await saveChanges();const {backup}=await send('BACKUP');const url=URL.createObjectURL(new Blob([backup],{type:'application/json'}));try{await chrome.downloads.download({url,filename:`Video Image Projects/${current().folder}/Project_Record.json`,conflictAction:'uniquify',saveAs:false});}finally{setTimeout(()=>URL.revokeObjectURL(url),30000);}toast('Project record exported.');});
$('folder').onclick=()=>chrome.downloads.showDefaultFolder();
$('deleteProject').onclick=()=>action(async()=>{if(!confirm('Delete this project record? Downloaded files will stay on disk.'))return;await send('DELETE');dirty=false;currentId='';activeRowId='';await refresh(true);toast('Project record deleted.');});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
void action(async()=>{const saved=await chrome.storage.local.get(['activeProject','activeSection']);currentId=saved.activeProject||'';activeTab=saved.activeSection||'keywords';await refresh(true);});
setInterval(()=>{if(!document.hidden)void action(()=>refresh());},2000);
