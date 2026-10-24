from ai_hq.config import Settings
from ai_hq.db import Database
from ai_hq.models import Agent

def test_doctor_preserves_real_execution_evidence_without_authentication_calls(tmp_path, monkeypatch):
    from ai_hq import doctor
    from ai_hq.agents import AgentRegistry
    db=Database(tmp_path/'hq.sqlite3');db.init()
    timestamp='2026-10-24T11:30:00+00:00'
    with db.Session.begin() as session:
        for name in ('codex','claude'):
            session.add(Agent(id=name,status={'authentication':'verified_by_execution','last_live_success_at':timestamp,'last_live_role':'review'}))
    db.close()
    monkeypatch.setattr(doctor.shutil,'which',lambda name:None)
    monkeypatch.setattr(AgentRegistry,'probe',lambda self,authenticate=False:{name:{'name':name,'available':True,'reason':'Help checked','authentication':'not_checked'} for name in ('codex','claude')})
    report=doctor.inspect(Settings(data_dir=tmp_path))
    assert next(item for item in report['checks'] if item['name']=='Last real provider execution')['status']=='PASS'
    assert report['agents']['codex']['authentication']=='verified_by_execution'
    assert timestamp in report['agents']['claude']['reason']
