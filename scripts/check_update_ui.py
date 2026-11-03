"""Exercise update controls against an isolated app; no real download or installer is run."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('customer_ui_fixture', root / 'scripts/check_customer_ui.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.SERVER = fixture.SERVER.replace('uvicorn.run(app,', '''app.state.updater._set(phase="ready", tag="v99.0.0", message="Fixture update ready")
uvicorn.run(app,''')
# Reuse the existing bounded server lifecycle and authentication harness, with a dedicated browser regression.
original_run = fixture.subprocess.run
def run(args, **kwargs):
    args = [str(root / 'scripts/test_update_ui.cjs') if str(arg).endswith('test_customer_ui.cjs') else arg for arg in args]
    return original_run(args, **kwargs)
fixture.subprocess.run = run
if __name__ == '__main__':
    fixture.main()
