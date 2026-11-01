"""Low-content book collections for every age group (docs/ETSY_AMAZON_PLAN.md, phase 4).

For each age group: two kinds of low-content book that sell steadily to (or for) that age in the US, each an original
design drawn by code (ai_hq/interiors.py), a cover in the group's own palette and pattern (ai_hq/covers.py), a short
encouraging line at the foot of every page written for that age, and a complete listing: title, subtitle, description,
7 keywords and price, checked against KDP's limits. Nothing is copied from other sellers: the kinds of book are generic
(a reading log, a draw-and-write journal), and every design, line and listing here is Cerebra's own.

The quotes and listings were written for Cerebra with an AI assistant; the owner may edit any of them before upload.
KDP has no publishing API and doesn't allow bots in its account, so the upload stays the owner's two minutes a book.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from . import books, covers, interiors, notebooks
from .models import Book

GROUPS = {
    "kids": {
        "label": "Kids (4–8)", "palette": "sky", "motif": "dots",
        "quotes": ["TODAY I WILL TRY SOMETHING NEW", "MISTAKES HELP MY BRAIN GROW", "I CAN DRAW MY OWN ADVENTURE", "KIND WORDS MAKE THE DAY BRIGHTER",
                   "EVERY PICTURE TELLS MY STORY", "I LEARN A LITTLE MORE EACH DAY", "SHARING MAKES TWO PEOPLE HAPPY", "MY IDEAS ARE WORTH WRITING DOWN"],
        "books": [
            {"style": "draw_write", "trim": "8.5x11", "pages": 100, "price": 8.99,
             "title": "Draw and Write Journal for Kids", "subtitle": "Picture Box and Handwriting Lines with a Dashed Middle Line, Ages 4 to 8, 100 Pages",
             "why": "Parents and teachers buy them all year for early writing practice",
             "what": "A big, easy journal where kids draw a picture at the top of each page and write about it on the lines below.",
             "features": ["A large picture box on every page", "Handwriting lines with a dashed middle line to guide letter size"],
             "keywords": ["kindergarten writing journal", "draw and write notebook", "primary composition notebook", "story journal for kids",
                          "handwriting practice for kids", "first grade journal", "picture story notebook"]},
            {"style": "gratitude", "trim": "6x9", "pages": 100, "price": 7.99,
             "title": "My Gratitude Journal for Kids", "subtitle": "A Happy Daily Journal to Notice the Good Things, Ages 4 to 8",
             "why": "Gratitude journals for children are a steady gift and school-counselor favorite",
             "what": "A simple daily page that helps children notice what went well and look forward to tomorrow.",
             "features": ["Three short prompts every day: grateful for, something good, tomorrow", "Extra lines for anything else"],
             "keywords": ["gratitude journal for kids", "kids daily journal", "mindfulness for children", "happy journal for girls",
                          "happy journal for boys", "kindness journal", "feelings journal for kids"]},
        ],
    },
    "tweens": {
        "label": "Tweens (9–12)", "palette": "terracotta", "motif": "waves",
        "quotes": ["SMALL STEPS STILL MOVE ME FORWARD", "I GET TO DECIDE WHO I AM BECOMING", "BEING CURIOUS IS A SUPERPOWER", "A GOOD FRIEND IS WORTH THE EFFORT",
                   "HARD THINGS GET EASIER WITH PRACTICE", "I NOTICE THE GOOD THINGS TODAY", "IT'S OKAY TO ASK FOR HELP", "EVERY BOOK OPENS A NEW DOOR"],
        "books": [
            {"style": "reading", "trim": "6x9", "pages": 100, "price": 7.99,
             "title": "Reading Log for Kids Ages 9 to 12", "subtitle": "Track Every Book: Date, Title, Author, Pages and Rating",
             "why": "Schools ask for reading logs, so parents buy them every term",
             "what": "A reading log that turns every finished book into a small win.",
             "features": ["A clear table on every page: date, title, author, pages and rating", "Room for dozens of books"],
             "keywords": ["reading log for kids", "book tracker for kids", "summer reading log", "reading journal for kids",
                          "school reading record", "book log for students", "middle grade reading journal"]},
            {"style": "gratitude", "trim": "6x9", "pages": 110, "price": 7.99,
             "title": "Gratitude Journal for Tweens", "subtitle": "Daily Prompts to Notice the Good, Ages 9 to 12",
             "why": "Tween journals sell as birthday and holiday gifts",
             "what": "A daily journal with three quick prompts that builds a calm, positive habit.",
             "features": ["Three prompts every day", "Extra lines for thoughts, plans and ideas"],
             "keywords": ["gratitude journal for tweens", "journal for girls 10-12", "journal for boys 10-12", "daily journal for kids",
                          "positive thinking journal", "self esteem journal for kids", "gift for tween girl"]},
        ],
    },
    "teens": {
        "label": "Teens (13–17)", "palette": "charcoal", "motif": "checks",
        "quotes": ["PLAN THE WEEK, THEN LIVE IT", "PROGRESS OVER PERFECT", "WRITE IT DOWN SO YOUR MIND CAN REST", "ONE PAGE AT A TIME",
                   "YOUR PACE IS STILL A PACE", "TODAY COUNTS, EVEN THE QUIET PARTS", "IDEAS GROW WHEN YOU GIVE THEM SPACE", "REST IS PART OF THE WORK"],
        "books": [
            {"style": "dot", "trim": "6x9", "pages": 120, "price": 7.99,
             "title": "Dot Grid Journal for Teens", "subtitle": "Bullet Journal Notebook with 5 mm Dots, 120 Pages",
             "why": "Bullet journaling stays popular with teens for school and hobbies",
             "what": "A dot grid notebook for planning, lettering, sketching and lists, with a short line of encouragement on each page.",
             "features": ["5 mm dot grid on every page", "Works for planners, trackers, notes and doodles"],
             "keywords": ["dot grid journal for teens", "bullet journal notebook", "dotted notebook", "teen girl gifts",
                          "teen boy gifts", "dot journal for school", "bujo notebook"]},
            {"style": "weekly", "trim": "8.5x11", "pages": 110, "price": 9.99,
             "title": "Undated Weekly Planner for Teens", "subtitle": "Plan School, Activities and Goals, Start Any Week, Big 8.5 x 11 Pages",
             "why": "Undated planners sell all year because they never go out of date",
             "what": "A weekly planner with a box for each day and a notes box, ready to start any week of the year.",
             "features": ["Monday to Sunday on one page, plus notes", "Undated: start any time"],
             "keywords": ["undated planner for teens", "student weekly planner", "homework planner", "school planner for teens",
                          "weekly organizer", "academic planner undated", "high school planner"]},
        ],
    },
    "young_adults": {
        "label": "Young adults (18–25)", "palette": "blush", "motif": "bars",
        "quotes": ["BUILD THE HABIT, NOT THE PRESSURE", "STRONGER THAN LAST WEEK", "SHOW UP, EVEN FOR TEN MINUTES", "TRAIN HARD, REST WELL, REPEAT",
                   "THE PLAN IS YOURS TO CHANGE", "SMALL WINS STACK UP", "CONSISTENT BEATS INTENSE", "TODAY'S EFFORT IS TOMORROW'S EASY"],
        "books": [
            {"style": "workout", "trim": "6x9", "pages": 120, "price": 7.99,
             "title": "Workout Log Book", "subtitle": "Gym Journal to Track Exercises, Sets, Reps and Weight, 120 Pages",
             "why": "Fitness logs spike every January and sell steadily all year",
             "what": "A simple gym log to record every session and see your progress.",
             "features": ["A table on every page: date, exercise, sets, reps and weight", "Fits in a gym bag (6 x 9 in)"],
             "keywords": ["workout log book", "gym journal for men", "gym journal for women", "fitness tracker notebook",
                          "weight lifting log", "exercise journal", "strength training log"]},
            {"style": "college", "trim": "6x9", "pages": 120, "price": 7.99,
             "title": "College Ruled Notebook for Students", "subtitle": "Lined Journal with an Encouraging Line on Every Page, 120 Pages",
             "why": "Lined notebooks are the steadiest seller in low-content books",
             "what": "A clean college-ruled notebook for classes, notes and journaling.",
             "features": ["College-ruled lines (9/32 in)", "A short encouraging line at the foot of each page"],
             "keywords": ["college ruled notebook", "lined journal", "notebook for college students", "class notes notebook",
                          "simple lined journal", "writing notebook", "journal for young adults"]},
        ],
    },
    "adults": {
        "label": "Adults", "palette": "navy", "motif": "rules",
        "quotes": ["GOOD RECORDS MAKE TAX TIME CALMER", "EVERY MILE WRITTEN DOWN COUNTS", "A CHAPTER A DAY ADDS UP", "READ WHAT MAKES YOU WONDER",
                   "KEEP NOTES, KEEP GOING", "ORDER ON PAPER, CALM IN THE DAY", "STORIES ARE BETTER SHARED", "FINISH THE PAGE, THEN THE COFFEE"],
        "books": [
            {"style": "mileage", "trim": "6x9", "pages": 120, "price": 7.99,
             "title": "Mileage Log Book for Taxes", "subtitle": "Vehicle Mileage Tracker for Business and Self-Employed, 120 Pages",
             "why": "Small-business owners and drivers buy one every tax year",
             "what": "A mileage log with the columns a business-mileage record needs: date, odometer start and end, miles and purpose.",
             "features": ["A clear table on every page", "Room for hundreds of trips"],
             "keywords": ["mileage log book", "vehicle mileage tracker", "business mileage log", "mileage book for taxes",
                          "auto mileage record", "self employed tax log", "car mileage journal"]},
            {"style": "reading", "trim": "6x9", "pages": 120, "price": 7.99,
             "title": "Reading Journal for Book Lovers", "subtitle": "Book Log to Track Titles, Authors, Pages and Ratings, 120 Pages",
             "why": "Reading journals are a favorite gift for readers and book clubs",
             "what": "A reading log for every book you finish, to remember what you loved.",
             "features": ["Date, title, author, pages and rating on every row", "Room for a few hundred books"],
             "keywords": ["reading journal for book lovers", "book log", "reading tracker", "book club journal",
                          "gifts for readers", "book review journal", "reading record book"]},
        ],
    },
    "seniors": {
        "label": "Seniors (65+)", "palette": "forest", "motif": "double",
        "quotes": ["EACH DAY IS WORTH WRITING DOWN", "A STEADY HABIT IS A HEALTHY HABIT", "SHARE THESE NOTES WITH YOUR DOCTOR", "YOUR STORIES MATTER",
                   "TAKE IT SLOW AND ENJOY THE VIEW", "GRATITUDE MAKES ORDINARY DAYS FULL", "WRITE IT BIG, READ IT EASY", "EVERY MORNING IS A GOOD PLACE TO START"],
        "books": [
            {"style": "blood_pressure", "trim": "8.5x11", "pages": 110, "price": 8.99,
             "title": "Blood Pressure Log Book", "subtitle": "Daily Record of Systolic, Diastolic and Pulse, Big 8.5 x 11 Pages",
             "why": "Doctors ask patients to track it, and a full log is bought again",
             "what": "A blood pressure log with big pages and roomy rows, to bring to every doctor's visit.",
             "features": ["Date, time, systolic, diastolic, pulse and notes on every row", "Big 8.5 x 11 in pages"],
             "keywords": ["blood pressure log book", "blood pressure journal", "bp tracker", "health log for seniors",
                          "blood pressure record book", "heart rate log", "daily health journal"]},
            {"style": "large_print", "trim": "8.5x11", "pages": 100, "price": 8.99,
             "title": "Large Print Lined Journal for Seniors", "subtitle": "Wide-Ruled Notebook with Half-Inch Lines and Big 8.5 x 11 Pages",
             "why": "Large-print journals serve an underserved, growing audience",
             "what": "A notebook with half-inch lines and dark rules that are easy to see and write on.",
             "features": ["Half-inch lines, darker than usual", "Big 8.5 x 11 in pages"],
             "keywords": ["large print journal", "journal for seniors", "wide ruled notebook", "big lined notebook",
                          "notebook for elderly", "low vision notebook", "memory journal for seniors"]},
        ],
    },
}
AI_QUESTION = ("Pages and cover: No, both are drawn by code. The page quotes and the listing text came with Cerebra and were written with an AI "
               "assistant: answer KDP's AI question for text as it's worded when you upload (Yes, unless you've rewritten them yourself).")


def listing(group, spec):
    """The complete KDP listing for one book: nothing left to fill in."""
    label = GROUPS[group]["label"]
    description = "\n".join([spec["what"], "", "Inside:", *[f"- {item}" for item in spec["features"]],
                             f"- A short encouraging line at the foot of every page, written for {label.lower().split(' (')[0]}",
                             f"- {spec['pages']} pages, {spec['trim'].replace('x', ' x ')} in paperback, white paper", "",
                             "A thoughtful gift, and a simple habit worth keeping."])
    made = {"title": spec["title"], "subtitle": spec["subtitle"], "description": description, "keywords": list(spec["keywords"]), "price": spec["price"]}
    made["checks"] = notebooks.check(made)
    return made


def overview(session):
    made = {row.title: row.id for row in session.scalars(select(Book)).all()}
    return [{"key": key, "label": group["label"], "palette": group["palette"], "motif": group["motif"], "quotes": group["quotes"],
             "books": [{"title": spec["title"], "subtitle": spec["subtitle"], "style": spec["style"], "style_label": interiors.STYLES[spec["style"]][0],
                        "trim": spec["trim"], "pages": spec["pages"], "price": spec["price"], "why": spec["why"], "book_id": made.get(spec["title"], "")}
                       for spec in group["books"]]} for key, group in GROUPS.items()]


def make(session, folder: Path, group=None, limit=None):
    """Make every book of the group (or of all groups) that isn't made yet: interior, cover, listing, and a Book ready to upload."""
    if group is not None and group not in GROUPS:
        raise ValueError("Unknown age group")
    existing = {row.title for row in session.scalars(select(Book)).all()}
    made = []
    folder.mkdir(parents=True, exist_ok=True)
    for key, info in GROUPS.items():
        if group and key != group:
            continue
        for spec in info["books"]:
            if spec["title"] in existing or (limit is not None and len(made) >= limit):
                continue
            data, built = interiors.build(spec["style"], spec["trim"], spec["pages"], quotes=info["quotes"])
            name = f"{key}-{spec['style']}-{spec['trim']}-{built['pages']}p"
            (folder / f"{name}.pdf").write_bytes(data)
            cover = covers.save(folder, name, title=spec["title"], subtitle=spec["subtitle"], trim=spec["trim"], pages=built["pages"],
                                palette=info["palette"], motif=info["motif"])
            text = listing(key, spec)
            royalty = books.print_royalty(spec["price"], built["pages"], spec["trim"])
            tip = ""
            if spec["price"] < books.PRINT_RATE_HIGH_FROM:
                higher = books.print_royalty(books.PRINT_RATE_HIGH_FROM, built["pages"], spec["trim"])["royalty"]
                tip = (f"At ${books.PRINT_RATE_HIGH_FROM:.2f} KDP pays 60% instead of 50%: you'd earn ${higher:.2f} a copy instead of "
                       f"${royalty['royalty']:.2f}. Check what similar books cost before choosing.")
            row = Book(title=spec["title"], subtitle=spec["subtitle"], pen_name="", status="files_ready", formats=["paperback"], trim=spec["trim"],
                       paper="white", pages=built["pages"], words=0, prices={"paperback": spec["price"]},
                       extra={"kind": "low_content", "theme": f"{spec['title']} ({info['label']})", "interior": f"{name}.pdf", "cover": cover["file"],
                              "cover_palette": info["palette"], "style": spec["style"], "age_group": key, "listing": text,
                              "royalty": royalty["royalty"], "price_tip": tip, "ai_question": AI_QUESTION})
            session.add(row)
            session.flush()
            made.append({"id": row.id, "title": row.title, "group": info["label"]})
    return made
