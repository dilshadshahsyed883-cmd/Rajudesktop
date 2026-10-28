"""Windows desktop launcher for an independent image-only CapCut Combo animation editor."""
import json
import os
import secrets
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from animation_engine import (default_projects_dir,list_projects,load_project,image_clips,
                              harvest_animations,resource_is_available,make_plan,save,capcut_running)

BG='#17191f'; PANEL='#252932'; TEXT='#f1f2f7'; MUTED='#aaafbe'
CONFIG=Path.home()/'.autocapcut_animations_only.json'

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AutoCapCut — Animations Only (Images)')
        self.geometry('980x730');self.minsize(820,610);self.configure(bg=BG)
        try: self.settings=json.loads(CONFIG.read_text(encoding='utf8'))
        except (OSError,ValueError): self.settings={}
        self.root_dir=Path(self.settings.get('projects_root') or default_projects_dir())
        self.projects=[];self.catalog=[];self.clips=[];self.preview=[];self.preview_project=None;self.preview_catalog=[];self.preview_effect_id=None
        self.mode_var=tk.StringVar(value="single")
        self.project_var=tk.StringVar();self.effect_var=tk.StringVar();self.folder_var=tk.StringVar(value=str(self.root_dir))
        self.status_var=tk.StringVar(value='Read-only until Apply. Source videos and layers never modified.')
        self._styles();self._ui();self.refresh()

    def _styles(self):
        style=ttk.Style(self);style.theme_use('clam')
        style.configure('TFrame',background=BG)
        style.configure('TLabel',background=BG,foreground=TEXT,font=('Segoe UI',10))
        style.configure('TButton',background=PANEL,foreground=TEXT,padding=(12,8))
        style.map('TButton',background=[('active','#414754')])
        style.configure('TCombobox',fieldbackground=PANEL,background=PANEL,foreground=TEXT,padding=7)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=29)
        style.map('Treeview',background=[('selected','#4864a3')])
        style.configure('Treeview.Heading',background='#353a44',foreground=TEXT,font=('Segoe UI Semibold',9))

    def _ui(self):
        p=ttk.Frame(self,padding=16);p.pack(fill='both',expand=True)
        tk.Label(p,text='AutoCapCut · Animations Only',font=('Segoe UI Semibold',20),bg=BG,fg=TEXT,anchor='w').pack(fill='x')
        tk.Label(p,text='Only Combo → Trending animations already used on images in saved CapCut projects.',bg=BG,fg=MUTED,anchor='w').pack(fill='x',pady=(3,15))
        row=ttk.Frame(p);row.pack(fill='x')
        ttk.Button(row,text='Change projects folder',command=self.choose_folder).pack(side='right')
        tk.Label(row,textvariable=self.folder_var,bg=BG,fg=MUTED,anchor='w').pack(side='left',fill='x',expand=True)
        row=ttk.Frame(p);row.pack(fill='x',pady=9)
        ttk.Label(row,text='Target project').pack(side='left',padx=(0,8))
        self.project=ttk.Combobox(row,textvariable=self.project_var,state='readonly')
        self.project.pack(side='left',fill='x',expand=True)
        self.project.bind('<<ComboboxSelected>>',lambda e:self.refresh_clips())
        ttk.Button(row,text='Refresh projects & animations',command=self.refresh).pack(side='left',padx=(8,0))
        ttk.Label(p,text='Saved Combo animations (select one for Single; Ctrl/Shift to choose a Random subset)').pack(anchor='w',pady=(10,5))
        self.effects=ttk.Treeview(p,columns=('name','category','resource','available'),show='headings',height=6,selectmode='extended')
        for key,label,width in [('name','Animation',210),('category','Category',120),('resource','Native Resource ID',220),('available','Cache on this PC',140)]:
            self.effects.heading(key,text=label);self.effects.column(key,width=width,stretch=key in ('name','resource'))
        self.effects.pack(fill='x')
        self.effects.bind('<<TreeviewSelect>>',lambda e:self.invalidate())
        options=ttk.Frame(p);options.pack(fill='x',pady=(10,6))
        ttk.Label(options,text='Apply mode:').pack(side='left',padx=(0,8))
        for mode,label in [('single','Single'),('random_selected','Random selected'),('random_all','Random all available')]:
            ttk.Radiobutton(options,text=label,variable=self.mode_var,value=mode,command=self.invalidate).pack(side='left',padx=(0,14))
        ttk.Button(options,text='Randomize ALL images',command=self.randomize_all).pack(side='right')
        row=ttk.Frame(p);row.pack(fill='x',pady=(13,6))
        ttk.Label(row,text='Target images (multi-select with Ctrl/Shift)').pack(side='left')
        ttk.Button(row,text='Select all images',command=self.select_all).pack(side='right',padx=4)
        ttk.Button(row,text='Clear selection',command=self.clear_selection).pack(side='right',padx=4)
        self.images=ttk.Treeview(p,columns=('track','name','duration','animation'),show='headings',height=9,selectmode='extended')
        for key,label,width in [('track','Layer / Index',105),('name','Image filename',310),('duration','Duration',110),('animation','Already applied',260)]:
            self.images.heading(key,text=label);self.images.column(key,width=width,stretch=key in ('name','animation'))
        self.images.pack(fill='both',expand=True)
        self.images.bind('<<TreeviewSelect>>',lambda e:self.invalidate())
        row=ttk.Frame(p);row.pack(fill='x',pady=(12,5))
        ttk.Button(row,text='Preview & validate',command=self.validate).pack(side='left')
        ttk.Button(row,text='Open backups',command=self.open_backups).pack(side='left',padx=8)
        ttk.Button(row,text='Apply animations to selected images',command=self.apply).pack(side='right')
        self.log=tk.Text(p,bg=PANEL,fg=TEXT,height=5,wrap='word',relief='flat',font=('Consolas',9))
        self.log.pack(fill='x',pady=6)
        tk.Label(p,textvariable=self.status_var,bg=BG,fg='#bcd0ff',anchor='w',wraplength=920).pack(fill='x')

    def selected_project(self):
        return next((p for p in self.projects if p.name==self.project_var.get()),None)

    def choose_folder(self):
        v=filedialog.askdirectory(initialdir=str(self.root_dir) if self.root_dir.exists() else str(Path.home()))
        if v:
            self.root_dir=Path(v);self.folder_var.set(str(self.root_dir))
            try:CONFIG.write_text(json.dumps({'projects_root':str(self.root_dir)}),encoding='utf8')
            except OSError:pass
            self.refresh()

    def invalidate(self):
        self.preview=[];self.preview_project=None;self.preview_catalog=[];self.preview_effect_id=None

    def refresh(self):
        current=self.project_var.get()
        self.projects=list_projects(self.root_dir)
        self.project['values']=[p.name for p in self.projects]
        self.project_var.set(current if any(p.name==current for p in self.projects) else (self.projects[0].name if self.projects else ''))
        self.catalog=harvest_animations(self.root_dir,True)
        self.effects.delete(*self.effects.get_children())
        for e in self.catalog:
            self.effects.insert('', 'end', iid=e['effect_id'],values=(e['name'],e['category'],e['effect_id'],'Available' if resource_is_available(e) else 'Missing'))
        self.refresh_clips()
        self.status_var.set(f'{len(self.projects)} projects · {len(self.catalog)} used Trending Combo animations found. No video animations allowed.')

    def refresh_clips(self):
        self.images.delete(*self.images.get_children());self.clips=[];self.invalidate()
        p=self.selected_project()
        if not p:return
        try:
            obj,paths,warnings=load_project(p)
            self.clips=image_clips(obj)
            mats={m.get('id'):m for m in obj.get('materials',{}).get('material_animations',[]) if isinstance(m,dict)}
            for c in self.clips:
                seg=obj['tracks'][c['track_index']]['segments'][c['segment_index']]
                applied=[]
                for rid in seg.get('extra_material_refs') or []:
                    m=mats.get(rid) or {}
                    for a in m.get('animations') or []:
                        if a.get('type')=='group':applied.append(a.get('name','Unknown'))
                iid=f"{c['track_index']}:{c['segment_index']}"
                self.images.insert('','end',iid=iid,values=(f"{c['track_index']+1} / {c['segment_index']+1}",c['name'],f"{c['duration_us']/1000000:g}s",', '.join(applied) or 'None'))
            self._log(f'{len(self.clips)} images detected (all videos excluded). '+ ' '.join(warnings))
        except Exception as e:
            self._log(f'Project read failed: {e}')

    def select_all(self):
        self.images.selection_set(self.images.get_children());self.invalidate()

    def clear_selection(self):
        self.images.selection_remove(self.images.selection());self.invalidate()

    def randomize_all(self):
        """One-click random assignment across ALL photo clips, then preview."""
        self.mode_var.set('random_all')
        self.select_all()
        self.validate()

    def _log(self,text):
        self.log.delete('1.0','end');self.log.insert('end',text)

    def validate(self):
        p=self.selected_project()
        if p is None:
            messagebox.showwarning('Select project','Choose a CapCut draft folder.');return False
        selection=set(self.effects.selection())
        mode=self.mode_var.get()
        if mode=='single' and len(selection)!=1:
            messagebox.showwarning('Select animation','Select exactly one used animation for Single mode.');return False
        if mode=='random_selected' and not selection:
            messagebox.showwarning('Select animations','Use Ctrl/Shift to select animations to mix.');return False
        if mode=='random_all':
            permitted=[x for x in self.catalog if resource_is_available(x)]
        elif mode=='random_selected':
            permitted=[x for x in self.catalog if x['effect_id'] in selection and resource_is_available(x)]
        else:
            permitted=[x for x in self.catalog if x['effect_id'] in selection]
        if not permitted:
            messagebox.showwarning('No available animations','First save a Combo Trending animation on an image in CapCut; ensure its effect cache exists on this PC.');return False
        selected=[tuple(int(i) for i in x.split(':')) for x in self.images.get_children() if x in self.images.selection()]
        try:
            obj,_,warnings=load_project(p)
            effect_id=next(iter(selection)) if mode=='single' else None
            rows,extra=make_plan(obj,permitted,selected,effect_id,
                                 mode='single' if mode=='single' else 'random',seed=secrets.randbits(64))
        except Exception as e:
            messagebox.showerror('Validation failed',str(e));return False
        self.preview=rows;self.preview_project=p;self.preview_catalog=permitted;self.preview_effect_id=effect_id
        counts={k:sum(x['status']==k for x in rows) for k in ('Will Apply','Missing','Skipped')}
        shortened=sum(r.get('applied_duration_us',0) < r.get('native_duration_us',0) for r in rows if r['status']=='Will Apply')
        lines=[f"{r['status']}: {r.get('name','image')} → {r.get('animation','N/A')} | {r.get('reason','')}" for r in rows]
        if mode!='single':
            lines.insert(0,f"RANDOM PLAN · {len(permitted)} available saved animation(s) · fixed assignments until next Preview")
        if warnings or extra:
            lines.extend('Warning: '+w for w in warnings+extra)
        self._log('\n'.join(lines) or 'No image clips selected')
        self.status_var.set(f"Preview: {counts['Will Apply']} Will Apply, {counts['Missing']} Missing, {counts['Skipped']} Skipped; {shortened} fitted to image durations. Videos, timing, transitions, layers untouched.")
        return True

    def apply(self):
        # Use the exact random assignments already shown in Preview.
        if self.preview_project is None and not self.validate():return
        if not any(x['status']=='Will Apply' for x in self.preview):
            messagebox.showwarning('Nothing to apply','No compatible images selected. Refresh saved animation catalog or preview again.');return
        if capcut_running():
            messagebox.showerror('CapCut open','Close CapCut before applying.');return
        num=sum(r['status']=='Will Apply' for r in self.preview)
        shortened=sum(r.get('applied_duration_us',0)<r.get('native_duration_us',0) for r in self.preview if r['status']=='Will Apply')
        if not messagebox.askyesno('Apply native image-only animations?',
             f"Apply to {num} photo clips in {self.preview_project.name}?\n"
             f"{shortened} presets will be shortened to their image durations (CapCut visual behavior requires testing).\n\n"
             'Backups will be created. Videos, layers, timings, transitions and audio will not be modified.'):
            return
        try:
            result=save(self.preview_project,self.preview_catalog,self.preview_effect_id,self.preview)
        except Exception as e:
            messagebox.showerror('Apply failed',str(e));return
        self.status_var.set(f"Applied: {result['changed']} | Already matching: {result['already_matching']} | Backup: {result['backup_dir']}")
        messagebox.showinfo('Image-only animation result',f"Applied: {result['changed']}\nAlready matching: {result['already_matching']}\nBackup: {result['backup_dir']}\n\nReopen your duplicate project in CapCut to verify the shortened animations.")
        self.refresh_clips()

    def open_backups(self):
        p=self.selected_project()
        if not p:return
        directory=p/'.animations_only_backups'
        if not directory.exists():
            messagebox.showinfo('Backups','No animation backups for this project.');return
        try:
            if sys.platform=='win32':os.startfile(directory)
            else:messagebox.showinfo('Backups',str(directory))
        except OSError as e:
            messagebox.showerror('Backups',str(e))


if __name__=='__main__':
    App().mainloop()