'use strict';

const { app, BrowserWindow, dialog, ipcMain, protocol, net } = require('electron');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { Readable } = require('node:stream');
const { mediaExtension, mediaFilePath, staticFilePath } = require('./paths.cjs');

protocol.registerSchemesAsPrivileged([{
  scheme: 'vf',
  privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true },
}]);

let win;
const transfers = new Map();
let draftQueue = Promise.resolve();
const MAX_CHUNK = 4 * 1024 * 1024;
const MAX_PROJECT = 20 * 1024 * 1024;

function userPaths() {
  const root = app.getPath('userData');
  return {
    media: path.join(root, 'media'),
    staging: path.join(root, 'staging'),
    draft: path.join(root, 'last-project.json'),
  };
}

function checkCaller(event) {
  const url = event.senderFrame?.url ?? '';
  if (!win || event.sender.id !== win.webContents.id || !url.startsWith('vf://desktop/'))
    throw new Error('Unauthorized renderer');
}

function validProject(project) {
  if (!project || typeof project !== 'object' || !Array.isArray(project.layers) ||
      !Number.isFinite(project.fps)) throw new Error('Invalid VideoJSON project');
  const content = JSON.stringify(project, null, 2);
  if (Buffer.byteLength(content) > MAX_PROJECT) throw new Error('VideoJSON too large');
  return content;
}

async function atomicSave(destination, content) {
  await fsp.mkdir(path.dirname(destination), { recursive: true });
  const temporary = destination + '.' + randomUUID() + '.part';
  try {
    await fsp.writeFile(temporary, content, { encoding: 'utf8', flag: 'wx' });
    await fsp.rename(temporary, destination);
  } finally {
    await fsp.rm(temporary, { force: true }).catch(() => {});
  }
}

function mediaMime(fileName) {
  const ext = path.extname(fileName).toLowerCase();
  return {
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.m4v': 'video/mp4',
    '.webm': 'video/webm', '.mkv': 'video/x-matroska',
    '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4',
    '.aac': 'audio/aac', '.flac': 'audio/flac', '.ogg': 'audio/ogg',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.webp': 'image/webp', '.gif': 'image/gif',
  }[ext] ?? 'application/octet-stream';
}

async function serveMedia(fileName, request) {
  const filePath = mediaFilePath(userPaths().media, fileName);
  const stat = await fsp.stat(filePath);
  if (!stat.isFile() || !stat.size) return new Response('Not found', { status: 404 });
  const total = stat.size;
  const range = request.headers.get('range');
  let start = 0, end = total - 1, status = 200;
  if (range) {
    const match = /^bytes=(\d+)-(\d*)$/.exec(range);
    if (!match) return new Response(null, { status: 416 });
    start = Number(match[1]);
    end = match[2] ? Number(match[2]) : end;
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) ||
        start >= total || start > end) {
      return new Response(null, {
        status: 416, headers: { 'Content-Range': 'bytes */' + total },
      });
    }
    end = Math.min(end, total - 1);
    status = 206;
  }
  const headers = {
    'Content-Type': mediaMime(fileName),
    'Accept-Ranges': 'bytes',
    'Content-Length': String(status === 206 ? end - start + 1 : total),
    'Access-Control-Allow-Origin': '*',
  };
  if (status === 206) headers['Content-Range'] = 'bytes ' + start + '-' + end + '/' + total;
  if (request.method === 'HEAD') return new Response(null, { status, headers });
  return new Response(
    Readable.toWeb(fs.createReadStream(filePath, { start, end })),
    { status, headers }
  );
}

async function startLocalProtocol() {
  protocol.handle('vf', async (request) => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'desktop' || !['GET', 'HEAD'].includes(request.method)) {
        return new Response('Not found', { status: 404 });
      }
      const pathname = decodeURIComponent(url.pathname);
      if (pathname.startsWith('/media/'))
        return await serveMedia(pathname.slice('/media/'.length), request);
      const bundledFile = staticFilePath(path.join(__dirname, '..', 'dist'), pathname);
      return net.fetch(pathToFileURL(bundledFile).href);
    } catch (error) {
      console.error('Local resource error', error?.message);
      return new Response('Not found', { status: 404 });
    }
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 960, minHeight: 600,
    title: 'VideoFlow Original Desktop Test',
    backgroundColor: '#151515',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', (event) => event.preventDefault());
  win.on('closed', () => { win = null; });
  win.loadURL('vf://desktop/index.html');
}

function installProjectHandlers() {
  ipcMain.handle('vf:load-draft', async (event) => {
    checkCaller(event);
    try {
      const data = JSON.parse(await fsp.readFile(userPaths().draft, 'utf8'));
      validProject(data);
      return data;
    } catch (error) {
      if (error.code !== 'ENOENT') console.warn('Draft not loaded', error?.message);
      return null;
    }
  });
  ipcMain.handle('vf:save-draft', async (event, data) => {
    checkCaller(event);
    const serialized = validProject(data);
    draftQueue = draftQueue.catch(() => {}).then(() => atomicSave(userPaths().draft, serialized));
    return draftQueue;
  });
  ipcMain.handle('vf:save-project', async (event, data) => {
    checkCaller(event);
    const serialized = validProject(data);
    const result = await dialog.showSaveDialog(win, {
      title: 'Save VideoFlow JSON project',
      defaultPath: 'VideoFlow-project.json',
      filters: [{ name: 'JSON project', extensions: ['json'] }],
    });
    if (result.canceled || !result.filePath) return false;
    await atomicSave(result.filePath, serialized);
    draftQueue = draftQueue.catch(() => {}).then(() => atomicSave(userPaths().draft, serialized));
    await draftQueue;
    return true;
  });
}

function validSize(size) {
  if (!Number.isSafeInteger(size) || size <= 0) throw new Error('Invalid file size');
}

async function beginTransfer(kind, size, destination, fileName) {
  validSize(size);
  const id = randomUUID();
  const staging = userPaths().staging;
  await fsp.mkdir(staging, { recursive: true });
  const temp = path.join(staging, id + '.part');
  const file = await fsp.open(temp, 'wx');
  transfers.set(id, { kind, size, destination, fileName, temp, file, offset: 0 });
  return { id };
}

async function appendTransfer(packet, kind) {
  const t = transfers.get(packet?.id);
  if (!t || t.kind !== kind) throw new Error('Invalid transfer');
  if (packet?.offset !== t.offset || !Number.isSafeInteger(packet.offset))
    throw new Error('Chunk offset mismatch');
  const chunk = Buffer.from(packet.chunk ?? []);
  if (!chunk.length || chunk.length > MAX_CHUNK || t.offset + chunk.length > t.size)
    throw new Error('Invalid transfer chunk size');
  let written = 0;
  while (written < chunk.length) {
    const part = await t.file.write(chunk, written, chunk.length - written, t.offset + written);
    if (part.bytesWritten <= 0) throw new Error('Short write');
    written += part.bytesWritten;
  }
  t.offset += chunk.length;
  return t.offset;
}

async function finishTransfer(id, kind) {
  const t = transfers.get(id);
  if (!t || t.kind !== kind || t.offset !== t.size)
    throw new Error('Incomplete or invalid transfer');
  await t.file.sync();
  await t.file.close();
  transfers.delete(id);
  await fsp.mkdir(path.dirname(t.destination), { recursive: true });
  await fsp.rename(t.temp, t.destination);
  return t;
}

async function abortTransfer(id, kind) {
  const t = transfers.get(id);
  if (!t || t.kind !== kind) return;
  transfers.delete(id);
  await t.file.close().catch(() => {});
  await fsp.rm(t.temp, { force: true }).catch(() => {});
}

function installTransferHandlers() {
  ipcMain.handle('vf:begin-asset', async (event, meta) => {
    checkCaller(event);
    const ext = mediaExtension(meta?.name);
    const fileName = randomUUID() + ext;
    return beginTransfer('asset', meta.size, mediaFilePath(userPaths().media, fileName), fileName);
  });
  ipcMain.handle('vf:write-asset', async (event, data) => {
    checkCaller(event); return appendTransfer(data, 'asset');
  });
  ipcMain.handle('vf:finish-asset', async (event, id) => {
    checkCaller(event);
    const t = await finishTransfer(id, 'asset');
    return 'vf://desktop/media/' + t.fileName;
  });
  ipcMain.handle('vf:abort-asset', async (event, id) => {
    checkCaller(event); return abortTransfer(id, 'asset');
  });
  ipcMain.handle('vf:begin-export', async (event, meta) => {
    checkCaller(event);
    validSize(meta?.size);
    const result = await dialog.showSaveDialog(win, {
      title: 'Save rendered MP4', defaultPath: 'VideoFlow-render.mp4',
      filters: [{ name: 'MP4 video', extensions: ['mp4'] }],
    });
    if (result.canceled || !result.filePath) return null;
    return beginTransfer('export', meta.size, result.filePath, path.basename(result.filePath));
  });
  ipcMain.handle('vf:write-export', async (event, data) => {
    checkCaller(event); return appendTransfer(data, 'export');
  });
  ipcMain.handle('vf:finish-export', async (event, id) => {
    checkCaller(event);
    const t = await finishTransfer(id, 'export');
    await dialog.showMessageBox(win, {
      type: 'info', title: 'VideoFlow MP4 saved', message: 'Video rendered and saved.',
      detail: t.destination,
    });
    return t.destination;
  });
  ipcMain.handle('vf:abort-export', async (event, id) => {
    checkCaller(event); return abortTransfer(id, 'export');
  });
}

app.whenReady().then(async () => {
  try {
    await startLocalProtocol();
    installProjectHandlers();
    installTransferHandlers();
    if (process.argv.includes('--self-test')) {
      await fsp.access(path.join(__dirname, '..', 'dist', 'index.html'));
      console.log('Original VideoFlow packaged web assets present');
      app.exit(0);
      return;
    }
    createWindow();
  } catch (error) {
    console.error('Desktop startup failed', error);
    app.exit(1);
  }
});
app.on('window-all-closed', () => app.quit());
