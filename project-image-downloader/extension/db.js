let connection;
function db() {
  return connection ||= new Promise((resolve,reject) => {
    const req=indexedDB.open('project-image-downloader',1);
    req.onupgradeneeded=()=>req.result.createObjectStore('state');
    req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
  });
}
export async function load() {
  const d=await db(); return new Promise((resolve,reject)=>{
    const req=d.transaction('state').objectStore('state').get('root');
    req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
  });
}
export async function save(state) {
  const d=await db(); return new Promise((resolve,reject)=>{
    const tx=d.transaction('state','readwrite'); tx.objectStore('state').put(state,'root');
    tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error); tx.onabort=()=>reject(tx.error || Error('Storage write aborted'));
  });
}
