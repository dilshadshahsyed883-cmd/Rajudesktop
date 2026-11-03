'use strict';
const path = require('node:path');
const ALLOWED_MEDIA_EXTENSIONS = new Set([
  '.mp4', '.mov', '.m4v', '.webm', '.mkv',
  '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg',
  '.jpg', '.jpeg', '.png', '.webp', '.gif'
]);
const ID_NAME = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.[a-z0-9]+$/;
function mediaExtension(fileName) {
  if (typeof fileName !== 'string' || !fileName || fileName.length > 300)
    throw new Error('Invalid media filename');
  const ext = path.extname(fileName).toLowerCase();
  if (!ALLOWED_MEDIA_EXTENSIONS.has(ext)) throw new Error('Unsupported media type: ' + ext);
  return ext;
}
function mediaFilePath(directory, fileName) {
  if (typeof fileName !== 'string' || !ID_NAME.test(fileName))
    throw new Error('Invalid media identifier');
  mediaExtension(fileName);
  return path.join(directory, fileName);
}
function staticFilePath(directory, urlPath) {
  if (typeof urlPath !== 'string' || !urlPath.startsWith('/') || urlPath.startsWith('//'))
    throw new Error('Invalid asset URL');
  const relative = urlPath === '/' ? 'index.html' : urlPath.slice(1);
  if (relative.includes('\0') || relative.includes('\\')) throw new Error('Invalid asset path');
  const root = path.resolve(directory);
  const resolved = path.resolve(root, relative);
  if (!resolved.startsWith(root + path.sep)) throw new Error('Asset outside bundle');
  return resolved;
}
module.exports = { mediaExtension, mediaFilePath, staticFilePath };
