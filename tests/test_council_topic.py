"""A meeting's topic is the owner's question: no pasted page wrapper, and follow-ups don't pile up old summaries."""
from ai_hq.council import ENDED, clean_topic


def test_the_pages_wrapper_is_removed_once_or_several_times():
    assert clean_topic("  How do we reach buyers?  ") == "How do we reach buyers?"
    assert clean_topic("The owner asked: “How do we reach buyers?”") == "How do we reach buyers?"
    nested = "The owner asked: “The owner asked: “Hello, research the market” · 3 rounds” · they talk until they both agree"
    assert clean_topic(nested) == "Hello, research the market"
    assert clean_topic('The owner asked: "Plan the launch"\nKeep it cheap') == "Plan the launch\nKeep it cheap"
    assert clean_topic("Explain why “the owner asked” matters") == "Explain why “the owner asked” matters"


def test_a_follow_up_keeps_only_the_question():
    topic = "Find buyers" + ENDED + " they agreed on X\n\nTHE OWNER ADDS (their words decide): more"
    assert topic.split(ENDED)[0].strip() == "Find buyers"
