"""Run the sending pause and the keyword check in a real browser, against isolated records only."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('customer_ui_fixture', root / 'scripts/check_customer_ui.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
setup = '''
from ai_hq.models import Book, Outbox, Prospect
with app.state.db.Session.begin() as session:
    for number in range(3):
        session.add(Prospect(id=f"gone{number}", name=f"Gone {number}", kind="dentists", city="Austin", state="Texas", status="lost"))
        session.add(Outbox(prospect_id=f"gone{number}", email=f"a@gone{number}.example", stage="bounced",
                           emails=[{"at": "2026-11-01T10:00:00+00:00", "subject": "s", "body": "b", "message_id": f"<{number}>"}]))
    listing = {"title": "Daily Gratitude Journal", "subtitle": "", "description": "A simple journal for a calm start to each day.", "price": 7.99, "checks": [],
               "keywords": ["journal", "daily gratitude journals", "self care diary prompts", "morning reflection notebook"]}
    session.add(Book(id="fixture-book", title="Daily Gratitude Journal", status="files_ready", trim="6x9", pages=120, extra={"kind": "low_content", "listing": listing}))
'''
fixture.SERVER = fixture.SERVER.replace('uvicorn.run(app,', setup + '\nuvicorn.run(app,')
original_run = fixture.subprocess.run


def run(args, **kwargs):
    args = [str(root / 'scripts/test_delivery_ui.cjs') if str(arg).endswith('test_customer_ui.cjs') else arg for arg in args]
    return original_run(args, **kwargs)


fixture.subprocess.run = run
if __name__ == '__main__':
    fixture.main()
