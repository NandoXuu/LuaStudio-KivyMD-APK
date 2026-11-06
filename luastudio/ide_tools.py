# -*- coding: utf-8 -*-
"""Ferramentas puras da IDE: abas, backups, templates, plugins e edicao de linhas.
Independente de Kivy para poder ser testado e usado no desktop ou Android.
"""
import json, os, re, shutil, time, zipfile
from datetime import datetime

PROJECT_TEMPLATES = {
    '2d': {'main.lua': '-- Projeto 2D\ncreate.label = { Text = "Olá, mundo!", Position = {20, 20} }\n'},
    '3d': {'main.lua': '-- Projeto 3D\nEnv3D.set({ Ambient = 0.35, SunIntensity = 0.85 })\ncreate.part = { Shape = "cube", Position = {0, 0, 0}, Size = {1, 1, 1}, Color = "#4aa3ff" }\n'},
    'platformer': {'main.lua': '-- Plataforma: movimento e pulo\nlocal speed = 5\nfunction app.onupdate(dt)\n  -- Atualize o jogador usando dt\nend\n'},
    'top-down': {'main.lua': '-- Top-down\nlocal speed = 4\nfunction app.onupdate(dt)\n  -- Movimento em X/Z\nend\n'},
}

class TabManager:
    """Abas simples com documento ativo, alteracoes e caminhos."""
    def __init__(self): self.tabs=[]; self.active=-1
    def open(self, path, text=''):
        path=os.path.abspath(path) if path else None
        for i,t in enumerate(self.tabs):
            if t['path']==path and path is not None: self.active=i; return i
        self.tabs.append({'path':path,'text':text,'saved_text':text,'dirty':False})
        self.active=len(self.tabs)-1; return self.active
    def update(self, text):
        if self.active<0: return
        t=self.tabs[self.active]; t['text']=text; t['dirty']=text!=t['saved_text']
    def mark_saved(self, path=None):
        if self.active<0:return
        t=self.tabs[self.active]
        if path:t['path']=os.path.abspath(path)
        t['saved_text']=t['text']; t['dirty']=False
    def close(self, index=None):
        index=self.active if index is None else index
        if 0<=index<len(self.tabs):
            self.tabs.pop(index)
            self.active=min(index,len(self.tabs)-1)
            return True
        return False
    def current(self): return self.tabs[self.active] if 0<=self.active<len(self.tabs) else None

class VersionStore:
    """Backups rotativos e snapshots datados para um arquivo."""
    def __init__(self, root, keep=20): self.root=root; self.keep=max(1,int(keep))
    def snapshot(self, path, content=None):
        if content is None:
            with open(path,'r',encoding='utf-8') as f: content=f.read()
        folder=os.path.join(self.root,'.luastudio','history'); os.makedirs(folder,exist_ok=True)
        stamp=datetime.utcnow().strftime('%Y%m%d-%H%M%S-%f')
        name=os.path.basename(path)+'.'+stamp+'.bak'; dest=os.path.join(folder,name)
        with open(dest,'w',encoding='utf-8') as f:f.write(content)
        files=sorted(os.path.join(folder,n) for n in os.listdir(folder) if n.startswith(os.path.basename(path)+'.') and n.endswith('.bak'))
        for old in files[:-self.keep]:
            try:os.remove(old)
            except OSError:pass
        return dest
    def restore_list(self, path):
        folder=os.path.join(self.root,'.luastudio','history')
        if not os.path.isdir(folder):return []
        prefix=os.path.basename(path)+'.'
        return [os.path.join(folder,n) for n in sorted(os.listdir(folder)) if n.startswith(prefix) and n.endswith('.bak')]

class ProjectConfig:
    FILE='.luastudio-project.json'
    def __init__(self, project_root, defaults=None):
        self.root=project_root; self.values=dict(defaults or {})
        self.path=os.path.join(project_root,self.FILE)
        try:
            with open(self.path,encoding='utf-8') as f:
                data=json.load(f)
            if isinstance(data,dict):self.values.update(data)
        except (OSError,ValueError):pass
    def save(self):
        os.makedirs(self.root,exist_ok=True)
        tmp=self.path+'.tmp'
        with open(tmp,'w',encoding='utf-8') as f:json.dump(self.values,f,indent=2,ensure_ascii=False)
        os.replace(tmp,self.path)
    def set(self,key,value):self.values[key]=value
    def get(self,key,default=None):return self.values.get(key,default)
    def export(self,path):
        with open(path,'w',encoding='utf-8') as f:json.dump(self.values,f,indent=2,ensure_ascii=False)
    def import_file(self,path):
        with open(path,encoding='utf-8') as f:data=json.load(f)
        if not isinstance(data,dict):raise ValueError('A configuração precisa ser um objeto JSON.')
        self.values.update(data); self.save(); return len(data)

def create_template(root, template):
    key=template.lower().replace('_','-')
    if key not in PROJECT_TEMPLATES: raise ValueError('Template desconhecido: '+template)
    os.makedirs(root,exist_ok=True); created=[]
    for name,content in PROJECT_TEMPLATES[key].items():
        path=os.path.join(root,name)
        if not os.path.exists(path):
            with open(path,'w',encoding='utf-8') as f:f.write(content)
        created.append(path)
    ProjectConfig(root,{'template':key}).save()
    return created

def color_literal(value):
    """Devolve RGB hex normalizado para cores #RGB/#RRGGBB, ou None."""
    if not isinstance(value,str):return None
    s=value.strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',s):return None
    if len(s)==4:s='#'+''.join(c*2 for c in s[1:])
    return s.lower()

def edit_line(text, line, action, target=None):
    lines=text.splitlines(True); idx=max(0,min(len(lines)-1,int(line))) if lines else 0
    if action=='duplicate': lines.insert(idx+1,lines[idx])
    elif action=='delete': lines.pop(idx)
    elif action=='move-up' and idx>0: lines[idx-1],lines[idx]=lines[idx],lines[idx-1]
    elif action=='move-down' and idx+1<len(lines): lines[idx+1],lines[idx]=lines[idx],lines[idx+1]
    elif action=='goto': return ''.join(lines),sum(len(x) for x in lines[:idx])
    elif action=='replace' and target is not None: return text.replace(str(target[0]),str(target[1])),None
    else: raise ValueError('Ação de linha inválida')
    return ''.join(lines),None

class PluginRegistry:
    """Registro local de plugins/extension hooks; nao executa codigo externo automaticamente."""
    def __init__(self):self.plugins={}; self.hooks={}
    def register(self,name,enabled=True,**hooks):
        self.plugins[name]={'enabled':bool(enabled),'hooks':hooks}
        for hook,fn in hooks.items():self.hooks.setdefault(hook,[]).append((name,fn))
    def set_enabled(self,name,enabled):
        if name not in self.plugins:raise KeyError(name)
        self.plugins[name]['enabled']=bool(enabled)
    def run_hook(self,hook,*args,**kwargs):
        out=[]
        for name,fn in list(self.hooks.get(hook,[])):
            if self.plugins.get(name,{}).get('enabled'):
                out.append(fn(*args,**kwargs))
        return out
    def list(self):return [{'name':n,'enabled':v['enabled'],'hooks':list(v['hooks'])} for n,v in self.plugins.items()]

class SceneHierarchy:
    """Adaptador generico para listas de objetos; muta apenas a lista fornecida."""
    def __init__(self, objects=None):self.objects=list(objects or [])
    @staticmethod
    def name(obj):
        if isinstance(obj,dict):return str(obj.get('Name',obj.get('name','')))
        return str(getattr(obj,'name',getattr(obj,'Name','')))
    def search(self,query):
        q=str(query).lower();return [o for o in self.objects if q in self.name(o).lower()]
    def rename(self,obj,new_name):
        if isinstance(obj,dict):obj['Name']=str(new_name)
        elif hasattr(obj,'name'):obj.name=str(new_name)
        else:setattr(obj,'Name',str(new_name))
    def delete(self,obj):
        try:self.objects.remove(obj);return True
        except ValueError:return False

SIGNATURES={
 'create.part':'create.part(properties)', 'create.model':'create.model(properties)',
 'create.light':'create.light(properties)', 'create.camera':'create.camera(properties)',
 'Env3D.set':'Env3D.set(properties)', 'app.onupdate':'app.onupdate(dt)',
 'Graphics.HDR.IsSupported':'Graphics.HDR.IsSupported() -> bool', 'Graphics.HDR.GetStatus':'Graphics.HDR.GetStatus() -> table',
 'Graphics.ColorCalibration.GetStatus':'Graphics.ColorCalibration.GetStatus() -> table',
 'Graphics.ColorCalibration.Player.CanAdjust':'Graphics.ColorCalibration.Player.CanAdjust(control) -> bool',
 'app.onstart':'app.onstart()', 'input.is_down':'input.is_down(key)',
 'input.pressed':'input.pressed(key)', 'input.released':'input.released(key)',
}
def signature_hint(source,cursor=None):
    before=source[:cursor] if cursor is not None else source
    m=re.search(r'([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\([^()]*$',before)
    return SIGNATURES.get(m.group(1)) if m else None
