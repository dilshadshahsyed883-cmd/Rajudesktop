import {blankState,newProject,normalizeRow,uid,imageURL,counts,searchURL,enqueueSelected,refillAuto,nextFilename,sniffImage,meetsQuality,reports,keywordCSV} from './core.js';
import {load,save} from './db.js';

let state;
let serial=Promise.resolve();
const running=new Set();
const controllers=new Map();
const collectedAt=new Map();
function locked(fn) {
  const task=serial.then(async()=>{await ready;return fn();});
  serial=task.catch(e=>console.error('Project Image Downloader:',e));
  return task;
}
async function persist() {await save(state);}
function project(id) {const p=state.projects.find(p=>p.id===id); if(!p) throw Error('Project not found.');return p;}
function jobById(id) {for(const p of state.projects) {const j=p.jobs.find(j=>j.id===id);if(j)return {p,j};}return {};}
function boundTab(p,rowId) {return Object.entries(state.bindings).reverse().find(([,b])=>b.projectId===p.id && b.rowId===rowId)?.[0];}
async function collectTab(p,rowId,tabId) {
  if(!p.rows.some(r=>r.id===rowId))throw Error('Select a keyword.');
  const binding=state.bindings[tabId];
  if(binding && (binding.projectId!==p.id || binding.rowId!==rowId))throw Error('This tab belongs to a different keyword. Select its keyword before collecting.');
  await chrome.scripting.executeScript({target:{tabId},files:['collector.js']});
  const [result]=await chrome.scripting.executeScript({target:{tabId},func:()=>collectPageImages()});
  const data=result?.result;if(!data?.items)throw Error('Page is still loading. Try Collect again.');
  let added=0;
  for(const raw of data.items.slice(0,600)) {
    const url=imageURL(raw.url);if(!url)continue;
    const existing=p.candidates.find(c=>c.rowId===rowId && c.url===url);
    const candidate={...raw,url,preview:imageURL(raw.preview)||url,sourcePage:imageURL(raw.sourcePage)||data.page};
    if(existing){if(raw.original && (!existing.original || raw.width>existing.width))Object.assign(existing,candidate);continue;}
    if(p.candidates.length>=10000)break;
    p.candidates.push({...candidate,id:uid(),rowId,selected:false});added++;
  }
  return {added,source:data.source};
}
async function collectAutoTabs(force=false) {
  for(const p of state.projects) {
    if(p.paused)continue;
    for(const [rowId,mode] of Object.entries(p.autoRows || {})) {
      if(!mode.enabled || mode.tabId==null)continue;
      const key=p.id+rowId;
      if(!force && Date.now()-(collectedAt.get(key)||0)<4000)continue;
      collectedAt.set(key,Date.now());
      try{await collectTab(p,rowId,mode.tabId);mode.error='';}
      catch(e){mode.error=e.message;}
    }
    refillAuto(p);
  }
}
function settle(j,d) {
  if(j.status==='cancelled' && d.state!=='complete') return;
  j.actualFilename=d.filename || j.actualFilename;
  if(d.state==='complete') {j.status='complete';j.completed=d.endTime || new Date().toISOString();j.error='';}
  else if(d.state==='interrupted') {j.status='failed';j.error=d.error || 'Download interrupted';}
  else {j.status='downloading';j.browserPaused=Boolean(d.paused);}
}
async function reconcile(initial=false) {
  for(const p of state.projects) for(const j of p.jobs) {
    if(initial && j.status==='validating') j.status='pending';
    if(j.downloadId!=null && ['downloading','dispatching','cancelled'].includes(j.status)) {
      const [d]=await chrome.downloads.search({id:j.downloadId});
      if(d) settle(j,d); else if(j.status!=='cancelled') {j.status='failed';j.error='Chrome no longer has this download. Retry explicitly.';}
    } else if(initial && j.status==='dispatching') {
      const matches=await chrome.downloads.search({startedAfter:j.dispatchedAt,limit:100,orderBy:['-startTime']});
      const d=matches.find(d=>d.filename?.replaceAll('\\','/').endsWith('/'+j.filename));
      if(d){j.downloadId=d.id;settle(j,d);}else {j.status='failed';j.error='Dispatch interrupted. Check Downloads before retrying.';}
    }
  }
  await persist();
}
const ready=(async()=>{
  state=await load() || blankState();
  await reconcile(true);
  await chrome.alarms.create('queue-recovery',{periodInMinutes:0.5});
  await chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true});
})();

async function downloadReport(p,kind) {
  const r=reports(p);
  const filename=kind==='summary'?'Media_Summary.txt':kind==='sources'?'Image_Sources.csv':'Keywords.csv';
  const text=kind==='summary'?r.txt:kind==='sources'?r.csv:keywordCSV(p);
  return chrome.downloads.download({url:'data:'+(kind==='summary'?'text/plain':'text/csv')+';charset=utf-8,'+encodeURIComponent('\uFEFF'+text),filename:`Video Image Projects/${p.folder}/${filename}`,conflictAction:'uniquify',saveAs:false});
}

async function handle(m) {
  if(m.type==='STATE') {
    await collectAutoTabs();
    // Byte counts are polled because Chrome does not emit onChanged for bytesReceived.
    const transfers=[];
    for(const p of state.projects) for(const j of p.jobs.filter(j=>['downloading','cancelled'].includes(j.status) && j.downloadId!=null)) {
      const [d]=await chrome.downloads.search({id:j.downloadId});
      if(d){settle(j,d);transfers.push({id:j.id,bytes:d.bytesReceived,total:d.totalBytes,paused:d.paused});}
    }
    await persist();return {state,transfers};
  }
  if(m.type==='CREATE') {const p=newProject(m.name);state.projects.unshift(p);await persist();return {id:p.id};}
  let p=project(m.projectId);
  if(m.type==='SAVE') {
    p=structuredClone(p);
    if(m.name) p.name=String(m.name).trim().slice(0,100) || p.name;
    if(m.settings) {
      const {source,minWidth,minHeight,landscape,subfolders}=m.settings;
      if(!['google','getty','google-first'].includes(source)) throw Error('Invalid source.');
      if(!Number.isInteger(minWidth)||!Number.isInteger(minHeight)||minWidth<0||minHeight<0||minWidth>20000||minHeight>20000) throw Error('Resolution must be 0–20000 pixels.');
      p.settings={source,minWidth,minHeight,landscape:!!landscape,subfolders:!!subfolders};
    }
    if(m.rows) {
      if(m.rows.length>500) throw Error('Maximum 500 rows per project.');
      const rows=m.rows.map(normalizeRow);
      if(new Set(rows.map(r=>r.id)).size!==rows.length) throw Error('Duplicate row IDs.');
      for(const r of p.rows) {
        const replacement=rows.find(n=>n.id===r.id);
        const used=p.jobs.some(j=>j.rowId===r.id);
        if(used && (!replacement || replacement.query!==r.query || replacement.prefix!==r.prefix)) throw Error('A row with download history must keep its search/name. Add a new row instead.');
        if(replacement && replacement.qty<counts(p,r.id).downloaded+counts(p,r.id).queued) throw Error('Quantity cannot be lower than completed + queued downloads.');
      }
      const changedQueries=new Set(p.rows.filter(r=>rows.some(n=>n.id===r.id && n.query!==r.query)).map(r=>r.id));
      p.rows=rows;
      p.candidates=p.candidates.filter(c=>rows.some(r=>r.id===c.rowId) && !changedQueries.has(c.rowId));
      if(p.autoRows)for(const rowId of Object.keys(p.autoRows))if(!rows.some(r=>r.id===rowId) || changedQueries.has(rowId))delete p.autoRows[rowId];
    }
    state.projects[state.projects.findIndex(x=>x.id===p.id)]=p;
  } else if(m.type==='SEARCH') {
    const row=p.rows.find(r=>r.id===m.rowId);if(!row) throw Error('Add and save a keyword row first.');
    const source=m.source || row.source || p.settings.source;
    const tab=await chrome.tabs.create({url:searchURL(row.query,source==='getty'?'getty':'google'),active:true});
    state.bindings[tab.id]={projectId:p.id,rowId:row.id};
    if(p.autoRows?.[row.id]?.enabled){p.autoRows[row.id].tabId=tab.id;collectedAt.delete(p.id+row.id);}
    await persist();return {tabId:tab.id};
  } else if(m.type==='COLLECT') {
    const row=p.rows.find(r=>r.id===m.rowId); if(!row)throw Error('Select a keyword.');
    const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});
    const tabId=tab && /^https?:/.test(tab.url||'')?tab.id:Number(boundTab(p,row.id));
    if(!Number.isInteger(tabId))throw Error('Open a normal Google, Getty or source webpage first.');
    const result=await collectTab(p,row.id,tabId);
    if(p.autoRows?.[row.id]?.enabled)p.autoRows[row.id].tabId=tabId;
    refillAuto(p);await persist();return result;
  } else if(m.type==='ADD_URL') {
    if(!p.rows.some(r=>r.id===m.rowId))throw Error('Select a keyword first.');
    const url=imageURL(m.url);if(!url)throw Error('Enter a public HTTP(S) image URL.');
    if(p.candidates.some(c=>c.rowId===m.rowId && c.url===url))throw Error('This URL is already in this keyword gallery.');
    const licenseRequired=/(^|\.)(gettyimages\.[a-z.]+|istockphoto\.com)$/i.test(new URL(url).hostname);
    p.candidates.push({id:uid(),rowId:m.rowId,url,preview:url,width:0,height:0,title:'Added image URL',source:'manual',sourcePage:url,original:true,licenseRequired,selected:false});
  } else if(m.type==='SELECT') {
    const c=p.candidates.find(c=>c.id===m.candidateId);if(c && !c.licenseRequired)c.selected=!!m.selected;
  } else if(m.type==='AUTOSELECT') {
    const row=p.rows.find(r=>r.id===m.rowId);if(!row)throw Error('Select a keyword.');
    let n=Math.max(0,row.qty-counts(p,row.id).downloaded-counts(p,row.id).queued);
    const used=new Set(p.jobs.filter(j=>!['failed','cancelled','duplicate'].includes(j.status)).map(j=>j.url));
    for(const c of p.candidates.filter(c=>c.rowId===row.id))c.selected=false;
    for(const c of p.candidates.filter(c=>c.rowId===row.id && c.original && !c.licenseRequired && meetsQuality(p,c)).sort((a,b)=>b.width*b.height-a.width*a.height)) {
      if(n>0 && !used.has(c.url)){c.selected=true;used.add(c.url);n--;}
    }
  } else if(m.type==='AUTO_START') {
    if(!m.rightsConfirmed)throw Error('Confirm image usage permission before Auto Download.');
    if(!p.rows.some(r=>r.id===m.rowId))throw Error('Select a keyword first.');
    p.autoRows ||= {};
    let tabId;
    const [tab]=await chrome.tabs.query({active:true,lastFocusedWindow:true});
    if(tab && /^https?:/.test(tab.url||'')) {
      const binding=state.bindings[tab.id];
      if(!binding || (binding.projectId===p.id && binding.rowId===m.rowId))tabId=tab.id;
    }
    if(tabId==null && boundTab(p,m.rowId)!=null)tabId=Number(boundTab(p,m.rowId));
    if(tabId!=null)state.bindings[tabId]={projectId:p.id,rowId:m.rowId};
    p.autoRows[m.rowId]={enabled:true,tabId,status:'Starting Auto Download',error:''};p.paused=false;
    if(tabId!=null){try{await collectTab(p,m.rowId,tabId);}catch(e){p.autoRows[m.rowId].error=e.message;}}
    const added=refillAuto(p);await persist();return {added,status:p.autoRows[m.rowId].status};
  } else if(m.type==='AUTO_STOP') {
    if(p.autoRows?.[m.rowId]){p.autoRows[m.rowId].enabled=false;p.autoRows[m.rowId].status='Auto stopped';}
    for(const j of p.jobs.filter(j=>j.rowId===m.rowId && j.auto && ['pending','validating','dispatching','downloading'].includes(j.status))) {
      j.status='cancelled';controllers.get(j.id)?.abort();
      if(j.downloadId!=null)await chrome.downloads.cancel(j.downloadId).catch(()=>{});
    }
  } else if(m.type==='ENQUEUE') {
    if(!m.rightsConfirmed)throw Error('Confirm you have permission to use the selected images.');
    const added=enqueueSelected(p);p.paused=false;await persist();return {added};
  } else if(m.type==='PAUSE') {
    p.paused=true;
    for(const j of p.jobs) {
      if(j.status==='validating'){j.status='pending';controllers.get(j.id)?.abort();}
      if(j.status==='downloading')await chrome.downloads.pause(j.downloadId).catch(()=>{});
    }
  } else if(m.type==='RESUME') {
    p.paused=false;
    for(const j of p.jobs.filter(j=>j.status==='downloading'))await chrome.downloads.resume(j.downloadId).catch(()=>{});
  } else if(m.type==='CANCEL') {
    p.paused=true;
    for(const mode of Object.values(p.autoRows || {})){mode.enabled=false;mode.status='Auto stopped';}
    for(const j of p.jobs.filter(j=>['pending','validating','dispatching','downloading'].includes(j.status))) {
      j.status='cancelled';controllers.get(j.id)?.abort();
      if(j.downloadId!=null)await chrome.downloads.cancel(j.downloadId).catch(()=>{});
    }
  } else if(m.type==='RETRY') {
    let retried=0;
    for(const j of p.jobs.filter(j=>['failed','cancelled'].includes(j.status))) {
      const row=p.rows.find(r=>r.id===j.rowId);
      if(!row || counts(p,row.id).downloaded+counts(p,row.id).queued>=row.qty)continue;
      if(p.jobs.some(x=>x.id!==j.id && x.url===j.url && !['failed','cancelled','duplicate'].includes(x.status)))continue;
      if(j.downloadId!=null) {
        const [d]=await chrome.downloads.search({id:j.downloadId});
        if(d?.state==='complete'){settle(j,d);continue;}
        if(d?.state==='in_progress'){await chrome.downloads.resume(d.id).catch(()=>{});settle(j,d);retried++;continue;}
        if(d?.canResume) {try {await chrome.downloads.resume(d.id);j.status='downloading';j.error='';retried++;continue;}catch{}}
      }
      j.status='pending';j.error='';j.downloadId=null;j.hash=null;retried++;
    }
    p.paused=false;await persist();return {retried};
  } else if(m.type==='REPORT') {return {downloadId:await downloadReport(p,m.kind)};}
  else if(m.type==='BACKUP') {return {backup:JSON.stringify({format:'project-image-downloader',version:1,project:p},null,2)};}
  else if(m.type==='DELETE') {
    if(p.jobs.some(j=>['validating','dispatching','downloading'].includes(j.status)))throw Error('Cancel the queue before deleting this project.');
    state.projects=state.projects.filter(x=>x.id!==p.id);
    for(const [id,b] of Object.entries(state.bindings))if(b.projectId===p.id)delete state.bindings[id];
  } else throw Error('Unknown action.');
  await persist();return {};
}

// All state changes are serialized; slow remote fetches run outside this lock.
chrome.runtime.onMessage.addListener((m,sender,respond)=>{
  if(sender.id!==chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL('')))return false;
  locked(()=>handle(m)).then(data=>{respond({ok:true,...data});void pump();},e=>respond({ok:false,error:e.message}));return true;
});
chrome.downloads.onChanged.addListener(delta=>{
  void locked(async()=>{
    for(const p of state.projects)for(const j of p.jobs.filter(j=>j.downloadId===delta.id && ['downloading','dispatching','cancelled'].includes(j.status))) {
      const [d]=await chrome.downloads.search({id:delta.id});if(d)settle(j,d);
    }
    await persist();
  }).then(()=>pump());
});
chrome.tabs.onRemoved.addListener(id=>{void locked(async()=>{delete state.bindings[id];for(const p of state.projects)for(const mode of Object.values(p.autoRows||{}))if(mode.tabId===id){mode.tabId=null;mode.error='Search tab closed. Open search to reconnect Auto.';}await persist();});});
chrome.alarms.onAlarm.addListener(a=>{if(a.name==='queue-recovery')void locked(async()=>{await reconcile();await collectAutoTabs();await persist();}).then(()=>pump());});
chrome.runtime.onStartup.addListener(()=>{void ready.then(()=>pump());});
chrome.runtime.onInstalled.addListener(()=>{void ready.then(()=>pump());});

async function pump() {
  await locked(async()=>{
    let slots=2-running.size-state.projects.flatMap(p=>p.jobs).filter(j=>['downloading','dispatching'].includes(j.status)).length;
    for(const p of state.projects) {
      if(p.paused)continue;
      refillAuto(p);await persist();
      for(const j of p.jobs.filter(j=>j.status==='pending')) {
        if(running.has(j.id))continue;
        if(slots<=0)break;
        j.status='validating';running.add(j.id);slots--;
        await persist();
        void processImage(j.id).finally(()=>{running.delete(j.id);controllers.delete(j.id);void pump();});
      }
    }
  });
}
async function fetchBytes(url,signal) {
  if(!imageURL(url))throw Error('Invalid image URL.');
  const response=await fetch(url,{signal,credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store'});
  if(!response.ok)throw Error(`Source returned HTTP ${response.status}. Open its page or choose another original.`);
  if(!imageURL(response.url || url))throw Error('Source redirected to a non-public URL.');
  const max=20*1024*1024;
  if(Number(response.headers.get('content-length'))>max)throw Error('Image exceeds the 20 MB limit.');
  const reader=response.body.getReader();const chunks=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>max){await reader.cancel();throw Error('Image exceeds the 20 MB limit.');}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const b of chunks){bytes.set(b,offset);offset+=b.length;}return bytes;
}
async function processImage(id) {
  const controller=new AbortController();controllers.set(id,controller);
  const timeout=setTimeout(()=>controller.abort(),20000);
  try {
    const snapshot=await locked(()=>{
      const {p,j}=jobById(id);if(!j || j.status!=='validating' || p.paused)return null;
      return {url:j.url};
    });
    if(!snapshot)return;
    const bytes=await fetchBytes(snapshot.url,controller.signal);
    const format=sniffImage(bytes);
    const bitmap=await createImageBitmap(new Blob([bytes],{type:format.mime}));
    const width=bitmap.width,height=bitmap.height;bitmap.close();
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
    clearTimeout(timeout);
    let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
    const dataURL=`data:${format.mime};base64,${btoa(binary)}`;
    await locked(async()=>{
      const {p,j}=jobById(id);if(!j || j.status!=='validating')return;
      if(p.paused){j.status='pending';await persist();return;}
      if(!meetsQuality(p,{width,height}))throw Error(`Original is ${width}×${height}; below your quality/orientation settings.`);
      const duplicate=p.jobs.find(x=>x.id!==id && x.hash===hash && ['dispatching','downloading','complete'].includes(x.status));
      if(duplicate){j.status='duplicate';j.error='Exact image bytes already used in this project. Choose a different photograph.';j.hash=hash;await persist();return;}
      const row=p.rows.find(r=>r.id===j.rowId);if(!row)throw Error('Keyword row removed.');
      j.hash=hash;j.width=width;j.height=height;j.mime=format.mime;
      j.filename=nextFilename(p,row,format.ext);
      j.dispatchedAt=new Date().toISOString();j.status='dispatching';await persist();
      // Download the exact validated bytes, not an unverified second response.
      j.downloadId=await chrome.downloads.download({url:dataURL,filename:j.filename,conflictAction:'uniquify',saveAs:false});
      j.status='downloading';await persist();
      const [d]=await chrome.downloads.search({id:j.downloadId});if(d)settle(j,d);await persist();
    });
  } catch(e) {
    await locked(async()=>{
      const {p,j}=jobById(id);if(!j || ['pending','cancelled','complete'].includes(j.status))return;
      j.status=p.paused?'pending':'failed';j.error=e.name==='AbortError'?'Image request paused or timed out; retry when ready.':e.message;await persist();
    });
  } finally {clearTimeout(timeout);}
}

// Reconcile every worker wake, including a wake after idle termination.
void ready.then(()=>pump()).catch(e=>console.error('Startup failed:',e));
