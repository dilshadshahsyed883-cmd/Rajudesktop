'use strict';
const { contextBridge, ipcRenderer } = require('electron');
// Only these narrow, local operations are exposed; never expose Node.js or fs.
contextBridge.exposeInMainWorld('vfDesktop', {
  loadDraft: () => ipcRenderer.invoke('vf:load-draft'),
  saveDraft: (project) => ipcRenderer.invoke('vf:save-draft', project),
  saveProject: (project) => ipcRenderer.invoke('vf:save-project', project),
  beginAsset: (meta) => ipcRenderer.invoke('vf:begin-asset', meta),
  writeAsset: (chunk) => ipcRenderer.invoke('vf:write-asset', chunk),
  finishAsset: (id) => ipcRenderer.invoke('vf:finish-asset', id),
  abortAsset: (id) => ipcRenderer.invoke('vf:abort-asset', id),
  beginExport: (meta) => ipcRenderer.invoke('vf:begin-export', meta),
  writeExport: (chunk) => ipcRenderer.invoke('vf:write-export', chunk),
  finishExport: (id) => ipcRenderer.invoke('vf:finish-export', id),
  abortExport: (id) => ipcRenderer.invoke('vf:abort-export', id),
});
