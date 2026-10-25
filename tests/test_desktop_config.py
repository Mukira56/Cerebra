import json
import pytest
from ai_hq import config
from ai_hq.manage import status
from ai_hq.db import Database
from ai_hq.models import Project,Task

def test_installed_data_location_preserves_external_history(tmp_path,monkeypatch):
    program=tmp_path/'program';program.mkdir();data=tmp_path/'existing-data'
    (program/'desktop-settings.json').write_text(json.dumps({'app_id':'AIDevelopmentHQ','data_dir':str(data)}))
    monkeypatch.delenv('AIHQ_DATA_DIR',raising=False);monkeypatch.setattr(config,'ROOT',program)
    assert config.Settings().data_dir==data
    explicit=tmp_path/'override';monkeypatch.setenv('AIHQ_DATA_DIR',str(explicit))
    assert config.Settings().data_dir==explicit

def test_invalid_desktop_configuration_fails_closed(tmp_path,monkeypatch):
    monkeypatch.delenv('AIHQ_DATA_DIR',raising=False);monkeypatch.setattr(config,'ROOT',tmp_path)
    (tmp_path/'desktop-settings.json').write_text(json.dumps({'app_id':'OtherApp','data_dir':'relative'}))
    with pytest.raises(ValueError):config.Settings()

def test_tray_status_detects_active_work_without_starting_agents(tmp_path):
    settings=config.Settings(data_dir=tmp_path)
    db=Database(settings.db_path);db.init()
    with db.Session.begin() as session:
        project=Project(name='status fixture',path=str(tmp_path/'repo'),default_branch='main');session.add(project);session.flush()
        session.add(Task(project_id=project.id,description='Active status fixture',state='RUNNING'))
    db.close()
    result=status(settings)
    assert {key:result[key] for key in ('running','active_tasks','url')}=={'running':False,'active_tasks':1,'url':'http://127.0.0.1:8765'}
    assert [task['title'] for task in result['tasks']]==['Active status fixture']  # named in the close warning
