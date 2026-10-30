# Build prompt: Cerebra Books (AI publishing for Amazon KDP)

Copy everything below the line into a new Claude Code session opened in this repository.

---

You are building a new, production-grade feature in Cerebra, the owner's local AI work app in this repository. It is a FastAPI and SQLAlchemy backend in `ai_hq/`, a single-page dashboard in `ai_hq/static/` (vanilla JS, no framework), and pytest tests in `tests/`. Before writing code, read `AGENTS.md`, `CLAUDE.md`, `docs/SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/FREELANCE_PLAN.md` and the last five entries of `docs/progress.md`. Then study how the existing modules are built, and build the same way: `ai_hq/freelance.py`, `ai_hq/money.py`, `ai_hq/products.py`, `ai_hq/payments.py`, `ai_hq/commerce.py`, `ai_hq/vault.py`, `ai_hq/business.py`. The other streams (freelancing, client work, products, marketing) stay exactly as they are. This adds a new one.

## What the owner wants

The owner wants a business of short nonfiction books (50 to 150 printed pages), each solving one specific problem for one kind of reader. The books are sold on Amazon through Kindle Direct Publishing (KDP), in the **US market (amazon.com) first**, as paperback, Kindle ebook and hardcover. The owner lives in Kenya and publishes under a pen name.

Build the whole workflow inside Cerebra, so that a book goes from "find a niche" to "files ready to upload" to "sales tracked", with the owner making the decisions. This is not a demo. Every screen must work on real data. Every file Cerebra produces must pass KDP's own previewer the first time. Nothing may be faked, estimated without saying so, or left as a placeholder.

## The hard rules (platform rules and law, not preferences)

1. **KDP has no publishing API, and Cerebra must not drive the KDP website with a bot.** Automating the KDP site risks the owner's account. Cerebra prepares a complete, validated upload package and a step-by-step upload checklist. The owner clicks Publish, including the "AI-generated content" disclosure, which Amazon requires for AI-generated text, images or translations. Show the disclosure answers Cerebra recommends for each book, from what was actually generated.
2. **KDP caps new titles at 3 a day per account** (Amazon told the Authors Guild; it can change). Store the cap as a setting, warn at it, and never plan launches that break it.
3. **No review manipulation.** Amazon bans reviews from family and close friends, reviews in exchange for anything, review swaps, and making a free copy conditional on a review.
   - Cerebra may keep a list of readers who **asked** for an advance copy and send them one with no review condition. Every message template must say a review is welcome but not required, and must ask them to disclose a free copy.
   - No feature may buy, trade or incentivize reviews.
4. **No scraping of Amazon pages.** Amazon's Conditions of Use forbid it. Market data comes from:
   - **Keepa API**, for sales rank history, price, and rating and review counts. It is paid, and the owner adds their own key in Business connections.
   - **Google Trends**, through the official Google Trends API (alpha) if the owner has access. Otherwise the owner pastes a Trends CSV export.
   - **Review text:** the owner pastes the 3-star reviews they copied. Cerebra never fetches them.
5. **Truthful nonfiction.** These books are in health, money, parenting and caregiving, so wrong facts can hurt a reader and break US consumer protection law.
   - Every factual claim the model writes goes into a claims list.
   - Claims about health, money, law or safety need a source the owner can open, or they are rewritten as general guidance.
   - No invented studies, statistics, quotes, credentials or case stories. A story the model made up is marked as illustrative in the text.
   - Health, finance and legal books get a plain-language disclaimer page.
6. **Original work.**
   - Covers follow genre conventions (layout, type style, colour mood) but never copy a specific book's cover, title or trade dress.
   - Text never reproduces passages from the reviews or competitor books the owner pasted. Those are analysed for gaps, not copied.
   - Run a check that no paragraph of a draft overlaps a pasted source by more than 8 consecutive words.
7. **Secrets** (Keepa, image and model API keys) go through `vault.protect` and are never returned by the API, logged or put in a prompt.

## The workflow to build (a new "Books" page, plus a section on the Overview)

### 1. Niche research
The owner types a broad area ("menopause sleep", "caring for aging parents", "budgeting on one income"). Cerebra helps narrow it to one reader and one problem, then scores each candidate niche from real data only:
- **Demand that lasts:** a 5-year Trends line (flat or rising scores well; a spike that fell is flagged as a fad).
- **Proof people buy:** the Best Sellers Rank of the top 10 to 20 competing books, from Keepa. Under 100,000 on amazon.com means it sells. Over 1,000,000 means it doesn't.
- **Competition:** how many competing books there are, their review counts and their age.
- **Price room:** typical paperback and Kindle prices.
- **Profit per paperback** at the planned price, from KDP's printing cost formula (below).

The score shows its inputs and reasons, like the freelance lead score does. A missing input says "not checked" and is never guessed.

### 2. Gap mining
The owner pastes reviews (3-star especially) from the top books, with the book's title. The model extracts what readers said was missing, confusing, too long or out of date. It groups these into 8 to 15 gaps, each with how many reviews mention it and two short paraphrases (not quotes). The owner can edit, merge or drop gaps.

### 3. Book plan
From the niche, the reader profile and the gaps, the model proposes:
- a title and subtitle, with 5 alternatives
- a promise (what the reader can do after reading)
- a 10 to 12 chapter outline, each chapter tied to the gaps it fixes
- a target length per chapter
- the tone and reading level

The owner edits and approves. Nothing is written before approval.

### 4. Writing
Chapter by chapter, with the approved outline, the voice settings and the previous chapters' summaries in context. That keeps the voice and facts consistent and avoids repetition.
- **Model:** the planner or implementer model profile the owner chooses in Models (they will pay for strong models: default to the best available Claude model for writing).
- **Front and back matter:** each chapter is saved as its own Markdown file in the book's folder, plus front matter (title page, copyright page with the pen name, disclaimer if needed, table of contents) and back matter (a short "about the author" for the pen name, and a polite request for an honest review, which Amazon allows).
- **Edit pass:** after each chapter, a separate pass:
  - removes AI tells (stock phrases such as "in today's fast-paced world", "delve", "tapestry", and repeated summaries)
  - shortens long sentences and checks reading level
  - fills the claims list
- **Owner review:** the owner reads and approves or asks for changes per chapter. Show word count, estimated pages and reading level as it goes.

### 5. Interior files (print and Kindle)
- **Paperback and hardcover interior PDF,** built to KDP's specifications:
  - trim size the owner picks (default 6 × 9 in)
  - margins by page count (gutter grows with pages), with no bleed for text books
  - all fonts embedded (ship an open-licence serif and sans font in the package, with their licences)
  - page numbers, running heads and chapters starting on a right-hand page
  - a page count that meets the minimum
- **Kindle EPUB 3:** a valid EPUB with a navigation document and reflowable text, made from the same Markdown.
- **Validation:** before declaring files ready, re-read the generated PDF (page size, page count, embedded fonts, nothing outside the margins) and the EPUB (structure). Report failures in plain words.

### 6. Covers
- **Artwork:** generated by the owner's image API (OpenAI images, already in `commerce.py`; add Ideogram as a second provider if the owner adds a key). Never ask the image model to draw the title.
- **Typography by Cerebra:** title, subtitle and pen name are set in real fonts, so text is always correct and sharp.
- **Paperback and hardcover:** one full-wrap PDF (back, spine, front) at the exact KDP size for the trim, page count and paper type. Spine width = page count × the paper's per-page thickness. No spine text below KDP's minimum page count. The back holds the description and a blank barcode area where KDP prints the barcode.
- **Kindle:** a front cover image at KDP's recommended size and ratio.
- **Style:** offer 3 cover directions the owner picks from, each following the genre's conventions without copying any book.

### 7. Listing
The model drafts for the owner to edit:
- the description, with KDP's allowed HTML, within the length limit
- the 7 keyword phrases
- 3 category suggestions with reasons
- the reading age, if relevant
- prices: paperback $12.99 to $16.99 by page count, Kindle $2.99 to $9.99 for the 70% royalty, and a $0.99 launch price option with its lower royalty shown

Show the royalty per sale for each format and marketplace.

### 8. Upload package and checklist
One folder per book holding:
- interior PDF, cover PDF, EPUB and Kindle cover image
- `listing.txt` with every field in KDP's order
- the recommended AI-disclosure answers
- a numbered checklist of the KDP upload screens

The owner opens it from the Books page. After they publish, they paste each format's ASIN and ISBN back into Cerebra.

### 9. Launch and series
- **Launch plan:** the 5-day $0.99 price, which niche communities to post in (written for each community's rules, owner posts by hand), and the advance-reader list from rule 3.
- **Series:** suggest the next book in the same niche, because Amazon shows a series author's books together.
- **Tracking:** in the publishing calendar, respect the daily cap.

### 10. Sales and money
KDP has no sales API.
- **Report import:** the owner downloads the KDP report (Excel or CSV, from Reports) and imports it. Cerebra matches rows to books by ASIN and ISBN and records royalties per book, format, marketplace and month into the Money ledger, in the report's currency, never converted silently.
- **Payments the owner must set up:** KDP pays a non-US author by bank transfer or check, and requires the US tax interview (W-8BEN). Add these to a "Start publishing" checklist.
- **Results:** feed the books into the "What works" view (`ai_hq/insights.py`): earnings per book, per niche and per month. Show whether a niche's books earn more over time.

## Numbers to encode
Put these in one constants module, with the KDP help page URL beside each value and the date checked. Verify each one against KDP's help pages (`kdp.amazon.com/help`) and the KDP pricing calculator while you build. Some third-party sources disagree, so the official page wins.
- **Printing cost (US, black ink):** fixed cost plus per-page cost, by page count and trim category.
- **Print royalty:** the current paperback tier(s) by list price. Sources report 60% at $9.99 and above and 50% below, so confirm.
- **Kindle royalty:** 70% between $2.99 and $9.99 minus delivery cost per MB; 35% otherwise.
- **Trim sizes, margins by page count, bleed rules and spine rules:** per-page thickness by paper type, and the minimum pages for spine text.
- **Limits:** description length, keyword slots, categories, minimum and maximum page counts per format, and the daily title cap.

## Engineering requirements (match the rest of Cerebra)
- **Data:**
  - New tables via `Base.metadata.create_all`, and never new columns on existing tables. Suggested tables: `book_niches`, `books`, `book_chapters`, `book_sales`.
  - Long text lives in files in the book's folder, not the database.
- **Model calls** go through the existing registry and model profiles. Tests use fixture models only and never call a real provider, Keepa, Google or an image API (simulate them with `httpx.MockTransport`, as `tests/test_autoapply.py` does).
- **PDF and EPUB generation:**
  - PDF: `reportlab` for building and `pypdf` for checking, pinned in `pyproject.toml` and `requirements.lock`, and bundled by `scripts/build_windows.py`.
  - EPUB: the standard library. No system dependencies, so it works on Windows, macOS and Linux.
- **Background work:** model writing runs in the background with progress, can be stopped and resumed, and never blocks the dashboard (the Overview polls every 3 seconds). Use the patterns in `freelance.Drafter`.
- **Model usage:** respect the owner's monthly spend cap for paid APIs, as `social.py` does, and show each book's model and image cost.
- **Security:** the job post rule applies to pasted reviews too. Pasted text is untrusted data inside prompts and is never followed as instructions.
- **UI:** a "Books" page under WORK, with these panels:
  - Niches
  - Books (a pipeline: researching, planned, writing, files ready, published)
  - a book detail view (chapters, claims, files, listing, checklist)
  - Sales
  - Start publishing

  Add a "Books" card to the Overview with what needs the owner. Every state has a clear empty state and next step. It must work at phone width and pass `scripts/test_dashboard.cjs` (add the page to it).
- **Tests:** for every rule above, including:
  - spine width and cover size for several page counts
  - printing cost and royalty for each format and price tier
  - margins by page count
  - a generated PDF's page size, fonts and margins, checked with `pypdf`
  - EPUB structure
  - the review and disclosure rules
  - the 8-word overlap check
  - the daily cap
  - the KDP report import, with a real report layout
  - that no secret appears in any response
- **Docs:** add a `docs/BOOKS_PLAN.md` with the phases ticked as you finish them. Add progress entries, a `SECURITY.md` section, and a user guide section written for the owner, a non-programmer.

## Build order (each phase shippable, tested, and released with the normal release steps)
1. Constants with sources, the money maths (cost, royalty, spine, cover size), tables, and the Books page with niches and manual inputs.
2. Keepa and Trends integration, and niche scoring.
3. Gap mining and the book plan.
4. Chapter writing, the edit pass, claims and the overlap check.
5. Interior PDF and EPUB with validation.
6. Covers.
7. Listing, the upload package and checklist.
8. Launch tools and the advance-reader list.
9. KDP report import, Money and "What works".

## Definition of done
The owner can take one real niche from idea to an upload package that passes KDP's previewer with no errors, without leaving Cerebra except to upload. The full test suite passes, and the installer test and dashboard test pass. Every number shown either comes from data, with its source, or is labelled as an estimate with its inputs. Do not claim anything works until you have run it. Report honestly what is not done.
