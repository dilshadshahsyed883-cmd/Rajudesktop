import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
const source=await readFile(new URL('../extension/worker.js',import.meta.url),'utf8');
const coreSource=await readFile(new URL('../extension/core.js',import.meta.url),'utf8');
const image=await readFile(new URL('./fixtures/landscape.png',import.meta.url));
const second=await readFile(new URL('./fixtures/second.png',import.meta.url));
const tiny=await readFile(new URL('./fixtures/small.png',import.meta.url));
const tick=()=>new Promise(r=>setTimeout(r,5));
async function until(fn) {for(let i=0;i<400;i++){if(await fn())return;await tick();}throw Error('Condition timed out');}
function event() {const listeners=[];return {addListener:f=>listeners.push(f),emit:(...a)=>listeners.map(f=>f(...a)),listeners};}
function environment() {
  const env={disk:null,items:new Map(),nextId:0,fetchMode:'ok',fetchCalls:[],downloads:[],settings:[],alarms:[],tabs:[],consoleErrors:[]};
  env.chrome={
    runtime:{id:'test-extension',getURL:p=>'chrome-extension://test-extension/'+p,onMessage:event(),onStartup:event(),onInstalled:event()},
    downloads:{onChanged:event(),search:async q=>[...env.items.values()].filter(d=>q.id==null || d.id===q.id),download:async options=>{
      const id=++env.nextId;env.downloads.push(options);env.items.set(id,{id,filename:'/Downloads/'+options.filename,startTime:new Date().toISOString(),state:'in_progress',bytesReceived:0,totalBytes:100,paused:false});return id;
    },pause:async id=>{env.items.get(id).paused=true;},resume:async id=>{const d=env.items.get(id);d.paused=false;d.state='in_progress';},cancel:async id=>{const d=env.items.get(id);d.state='interrupted';d.error='USER_CANCELED';}},
    alarms:{create:async(...a)=>env.alarms.push(a),onAlarm:event()},sidePanel:{setPanelBehavior:async o=>env.settings.push(o)},
    tabs:{create:async options=>{const t={id:env.tabs.length+1,...options};env.tabs.push(t);return t;},query:async()=>env.tabs.slice(-1),onRemoved:event()},
    scripting:{executeScript:async()=>[]}
  };
  env.fetch=async(url,options)=>{
    env.fetchCalls.push(url);
    if(env.fetchMode==='hold')await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
    if(env.fetchMode==='error')return new Response('Forbidden',{status:403});
    if(url.includes('bad'))return new Response('<html>Login</html>');
    if(url.includes('small'))return new Response(tiny,{'headers':{'content-type':'image/png'}});
    return new Response(url.includes('second')?second:image,{'headers':{'content-type':'image/png'}});
  };
  env.restart=async()=>{
    // Keep durable database and Chrome download records, discard worker memory/listeners.
    for(const e of [env.chrome.runtime.onMessage,env.chrome.runtime.onStartup,env.chrome.runtime.onInstalled,env.chrome.downloads.onChanged,env.chrome.alarms.onAlarm,env.chrome.tabs.onRemoved])e.listeners.length=0;
    const context=vm.createContext({chrome:env.chrome,crypto:webcrypto,URL,Blob,Uint8Array,TextEncoder,AbortController,DOMException,structuredClone,setTimeout,clearTimeout,btoa,fetch:env.fetch,
      console:{error:(...a)=>env.consoleErrors.push(a.join(' '))},
      createImageBitmap:async blob=>{const b=Buffer.from(await blob.arrayBuffer());return {width:b.readUInt32BE(16),height:b.readUInt32BE(20),close(){}};},
      testLoad:async()=>structuredClone(env.disk),testSave:async state=>{env.disk=structuredClone(state);}
    });
    const core=new vm.SourceTextModule(coreSource,{context});await core.link(()=>{});await core.evaluate();
    const db=new vm.SourceTextModule('export const load=testLoad;export const save=testSave;',{context});await db.link(()=>{});await db.evaluate();
    const worker=new vm.SourceTextModule(source,{context});await worker.link(s=>s==='./core.js'?core:db);await worker.evaluate();
    await until(()=>env.disk && env.chrome.runtime.onMessage.listeners.length);
  };
  env.send=async(type,data={})=>new Promise(resolve=>{
    const listener=env.chrome.runtime.onMessage.listeners[0];
    listener({type,...data},{id:'test-extension',url:'chrome-extension://test-extension/panel.html',tab:{id:3}},resolve);
  });
  env.state=async()=> (await env.send('STATE')).state;
  env.complete=async id=>{const d=env.items.get(id);d.state='complete';d.endTime=new Date().toISOString();env.chrome.downloads.onChanged.emit({id,state:{current:'complete'}});};
  return env;
}
async function setup(qty=3) {
  const env=environment();await env.restart();const created=await env.send('CREATE',{name:'Tennis Video'});const projectId=created.id;
  assert.ok(created.ok);
  const rows=[{id:'row-a',query:'Sabalenka match 2026',prefix:'Sabalenka',qty,source:''}];
  assert.ok((await env.send('SAVE',{projectId,rows})).ok);
  return {env,projectId,rowId:'row-a'};
}
async function addSelected(env,projectId,rowId,url) {
  assert.ok((await env.send('ADD_URL',{projectId,rowId,url})).ok);
  const p=(await env.state()).projects.find(p=>p.id===projectId);const c=p.candidates.find(c=>c.url===url);
  await env.send('SELECT',{projectId,candidateId:c.id,selected:true});
}
test('worker confirms completion, exact bytes, reports and durable reopen',async()=>{
  const {env,projectId,rowId}=await setup(2);
  await addSelected(env,projectId,rowId,'https://images.example/photo.png');
  const queued=await env.send('ENQUEUE',{projectId,rightsConfirmed:true});assert.equal(queued.added,1);
  await until(()=>env.downloads.length===1);
  let p=(await env.state()).projects[0];assert.equal(p.jobs[0].status,'downloading');
  assert.match(env.downloads[0].filename,/Sabalenka 1\.png$/);assert.equal(env.downloads[0].conflictAction,'uniquify');
  const downloaded=Buffer.from(env.downloads[0].url.split(',')[1],'base64');assert.deepEqual(downloaded,image);
  assert.ok(!p.jobs.some(j=>j.status==='complete'));
  await env.complete(1);await until(async()=> (await env.state()).projects[0].jobs[0].status==='complete');
  await env.restart();p=(await env.state()).projects[0];assert.equal(p.jobs[0].status,'complete');
  assert.equal(p.rows[0].query,'Sabalenka match 2026');assert.equal(p.rows[0].prefix,'Sabalenka');
  await env.send('REPORT',{projectId,kind:'summary'});
  const text=decodeURIComponent(env.downloads.at(-1).url.split(',')[1]);assert.match(text,/Downloaded: 1 \/ 2/);assert.match(text,/Still required: 1/);
});
test('worker rejects HTML, below-quality images and HTTP errors without counting success',async()=>{
  const {env,projectId,rowId}=await setup();
  for(const name of ['bad','small'])await addSelected(env,projectId,rowId,`https://images.example/${name}.png`);
  await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(async()=> (await env.state()).projects[0].jobs.filter(j=>j.status==='failed').length===2);
  assert.equal(env.downloads.length,0);let p=(await env.state()).projects[0];
  assert.match(p.jobs[0].error,/not a supported/);assert.match(p.jobs[1].error,/below your quality/);
  env.fetchMode='error';await addSelected(env,projectId,rowId,'https://images.example/blocked.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(async()=> (await env.state()).projects[0].jobs.some(j=>j.error.includes('403')));assert.equal(env.downloads.length,0);
});
test('worker suppresses exact byte duplicates across different original URLs',async()=>{
  const {env,projectId,rowId}=await setup();
  await addSelected(env,projectId,rowId,'https://images.example/a.png');await addSelected(env,projectId,rowId,'https://images.example/same-bytes.png');
  await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(async()=> (await env.state()).projects[0].jobs.some(j=>j.status==='duplicate'));
  assert.equal(env.downloads.length,1);assert.equal((await env.state()).projects[0].counters.sabalenka,1);
});
test('pause aborts validation, resume continues; cancel keeps completed files',async()=>{
  const {env,projectId,rowId}=await setup();env.fetchMode='hold';
  await addSelected(env,projectId,rowId,'https://images.example/a.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(()=>env.fetchCalls.length>0);await env.send('PAUSE',{projectId});
  await until(async()=> (await env.state()).projects[0].jobs[0].status==='pending');assert.equal(env.downloads.length,0);
  env.fetchMode='ok';await env.send('RESUME',{projectId});await until(()=>env.downloads.length===1);
  await env.complete(1);await until(async()=> (await env.state()).projects[0].jobs[0].status==='complete');
  await addSelected(env,projectId,rowId,'https://images.example/second.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});await until(()=>env.downloads.length===2);
  await env.send('CANCEL',{projectId});const p=(await env.state()).projects[0];assert.equal(p.jobs[0].status,'complete');assert.equal(p.jobs[1].status,'cancelled');
});
test('failed job retries do not reuse reserved filenames or overwrite files',async()=>{
  const {env,projectId,rowId}=await setup();await addSelected(env,projectId,rowId,'https://images.example/photo.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(()=>env.downloads.length===1);env.items.get(1).state='interrupted';env.items.get(1).error='NETWORK_FAILED';
  await env.send('STATE');assert.equal((await env.state()).projects[0].jobs[0].status,'failed');
  await env.send('RETRY',{projectId});await until(()=>env.downloads.length===2);assert.match(env.downloads[1].filename,/Sabalenka 2\.png$/);
});
test('restart reconciles a completed Chrome download that missed its event',async()=>{
  const {env,projectId,rowId}=await setup();await addSelected(env,projectId,rowId,'https://images.example/photo.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(()=>env.downloads.length===1);await env.send('STATE');env.items.get(1).state='complete';await env.restart();
  assert.equal((await env.state()).projects[0].jobs[0].status,'complete');assert.equal(env.downloads.length,1);
});
test('search creates an encoded direct URL and failed edits are atomic',async()=>{
  const {env,projectId,rowId}=await setup();await env.send('SEARCH',{projectId,rowId});assert.match(env.tabs[0].url,/tbm=isch/);
  assert.equal(new URL(env.tabs[0].url).searchParams.get('q'),'Sabalenka match 2026');
  const failed=await env.send('SAVE',{projectId,name:'Changed',rows:[{id:rowId,query:'',prefix:'x',qty:0}]});assert.equal(failed.ok,false);
  const p=(await env.state()).projects[0];assert.equal(p.name,'Tennis Video');assert.equal(p.rows[0].prefix,'Sabalenka');
});
test('Getty preview candidates cannot be selected or queued',async()=>{
  const {env,projectId,rowId}=await setup();await addSelected(env,projectId,rowId,'https://media.gettyimages.com/id/123/photo.jpg');
  const result=await env.send('ENQUEUE',{projectId,rightsConfirmed:true});assert.equal(result.added,0);assert.equal(env.downloads.length,0);
});
test('rapid pause/resume cannot dispatch the same pending job twice',async()=>{
  const {env,projectId,rowId}=await setup();env.fetchMode='hold';
  await addSelected(env,projectId,rowId,'https://images.example/photo.png');await env.send('ENQUEUE',{projectId,rightsConfirmed:true});
  await until(()=>env.fetchCalls.length>0);
  const pausing=env.send('PAUSE',{projectId});env.fetchMode='ok';const resuming=env.send('RESUME',{projectId});await Promise.all([pausing,resuming]);
  await until(()=>env.downloads.length===1);await tick();await tick();
  assert.equal(env.downloads.length,1);assert.equal((await env.state()).projects[0].jobs[0].status,'downloading');
});
test('Auto Download replaces failed originals, counts Chrome completion and stops at target',async()=>{
  const {env,projectId,rowId}=await setup(1);
  for(const name of ['bad','photo','second'])await env.send('ADD_URL',{projectId,rowId,url:`https://images.example/${name}.png`});
  const denied=await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:false});assert.equal(denied.ok,false);
  const start=await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});assert.equal(start.added,1);
  await until(()=>env.downloads.length===1);
  let p=(await env.state()).projects[0];assert.equal(p.jobs.length,2);assert.equal(p.jobs[0].status,'failed');assert.equal(p.jobs[1].auto,true);
  assert.ok(!p.jobs.some(j=>j.status==='complete'));
  await env.complete(1);await until(async()=>!(await env.state()).projects[0].autoRows[rowId].enabled);
  p=(await env.state()).projects[0];assert.equal(p.jobs.filter(j=>j.status==='complete').length,1);assert.equal(env.downloads.length,1);assert.equal(env.fetchCalls.filter(x=>x.includes('/bad.png')).length,1);
  assert.equal(p.autoRows[rowId].status,'Target complete');
});
test('Auto Download replaces duplicate bytes with the next distinct image',async()=>{
  const {env,projectId,rowId}=await setup(2);
  for(const name of ['photo','same-bytes','second'])await env.send('ADD_URL',{projectId,rowId,url:`https://images.example/${name}.png`});
  await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});
  await until(()=>env.downloads.length===2);let p=(await env.state()).projects[0];assert.equal(p.jobs.filter(j=>j.status==='duplicate').length,1);
  await env.complete(1);await env.complete(2);await until(async()=>!(await env.state()).projects[0].autoRows[rowId].enabled);
  p=(await env.state()).projects[0];assert.equal(p.jobs.filter(j=>j.status==='complete').length,2);assert.equal(env.downloads.length,2);
});
test('Auto stop cancels its work, preserves records and never replenishes it',async()=>{
  const {env,projectId,rowId}=await setup(2);env.fetchMode='hold';
  for(const name of ['photo','second'])await env.send('ADD_URL',{projectId,rowId,url:`https://images.example/${name}.png`});
  await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});await until(()=>env.fetchCalls.length>0);
  await env.send('AUTO_STOP',{projectId,rowId});await tick();await tick();const p=(await env.state()).projects[0];
  assert.equal(p.autoRows[rowId].enabled,false);assert.ok(p.jobs.every(j=>j.status==='cancelled'));assert.equal(env.downloads.length,0);
});
test('Auto mode displays Getty shortage without attempting preview downloads',async()=>{
  const {env,projectId,rowId}=await setup(1);await env.send('ADD_URL',{projectId,rowId,url:'https://media.gettyimages.com/id/123/photo.jpg'});
  const start=await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});assert.equal(start.added,0);assert.match(start.status,/Getty previews/);
  assert.equal(env.fetchCalls.length,0);assert.equal(env.downloads.length,0);
});
test('Auto collects available originals from the current source page',async()=>{
  const {env,projectId,rowId}=await setup(1);
  env.tabs.push({id:9,url:'https://www.google.com/search?tbm=isch&q=tennis'});
  env.chrome.scripting.executeScript=async options=>options.files?[]:[{result:{page:'https://www.google.com/search',source:'google',items:[{url:'https://images.example/photo.png',preview:'https://images.example/photo.png',sourcePage:'https://publisher.example/story',width:1600,height:900,original:true,source:'google',licenseRequired:false}]}}];
  const start=await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});assert.equal(start.added,1);await until(()=>env.downloads.length===1);
  const p=(await env.state()).projects[0];assert.equal(p.candidates.length,1);assert.equal(p.autoRows[rowId].tabId,9);assert.equal(p.jobs[0].sourcePage,'https://publisher.example/story');
});
test('Auto intent and target reservations survive a worker restart',async()=>{
  const {env,projectId,rowId}=await setup(1);await env.send('ADD_URL',{projectId,rowId,url:'https://images.example/photo.png'});
  await env.send('AUTO_START',{projectId,rowId,rightsConfirmed:true});await until(()=>env.downloads.length===1);await env.send('STATE');
  await env.restart();assert.equal((await env.state()).projects[0].autoRows[rowId].enabled,true);assert.equal(env.downloads.length,1);
  await env.complete(1);await until(async()=>!(await env.state()).projects[0].autoRows[rowId].enabled);assert.equal(env.downloads.length,1);
});
