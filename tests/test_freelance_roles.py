"""Jobs that need someone else's trade sink below automatic bidding; jobs that only mention one, while building something, don't."""
from ai_hq import freelance

SETTINGS = {"services": ["web", "mobile_ai", "design", "data"], "keywords": [], "exclude": [], "min_budget": 0, "skills": ["Web development", "AI integration"]}


def scored(title, body="We need branding, a logo and a website with AI and social media.", settings=SETTINGS):
    return freelance.score({"title": title, "description": body, "kind": "fixed", "budget_min": 750, "budget_max": 1500, "currency": "USD"}, settings)


def test_the_work_of_other_trades_stays_below_automatic_bidding():
    for title in ("Female Videographer for Personal Branding", "Looking for an AI Video Creator to Make a Product Review",
                  "Hiring an AI Filmmaker for a 60-Second Advert", "UGC Video Creator & Social Media Growth for AI Software",
                  "E-Commerce Website Copywriting", "Promo Video Editing for Social Media", "Facebook Ads & Google Ads Specialist Needed for E-commerce",
                  "SEO & Social Media Marketing Expert Needed", "Performance Marketing & Growth Expert", "English-Spanish Website Localization",
                  "Pre-Launch Legal Review of a Health Website", "US/Europe Article Reviewer"):
        points, reasons = scored(title)
        assert points < 40, title
        assert any("not what you sell" in reason for reason in reasons) or points == 0, title


def test_building_something_for_those_trades_is_the_owners_work():
    for title, role in (("Build a Video Editor App with AI", "video editor"), ("Website for my lawyer office with a logo", "lawyer"),
                        ("WordPress site for a photographer", "photographer"), ("Develop a Social Media Marketing Dashboard", "social media marketing"),
                        ("Shopify store for a tutor", "tutor"), ("Mobile app for a therapist", "therapist")):
        assert freelance.OTHER_ROLE.search(title), title
        assert not any("not what you sell" in reason for reason in scored(title)[1]), title


def test_real_web_jobs_are_untouched():
    for title in ("Multi-Product E-Commerce Website Build", "Clean Website & Logo Build", "WordPress Developer Needed", "AI Chatbot Website Integration",
                  "Graphic Design Expert Needed for Corporate Branding Materials"):
        assert not any("not what you sell" in reason for reason in scored(title)[1]), title


def test_the_owner_selling_that_work_overrides_the_rule():
    selling = {**SETTINGS, "keywords": ["videographer"]}
    assert any("not what you sell" in reason for reason in scored("Female Videographer for Personal Branding")[1])
    assert not any("not what you sell" in reason for reason in scored("Female Videographer for Personal Branding", settings=selling)[1])


def test_the_rules_changed_so_open_leads_are_scored_again():
    assert freelance.SCORE_VERSION >= 5
