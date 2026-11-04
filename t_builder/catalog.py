"""T Builder catalog, durable move history and conservative project-aware cleanup."""
from pathlib import Path
import json
import os
from z_builder.core import Catalog as ZCatalog, stable_id, MEDIA_EXTS
from .timeline import keyword, used

class Catalog(ZCatalog):
    def __init__(self, db_path):
        super().__init__(db_path)
        with self._connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS roots(path TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE IF NOT EXISTS draft_roots(path TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE IF NOT EXISTS moves(path TEXT PRIMARY KEY, original TEXT, project TEXT, status TEXT)')

    def add_root(self, path):
        p=Path(path).resolve(strict=True)
        with self._connect() as c: c.execute('INSERT OR IGNORE INTO roots VALUES(?)',(str(p),))

    def roots(self):
        with self._connect() as c: return [r[0] for r in c.execute('SELECT path FROM roots ORDER BY path')]

    def remember_drafts(self, path):
        with self._connect() as c: c.execute('INSERT OR IGNORE INTO draft_roots VALUES(?)',(str(Path(path).resolve()),))

    def add_folder(self, folder):
        self.add_root(folder)
        return super().add_folder(folder)

    def assets(self, include_missing=True):
        result=super().assets(include_missing)
        for a in result:
            a['keyword']=keyword(a['path'])
            a['used']=used(a['path'])
        return result

    def move_selected(self, timeline, log=lambda s:None):
        # Preflight every destination before touching files. Never overwrite an existing used file.
        paths=list(dict.fromkeys(c.path for c in timeline.images+timeline.videos))
        mapping={}
        for source in paths:
            p=Path(source).resolve(strict=True)
            if used(p) or p.is_symlink(): raise ValueError(f'Unavailable source: {p}')
            dest=p.parent/'used'/p.name
            if dest.exists(): raise FileExistsError(f'Used destination exists; nothing overwritten: {dest}')
            mapping[source]=str(dest)
        for source,destination in mapping.items():
            p,dest=Path(source),Path(destination)
            dest.parent.mkdir(exist_ok=True)
            if dest.parent.is_symlink(): raise ValueError('Symlinked used folders are not allowed')
            # Log intent first so interruption is visible and no moved media becomes untracked.
            with self._connect() as c:
                c.execute('INSERT OR REPLACE INTO moves VALUES(?,?,?,?)',(destination,source,'','pending'))
            # Hardlink creation fails if destination exists, including on Windows. Same volume by construction.
            os.link(p,dest)
            p.unlink()
            log(f'Moved: {source} → {destination}')
            old=next((a for a in self.assets() if a['path']==source),None)
            new=self.add(dest)
            if old:
                self.update_tags(new,old['tags']);self.remove(old['id'])
            self.record_successful_export([destination])
            with self._connect() as c: c.execute("UPDATE moves SET status='moved' WHERE path=?",(destination,))
        for clip in timeline.images+timeline.videos: clip.path=mapping[clip.path]
        return mapping

    def mark_project(self, paths, folder):
        with self._connect() as c:
            c.executemany("UPDATE moves SET project=?,status='verified' WHERE path=?",[(str(folder),p) for p in paths])

    def cleanup_candidates(self, selected_root, drafts_roots):
        root=Path(selected_root).resolve(strict=True)
        if str(root) not in self.roots(): raise ValueError('Choose an imported library folder')
        with self._connect() as c:
            known=[r[0] for r in c.execute('SELECT path FROM draft_roots')]
            moved=[r[0] for r in c.execute('SELECT path FROM moves')]
        references=set()
        def walk(value):
            if isinstance(value,dict):
                for k,v in value.items():
                    if k in ('path','file','media_path') and isinstance(v,str) and v:
                        references.add(str(Path(v).resolve()).casefold())
                    walk(v)
            elif isinstance(value,list):
                for v in value: walk(v)
        # Every known draft root is scanned; unreadable/encrypted drafts block deletion.
        for location in dict.fromkeys(known+[str(p) for p in drafts_roots if p]):
            base=Path(location)
            if not base.exists():
                raise ValueError(f'Cannot inspect known CapCut project location: {base}. Cleanup blocked.')
            for p in base.rglob('draft_content.json'):
                try: walk(json.loads(p.read_text(encoding='utf-8-sig')))
                except Exception as exc: raise ValueError(f'Cannot verify project references in {p}; cleanup blocked: {exc}')
        eligible=[];protected=[]
        for name in moved:
            p=Path(name)
            if not p.is_file() or p.is_symlink() or p.parent.is_symlink(): continue
            resolved=p.resolve()
            if not resolved.is_relative_to(root) or p.parent.name.casefold()!='used': continue
            if str(resolved).casefold() in references: protected.append(str(p))
            else: eligible.append(str(p))
        return eligible,protected

    def cleanup(self, selected_root, paths, drafts_roots, confirmed=False):
        if not confirmed: raise ValueError('Explicit cleanup confirmation required')
        eligible,_=self.cleanup_candidates(selected_root,drafts_roots)
        if not set(paths).issubset(eligible): raise ValueError('Cleanup eligibility changed; review again')
        from send2trash import send2trash
        for name in paths:
            send2trash(name)
            self.remove(stable_id(name))
        return len(paths)

    def summary(self):
        rows=['T BUILDER MEDIA SUMMARY','Available excludes used/ and missing files.','']
        for a in self.assets():
            state='USED' if a['used'] else 'AVAILABLE' if a['exists'] else 'MISSING'
            rows.append(f"{a['filename']} | {a['kind']} | keyword={a['keyword']} | {state} | tags={a['tags']} | {a['path']}")
        return '\n'.join(rows)+'\n'
