"""Exercise the real installer in isolated program/data directories, without live AI."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import HTTPError,URLError
import winreg

ROOT=Path(__file__).resolve().parent.parent
REGISTRY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDevelopmentHQ.InstallerTest'

def run(args,**kwargs):
    result=subprocess.run([str(arg) for arg in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=kwargs.pop('timeout',240),creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)
    if result.returncode: raise RuntimeError(str(args[0])+': '+result.stdout+'\n'+result.stderr)
    return result.stdout.strip()

MISSING_GIT=r'''
import json,os,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from ai_hq import toolpath
toolpath._registry_path=lambda:[];toolpath._git_folders=lambda:[]  # hide this laptop's Git completely
from ai_hq.api import create_app
from ai_hq.config import Settings
app=create_app(Settings(data_dir=Path(os.environ['AIHQ_DATA_DIR'])),bootstrap_key='KEY',start_worker=False)
with TestClient(app) as c:
    health=c.get('/health').json()['status']
    c.headers['X-CSRF-Token']=c.post('/api/session',json={'key':'KEY'}).json()['csrf_token']
    git=next(t for t in c.get('/api/tools').json() if t['id']=='git')
    folder=Path(tempfile.mkdtemp())
    refused=c.post('/api/projects',json={'name':'x','path':str(folder),'authorize':True,'test_commands':[]})
    print(json.dumps({'health':health,'git_listed_missing':git['installed'] is False,'project_refused':refused.status_code==400 and 'Required tools' in refused.json()['detail']}))
'''

PIPELINE_TEST=r'''
# The installed app ships no simulated agents. This test-only stand-in replaces the provider CLIs
# inside this one process, so the full pipeline runs with real Git and real pytest and no AI usage.
import json,secrets,subprocess,sys
from pathlib import Path
from fastapi.testclient import TestClient
from ai_hq.agents import AgentRegistry,AgentResult
from ai_hq.api import create_app
from ai_hq.config import Settings
class StandIn(AgentRegistry):
    def probe(self,authenticate=False): return {n:{'name':n,'available':True,'execution_allowed':True} for n in ('codex','claude')}
    def execute(self,name,request,cancel_event=None):
        if request.role=='implement': (Path(request.workdir)/'calculator.py').write_text('def add(a, b):\n    return a + b\n',encoding='utf-8')
        return AgentResult(True,json.dumps({'findings':[],'summary':'stand-in'}),[])
key=secrets.token_urlsafe(32)
app=create_app(Settings(),bootstrap_key=key,start_worker=False)
app.state.supervisor.registry=StandIn()
with TestClient(app) as c:
    r=c.post('/api/session',json={'key':key});r.raise_for_status();c.headers['X-CSRF-Token']=r.json()['csrf_token']
    project=c.post('/api/projects',json={'name':'Installer check','create_new':True,'authorize':True,'test_commands':[[sys.executable,'-m','pytest','-q','-p','no:cacheprovider']]});project.raise_for_status();project=project.json()
    root=Path(project['path'])
    (root/'calculator.py').write_text('def add(a, b):\n    return a - b\n',encoding='utf-8')
    (root/'test_calculator.py').write_text('from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_negative():\n    assert add(-2, -3) == -5\n',encoding='utf-8')
    (root/'.gitignore').write_text('__pycache__/\n',encoding='utf-8')
    for args in (['add','.'],['-c','user.name=T','-c','user.email=t@example.invalid','commit','-m','base']): subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True)
    c.post('/api/permissions',json={'enabled':True,'acknowledge_provider_usage':True,'acknowledge_residual_read_risk':True}).raise_for_status()
    task=c.post('/api/tasks',json={'project_id':project['id'],'description':'Fix calculator addition','allowed_paths':['calculator.py']});task.raise_for_status();task_id=task.json()['id']
    c.post('/api/tasks/'+task_id+'/approve-plan',json={}).raise_for_status()
    c.post('/api/tasks/'+task_id+'/start',json={}).raise_for_status()
    consent=next(a for a in c.get('/api/tasks/'+task_id).json()['approvals'] if a['kind']=='live_execution')
    c.post('/api/approvals/'+consent['id'],json={'approve':True}).raise_for_status()
    c.post('/api/tasks/'+task_id+'/start',json={}).raise_for_status()
    app.state.supervisor.run_until_idle()
    task=c.get('/api/tasks/'+task_id).json()
    assert task['state']=='AWAITING_APPROVAL',task
    assert task['results']['verified'] and task['reviews'] and all(t['passed'] for t in task['test_results'])
    assert [r['role'] for r in task['runs']]==['plan','implement','review']
    report=c.get('/api/reports/'+task_id).json();assert report['headline']=='Finished and waiting for you'
    print(json.dumps({'task_id':task_id,'state':task['state'],'tests':task['test_results'][0]['stdout'],'agents':'test stand-in (no AI usage)'}))
'''

def main():
    parser=argparse.ArgumentParser();parser.add_argument('installer',type=Path);parser.add_argument('--test-root',type=Path,default=ROOT/'work/install-test');args=parser.parse_args()
    target=args.test_root/'AI HQ';data=args.test_root/'retained-data'
    if target.exists():raise RuntimeError('A previous test directory exists; inspect it before repeating')
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,REGISTRY): raise RuntimeError('A previous installer test registration exists')
    except FileNotFoundError:pass
    with socket.socket() as probe:probe.bind(('127.0.0.1',18765))
    data.mkdir(parents=True,exist_ok=True);(data/'user-project.txt').write_text('Retain this user data',encoding='utf-8')
    # Git prerequisite detection, run for real: with the normal PATH and with a PATH that has no Git folder on it.
    system32=str(Path(os.environ['SystemRoot'])/'System32')
    found=json.loads(run([args.installer,'--check-git']))
    assert found['git'] and Path(found['git']).is_file(),found
    outside=json.loads(run([args.installer,'--check-git'],env={**os.environ,'PATH':system32}))
    assert outside['git'] and Path(outside['git']).is_file(),outside
    print('Setup finds working Git on PATH and outside PATH (registry/standard folder)...',flush=True)
    print('Installing the actual EXE into an isolated directory...',flush=True)
    run([args.installer,'--quiet','--dir',target,'--data',data,'--port','18765','--no-desktop','--test-registration'],timeout=360)
    manifest=json.loads((target/'aihq-install.json').read_text(encoding='utf-8'))
    assert manifest['data_dir']==str(data) and manifest['registry']==REGISTRY
    assert 'docs/progress.md' not in manifest['files'] and 'docs/environment-report.md' not in manifest['files']
    assert not (target/'data').exists() and not (target/'.env').exists()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,REGISTRY) as registry:assert winreg.QueryValueEx(registry,'InstallLocation')[0]==str(target)
    menu=Path(manifest['menu']);assert (menu/'Cerebra.lnk').is_file()
    python=target/'runtime/python.exe';launcher=target/'AIHQ.exe'
    env=os.environ.copy();env['PYTHONPATH']=r'C:\Users\ADMIN\AI-Development-HQ';env['PYTHONDONTWRITEBYTECODE']='1';env['AIHQ_DATA_DIR']=str(data)
    code="import ai_hq,fastapi,pydantic,sqlalchemy,pytest,httpx,json,sys;print(json.dumps({'file':ai_hq.__file__,'version':ai_hq.__version__,'path':sys.path}))"
    modules=json.loads(run([python,'-X','utf8','-c',code],cwd=target,env=env))
    assert Path(modules['file']).is_relative_to(target) and modules['version']=='0.55.0'
    assert r'C:\Users\ADMIN\AI-Development-HQ' not in modules['path']
    assert not any('__editable__' in p.name for p in target.rglob('*'))
    print('Private runtime imports application/dependencies without source Python...',flush=True)
    # A laptop without Git: the packaged app must still start and point to Required tools instead of crashing.
    nogit=MISSING_GIT.replace('KEY',secrets.token_urlsafe(32))
    missing=json.loads(run([python,'-X','utf8','-c',nogit],cwd=target,env={**env,'PATH':system32,'AIHQ_DATA_DIR':str(args.test_root/'no-git-data')}))
    assert missing=={'health':'ok','git_listed_missing':True,'project_refused':True},missing
    print('Packaged app starts without Git and explains how to install it...',flush=True)
    diagnostics=run([launcher,'--doctor'],cwd=target,timeout=180)
    assert 'FAIL' not in diagnostics,diagnostics
    started=False
    try:
        began=time.monotonic();run([launcher,'--start-no-browser'],cwd=target,timeout=120);started=True
        startup_seconds=round(time.monotonic()-began,2)
        with urlopen('http://127.0.0.1:18765/health',timeout=10) as response:health=json.load(response)
        assert health['version']=='0.55.0'
        with urlopen('http://127.0.0.1:18765/',timeout=10) as response:assert b'Cerebra' in response.read()
        try:urlopen('http://127.0.0.1:18765/api/overview',timeout=10);raise AssertionError('Unauthenticated API allowed')
        except HTTPError as error:assert error.code==401
        status=json.loads(run([launcher,'--status'],cwd=target));assert status['running'] and status['active_tasks']==0
        run([launcher,'--stop'],cwd=target);started=False
    finally:
        if started:run([launcher,'--stop'],cwd=target)
    print('Native launcher start, health, protected API and managed stop passed...',flush=True)
    run([launcher,'--desktop-smoke'],cwd=target,timeout=180)
    desktop=json.loads((data/'desktop-smoke.json').read_text(encoding='utf-8'))
    assert desktop.get('authenticated') and desktop.get('logo') and desktop.get('native') and desktop.get('system_view_connected'),desktop
    assert (data/'desktop-smoke.png').stat().st_size>10000
    assert not json.loads(run([launcher,'--status'],cwd=target))['running']
    print('Actual embedded desktop window authenticated, rendered, and closed without an external browser...',flush=True)
    proof=json.loads(run([python,'-X','utf8','-c',PIPELINE_TEST],cwd=target,env=env,timeout=360))
    print('Packaged pipeline (plan, code, real pytest, review, report) passed with a test stand-in agent...',flush=True)
    # Upgrade in place: recorded old program files are removed; an unknown file keeps only its backup folder.
    (target/'upgrade-note.txt').write_text('Unknown file present during upgrade',encoding='utf-8')
    run([args.installer,'--quiet','--dir',target,'--data',data,'--port','18765','--no-desktop','--test-registration'],timeout=360)
    backups=list(target.parent.glob(target.name+'.previous-*'))
    assert (target/'AIHQ.exe').is_file() and len(backups)==1,backups
    assert [p.relative_to(backups[0]).as_posix() for p in backups[0].rglob('*')]==['upgrade-note.txt']
    assert (target/'previous-install.txt').read_text(encoding='utf-8')==str(backups[0])
    print('Upgrade removed recorded old program files and kept the unknown file...',flush=True)
    (target/'keep-my-file.txt').write_text('Unknown user file must survive uninstall',encoding='utf-8')
    run([target/'Uninstall.exe','--quiet'],cwd=ROOT,timeout=180)
    deadline=time.monotonic()+30
    while (target/'AIHQ.exe').exists() and time.monotonic()<deadline:time.sleep(.2)
    assert not (target/'AIHQ.exe').exists() and not (target/'runtime/python.exe').exists()
    assert (target/'keep-my-file.txt').read_text()=='Unknown user file must survive uninstall'
    assert (data/'user-project.txt').read_text()=='Retain this user data'
    with sqlite3.connect(data/'hq.sqlite3') as db:assert db.execute('select state from tasks where id=?',(proof['task_id'],)).fetchone()[0]=='AWAITING_APPROVAL'
    assert not (menu/'Cerebra.lnk').exists()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,REGISTRY):raise AssertionError('Test uninstall registration was not removed')
    except FileNotFoundError:pass
    report={'installer':str(args.installer),'installer_sha256':hashlib.file_digest(args.installer.open('rb'),'sha256').hexdigest(),'version':health['version'],'private_runtime':True,'native_launch_stop':True,'startup_seconds':startup_seconds,'upgrade_cleanup':True,'embedded_desktop':desktop,'authentication_boundary':True,'pipeline':proof,'git_found_on_and_off_path':True,'starts_without_git':True,'registration_shortcuts':True,'uninstall':True,'database_retained':True,'unknown_user_file_retained':True,'live_provider_calls':False}
    (ROOT/'work/windows-build/installer-test-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
