"""Build a per-user Windows installer using installed runtimes and the OS C# compiler.

No SDK, installer builder, global pip install, or internet download is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import tomllib
from release_privacy import audit, copy_app, copy_dependencies

ROOT=Path(__file__).resolve().parent.parent
VERSION='0.74.39'
PUBLIC_DOCS={'ARCHITECTURE.md','SECURITY.md','USER_GUIDE.md','WINDOWS_INSTALLER.md'}

TRACE_MODULES=['ai_hq.api','ai_hq.manage','ai_hq.doctor','ai_hq.telemetry','ai_hq.gitops','ai_hq.agents','ai_hq.supervisor','ai_hq.processes',
    'uvicorn','uvicorn.main','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.lifespan.on','pytest','sqlite3']
TRACE=r'''
import importlib,json,sys
for name in sys.argv[1:]: importlib.import_module(name)
print(json.dumps(sorted({m.__file__ for m in list(sys.modules.values()) if getattr(m,"__file__",None) and m.__file__.endswith(".py")})))
'''

def precompile(stage,build):
    """Ship checked-hash bytecode for modules the app actually loads.

    The installed launcher sets PYTHONDONTWRITEBYTECODE, so without this every start recompiles
    FastAPI, Pydantic and SQLAlchemy from source on each start. Checked-hash pycs stay
    valid after extraction resets file times, and are ignored if a source file differs.
    """
    import importlib.util, py_compile
    env={key:value for key,value in os.environ.items() if key!='PYTHONPATH'}
    env.update(PYTHONDONTWRITEBYTECODE='1',AIHQ_DATA_DIR=str(build/'trace-data'))
    traced=json.loads(subprocess.run([str(stage/'runtime/python.exe'),'-X','utf8','-c',TRACE,*TRACE_MODULES],cwd=stage,env=env,
                                     capture_output=True,text=True,check=True).stdout)
    sources={Path(path).resolve() for path in traced}|{path.resolve() for path in (stage/'ai_hq').rglob('*.py')}
    for source in sorted(sources):
        if not source.is_relative_to(stage.resolve()): raise RuntimeError('Trace imported a module outside the payload: '+str(source))
        py_compile.compile(str(source),cfile=importlib.util.cache_from_source(str(source)),dfile=source.relative_to(stage.resolve()).as_posix(),doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    return len(sources)

def included_in_release(path,stage):
    parts=path.relative_to(stage).parts
    if path.suffix.lower()=='.pyo': return False
    if path.suffix.lower()=='.pyc' or '__pycache__' in parts:
        if not (path.suffix.lower()=='.pyc' and path.parent.name=='__pycache__'): return False
    if parts[0] in {'ai_hq','runtime'}: return True
    if parts[0]=='docs': return len(parts)==2 and parts[1] in PUBLIC_DOCS
    return len(parts)==1 and parts[0] in {'AIHQ.exe','Uninstall.exe','README.txt','THIRD-PARTY-NOTICES.txt','Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll','WEBVIEW2-LICENSE.txt','webview2-sdk.json','release-channel.json'}

def copy_tree(source, target, excluded=()):
    for path in source.rglob('*'):
        relative=path.relative_to(source)
        if any(part in excluded or part=='__pycache__' for part in relative.parts): continue
        if path.suffix.lower() in {'.pyc','.pyo','.pth'} or path.name.startswith('__editable__'): continue
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()): raise RuntimeError('Build inputs may not contain links: '+str(path))
        if path.is_file():
            destination=target/relative
            if destination.is_file() and destination.stat().st_size==path.stat().st_size and destination.stat().st_mtime_ns==path.stat().st_mtime_ns: continue
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)

def compile_program(compiler, source, output, resource=None, icon=None):
    native=ROOT/'packaging/windows'
    args=[str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+','/utf8output',f'/out:{output}',f'/win32manifest:{native/"app.manifest"}',
          '/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll','/r:System.IO.Compression.dll','/r:System.IO.Compression.FileSystem.dll']
    if resource: args.append(f'/resource:{resource},AIHQ.Payload.zip')
    if icon: args.append(f'/win32icon:{icon}')
    args.extend([str(native/'Common.cs'),str(native/source)])
    if source=='Launcher.cs':
        sdk=native/'webview2'
        args.extend([f'/r:{sdk/"Microsoft.Web.WebView2.Core.dll"}',f'/r:{sdk/"Microsoft.Web.WebView2.WinForms.dll"}',str(native/'Desktop.cs')])
    subprocess.run(args,check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build-dir',type=Path,default=ROOT/'work/windows-build')
    parser.add_argument('--update-repository',default='',help='Public GitHub owner/repository for this distributor edition')
    parser.add_argument('--no-update-channel',action='store_true',help='Build an edition that never looks for updates')
    args=parser.parse_args()
    if bool(args.update_repository)==args.no_update_channel:
        parser.error('Choose --update-repository owner/repository, or --no-update-channel: an installer without a channel can never update itself')
    if args.update_repository and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.update_repository):
        raise ValueError('Update channel must be a public owner/repository name')
    if os.name!='nt' or sys.version_info[:2]!=(3,13) or sys.maxsize<2**32: raise RuntimeError('Build with Windows x64 Python 3.13 and the tested project environment')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file(): raise RuntimeError('The Windows .NET Framework C# compiler is not available')
    build=args.build_dir.resolve();stage=build/'payload'
    if (stage/'data').exists() or (stage/'desktop-settings.json').exists(): raise RuntimeError('Build payload contains runtime data; use a new build directory')
    # Start from an empty payload so files dropped from the release (or stale pycs) cannot leak into it.
    if stage.exists(): raise RuntimeError('Use a new build directory; existing payloads are preserved')
    stage.mkdir(parents=True)
    args.output.mkdir(parents=True,exist_ok=True)
    base=Path(sys.base_prefix);runtime=stage/'runtime';runtime.mkdir(exist_ok=True)
    for name in ['python.exe','pythonw.exe','python3.dll','python313.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        shutil.copy2(base/name,runtime/name)
    print('Copying private Python runtime and tested dependencies...',flush=True)
    copy_tree(base/'Lib',runtime/'Lib',{'site-packages','test','idlelib','tkinter','turtledemo'})
    for path in (base/'DLLs').iterdir():
        if path.is_file() and path.suffix.lower() in {'.dll','.pyd'} and not path.name.startswith(('_test','_ctypes_test','_tkinter','tcl','tk')):
            (runtime/'DLLs').mkdir(exist_ok=True);shutil.copy2(path,runtime/'DLLs'/path.name)
    site=Path(sys.prefix)/'Lib/site-packages'
    # pip is not needed to run the app; nobody should install into the private runtime.
    project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
    packages=copy_dependencies(site,runtime/'Lib/site-packages',project['dependencies']+project['optional-dependencies']['dev'])
    (runtime/'python313._pth').write_text('Lib\nDLLs\nLib\\site-packages\n..\nimport site\n',encoding='utf-8')
    (runtime/'Lib/site-packages/sitecustomize.py').write_text("import sys\nfor stream in (sys.stdout,sys.stderr):\n    if stream is not None and hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8')\n",encoding='utf-8')
    copy_app(ROOT,stage)
    if args.update_repository:
        (stage/'release-channel.json').write_text(json.dumps({'repository':args.update_repository},indent=2),encoding='utf-8')
    (stage/'docs').mkdir(exist_ok=True)
    for name in PUBLIC_DOCS:shutil.copy2(ROOT/'docs'/name,stage/'docs'/name)
    shutil.copy2(ROOT/'docs/WINDOWS_INSTALLER.md',stage/'README.txt')
    (stage/'THIRD-PARTY-NOTICES.txt').write_text('Python runtime: runtime/LICENSE.txt\nThird-party package licenses and metadata are under runtime/Lib/site-packages/*.dist-info.\n\n'+'\n'.join(name+' '+version for name,version in packages)+'\n',encoding='utf-8')
    print('Precompiled '+str(precompile(stage,build))+' imported modules.',flush=True)
    print('Compiling native launcher and uninstaller...',flush=True)
    sdk=ROOT/'packaging/windows/webview2'
    metadata=json.loads((sdk/'sdk.json').read_text(encoding='utf-8'))
    for name in ['Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll']:
        if hashlib.sha256((sdk/name).read_bytes()).hexdigest()!=metadata['files'][name]: raise RuntimeError('WebView2 SDK integrity check failed: '+name)
        shutil.copy2(sdk/name,stage/name)
    shutil.copy2(sdk/'LICENSE.txt',stage/'WEBVIEW2-LICENSE.txt')
    shutil.copy2(sdk/'sdk.json',stage/'webview2-sdk.json')
    icon=build/'AIHQ.ico'
    subprocess.run([str(Path(os.environ['WINDIR'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-File',str(ROOT/'scripts/build_icon.ps1'),'-OutputPath',str(icon)],check=True)
    compile_program(compiler,'Launcher.cs',stage/'AIHQ.exe',icon=icon)
    compile_program(compiler,'Uninstaller.cs',stage/'Uninstall.exe',icon=icon)
    print('Auditing every customer payload file...',flush=True)
    files=audit(stage)
    if any(not included_in_release(stage/name,stage) for name in files): raise RuntimeError('Payload contains an uninventoried release file')
    (args.output/'customer-privacy-report.json').write_text(json.dumps({'version':VERSION,'passed':True,'files_checked':len(files),'checks':['Git-inventoried application files','Declared dependency closure','No databases, secrets, history or local settings','No known developer identity or paths outside explicit public release channel','Relative bytecode source paths'],'files':files},indent=2),encoding='utf-8')
    (stage/'release-files.json').write_text(json.dumps({'app_id':'AIDevelopmentHQ','version':VERSION,'files':files},indent=2),encoding='utf-8')
    print('Compressing '+str(len(files))+' files...',flush=True)
    payload=build/'payload.zip'
    with zipfile.ZipFile(payload,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in [*files,'release-files.json']:
            archive.write(stage/name,name)
    installer=args.output/f'Cerebra-Setup-{VERSION}-Windows-x64.exe'
    print('Embedding the offline application payload...',flush=True)
    compile_program(compiler,'Installer.cs',installer,resource=payload,icon=icon)
    digest=hashlib.file_digest(installer.open('rb'),'sha256').hexdigest()
    (args.output/(installer.name+'.sha256')).write_text(digest+'  '+installer.name+'\n',encoding='ascii')
    record={'version':VERSION,'installer':str(installer),'sha256':digest,'installer_bytes':installer.stat().st_size,'payload_files':len(files),'installed_bytes':sum((stage/name).stat().st_size for name in files),'python':sys.version.split()[0],'packages':packages,'signed':False}
    (build/'build-record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in record.items() if key!='packages'}),flush=True)

if __name__=='__main__': main()
