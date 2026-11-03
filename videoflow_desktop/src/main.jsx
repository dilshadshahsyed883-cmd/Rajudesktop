import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { VideoEditor } from '@videoflow/react-video-editor';
import '@videoflow/react-video-editor/style.css';

const BLANK_PROJECT = {
  name: '30-second VideoFlow test', width: 1280, height: 720,
  fps: 30, duration: 30, layers: []
};
const CHUNK_SIZE = 4 * 1024 * 1024;

// Use the unchanged official VideoEditor, not replacement panels or a custom editor.
function OriginalEditor() {
  const [initialVideo, setInitialVideo] = useState(null);
  const draftTimeout = useRef(null);

  useEffect(() => {
    let active = true;
    window.vfDesktop.loadDraft()
      .then((saved) => { if (active) setInitialVideo(saved ?? BLANK_PROJECT); })
      .catch(() => { if (active) setInitialVideo(BLANK_PROJECT); });
    return () => {
      active = false;
      if (draftTimeout.current) clearTimeout(draftTimeout.current);
    };
  }, []);

  const onUpload = useCallback(async (file) => {
    const session = await window.vfDesktop.beginAsset({ name: file.name, size: file.size, type: file.type });
    try {
      for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
        const chunk = new Uint8Array(
          await file.slice(offset, Math.min(file.size, offset + CHUNK_SIZE)).arrayBuffer()
        );
        await window.vfDesktop.writeAsset({ id: session.id, offset, chunk });
      }
      return await window.vfDesktop.finishAsset(session.id);
    } catch (error) {
      await window.vfDesktop.abortAsset(session.id).catch(() => {});
      throw error;
    }
  }, []);

  const onChange = useCallback((video) => {
    if (draftTimeout.current) clearTimeout(draftTimeout.current);
    draftTimeout.current = setTimeout(() => {
      window.vfDesktop.saveDraft(video).catch(console.error);
    }, 1200);
  }, []);

  const onSave = useCallback(async (video) => { await window.vfDesktop.saveProject(video); }, []);

  const onExportComplete = useCallback(async (result) => {
    // Keep VideoFlow's original export dialog and save the returned Blob using Windows Save As.
    if (!(result instanceof Blob)) {
      window.alert('VideoFlow export did not return an MP4 Blob.');
      return;
    }
    let session;
    try {
      session = await window.vfDesktop.beginExport({ size: result.size });
      if (!session) return;
      for (let offset = 0; offset < result.size; offset += CHUNK_SIZE) {
        const chunk = new Uint8Array(
          await result.slice(offset, Math.min(result.size, offset + CHUNK_SIZE)).arrayBuffer()
        );
        await window.vfDesktop.writeExport({ id: session.id, offset, chunk });
      }
      await window.vfDesktop.finishExport(session.id);
    } catch (error) {
      if (session) await window.vfDesktop.abortExport(session.id).catch(() => {});
      window.alert('MP4 save failed: ' + String(error?.message ?? error));
    }
  }, []);

  if (!initialVideo) return null;
  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <VideoEditor video={initialVideo} theme="dark" onUpload={onUpload}
        onChange={onChange} onSave={onSave} onExportComplete={onExportComplete} />
    </div>
  );
}
createRoot(document.getElementById('root')).render(<OriginalEditor />);
