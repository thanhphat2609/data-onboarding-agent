from datetime import date

import pytest

from agent.workflow.extraction import clean_description, rule_extract, validate

TODAY = date(2026, 10, 27)


@pytest.mark.parametrize("text, expected", [
    ("Hi, I want to onboarding new dataset call Google Search Console", "Onboarding new dataset call Google Search Console"),
    ("Hello team, please we need the CRM segments table", "We need the CRM segments table"),
    ("Hi data team, I would like to get GSC clicks", "Get GSC clicks"),
    ("Xin chào, tôi cần dữ liệu GA4", "Tôi cần dữ liệu GA4"),
    ("The sales team needs CRM customers", "The sales team needs CRM customers"),
    ("Higher-level CRM data", "Higher-level CRM data"),  # starts like "hi", isn't a greeting
    ("Hi", "Hi"),  # nothing left: keep the text
])
def test_clean_description(text, expected):
    assert clean_description(text) == expected


def test_first_message_gives_a_clean_description():
    found = rule_extract("Hi, I want to onboard Google Search Console clicks per page", [], TODAY, first_message=True)
    assert found["dataset_description"] == "Onboard Google Search Console clicks per page"


def test_labelled_answers():
    found = rule_extract("date range: 2024-01-01 to now\neta: 2026-12-01\ngrain: date x page", [], TODAY)
    assert found["date_range"] == {"start": "2024-01-01", "end": "2026-10-27"}
    assert found["eta"] == "2026-12-01"
    assert found["grain"] == "date x page"


def test_numbered_answers_map_to_the_asked_fields():
    found = rule_extract("1. 2024-01-01 to now\n3. date x page", ["date_range", "eta", "grain"], TODAY)
    assert found["date_range"]["start"] == "2024-01-01"
    assert found["grain"] == "date x page"
    assert "eta" not in found


def test_numbered_answer_with_its_own_label_drops_the_label():
    found = rule_extract("2. eta: 2026-12-01\n3. Grain: Date x Campaign", ["date_range", "eta", "grain"], TODAY)
    assert found["eta"] == "2026-12-01"
    assert found["grain"] == "Date x Campaign"


def test_relative_eta():
    found = rule_extract("eta: in 4 weeks", [], TODAY)
    assert found["eta"] == "2026-11-24"


def test_eta_in_the_past_is_asked_again():
    clean, errors = validate({"eta": "2026-10-01"}, TODAY)
    assert "eta" in errors and "eta" not in clean
