'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { mediaExtension, mediaFilePath, staticFilePath } = require('../electron/paths.cjs');

const mediaDir = path.resolve('safe-media');
const distDir = path.resolve('dist-root');

test('video, audio and image files are accepted', () => {
  for (const name of ['clip.MP4', 'voice.wav', 'photo.JPEG', 'two.webm'])
    assert.ok(mediaExtension(name).startsWith('.'));
});
test('executables and untrusted extensions are rejected', () => {
  for (const name of ['evil.exe', 'code.js', 'unlisted', 'cmd.bat'])
    assert.throws(() => mediaExtension(name));
});
test('only generated UUID media routes can be resolved', () => {
  const id = '41234f08-8bb9-4143-bbac-ac7eb66c1a01.mp4';
  assert.equal(mediaFilePath(mediaDir, id), path.join(mediaDir, id));
  for (const name of ['../../etc/passwd', 'C:\\windows\\secret.mp4', 'raw.mp4', id + '/bad'])
    assert.throws(() => mediaFilePath(mediaDir, name));
});
test('bundled asset URLs cannot escape the dist directory', () => {
  assert.equal(staticFilePath(distDir, '/'), path.join(distDir, 'index.html'));
  assert.equal(staticFilePath(distDir, '/assets/app.js'), path.join(distDir, 'assets', 'app.js'));
  for (const route of ['/../outside', '/../../outside', '/a\\b', '//server/path'])
    assert.throws(() => staticFilePath(distDir, route));
});
