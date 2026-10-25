"""Run dashboard regression checks against isolated data with no supervisor worker or live agents."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
SERVER = '''
import os
from pathlib import Path
import uvicorn
from ai_hq.api import create_app
from ai_hq.config import Settings
from ai_hq import business
root=Path(os.environ["CEREBRA_UI_DATA"])
app=create_app(Settings(data_dir=root,port=int(os.environ["CEREBRA_UI_PORT"])),bootstrap_key=os.environ.pop("CEREBRA_UI_KEY"),start_worker=False)
with app.state.db.Session.begin() as session: business.save(session,str(root/"business-outputs"))
uvicorn.run(app,host="127.0.0.1",port=int(os.environ["CEREBRA_UI_PORT"]),access_log=False,log_level="warning")
'''

def main():
    shots=ROOT/"work/release-090-ui"; shots.mkdir(parents=True,exist_ok=True)
    node=Path(os.environ.get("CEREBRA_NODE",str(Path.home()/".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")))
    playwright=node.parent.parent/"node_modules/playwright-core"
    with tempfile.TemporaryDirectory(prefix="cerebra-ui-") as directory:
        with socket.socket() as probe: probe.bind(("127.0.0.1",0)); port=probe.getsockname()[1]
        key=secrets.token_urlsafe(24)
        env={**os.environ,"CEREBRA_UI_DATA":directory,"CEREBRA_UI_PORT":str(port),"CEREBRA_UI_KEY":key,"PYTHONDONTWRITEBYTECODE":"1"}
        with (shots/"server.log").open("w",encoding="utf-8") as log:
            process=subprocess.Popen([sys.executable,"-c",SERVER],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for _ in range(120):
                    if process.poll() is not None: raise RuntimeError("UI server exited; see "+str(shots/"server.log"))
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/health",timeout=1): break
                    except OSError: time.sleep(.5)
                else: raise RuntimeError("UI server did not start")
                ui_env={**os.environ,"AIHQ_PLAYWRIGHT":str(playwright),"AIHQ_URL":f"http://127.0.0.1:{port}/#key={key}","AIHQ_SHOTS":str(shots)}
                result=subprocess.run([str(node),str(ROOT/"scripts/test_dashboard.cjs")],cwd=ROOT,env=ui_env,capture_output=True,text=True,encoding="utf-8",timeout=360)
                (shots/"result.txt").write_text(result.stdout+result.stderr,encoding="utf-8")
                print(result.stdout+result.stderr,flush=True)
                if result.returncode: raise SystemExit(result.returncode)
            finally:
                process.terminate(); process.wait(timeout=20)

if __name__=="__main__": main()
