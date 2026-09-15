from anonymize import anonymize_text


def test_anonymize_text_matches_exact_case():
    text, count = anonymize_text("BDR report", {"BDR": "namespace1"})
    assert text == "namespace1 report"
    assert count == 1


def test_anonymize_text_matches_lowercase_against_uppercase_key():
    text, count = anonymize_text("bdr report", {"BDR": "namespace1"})
    assert text == "namespace1 report"
    assert count == 1


def test_anonymize_text_matches_mixed_case_against_uppercase_key():
    text, count = anonymize_text("Bdr report", {"BDR": "namespace1"})
    assert text == "namespace1 report"
    assert count == 1


def test_anonymize_text_replacement_value_is_not_case_adjusted():
    # The dictionary value is substituted verbatim regardless of how the
    # match itself was cased in the source text.
    text, count = anonymize_text(
        "bdr and BDR and Bdr", {"BDR": "namespace1"}
    )
    assert text == "namespace1 and namespace1 and namespace1"
    assert count == 3


def test_anonymize_text_longer_key_wins_over_shorter_key_case_insensitively():
    # anonymize_text does not sort by length itself -- that's
    # load_replacements's job -- so the longer key must come first here,
    # same as load_replacements would produce.
    replacements = {"BDR2": "Company3", "BDR": "Company2"}
    text, count = anonymize_text("contact bdr2 team", replacements)
    assert text == "contact Company3 team"
    assert count == 1


def test_anonymize_text_returns_input_unchanged_when_no_match():
    text, count = anonymize_text(
        "nothing sensitive here", {"BDR": "namespace1"}
    )
    assert text == "nothing sensitive here"
    assert count == 0


def test_anonymize_text_returns_input_unchanged_for_empty_replacements():
    text, count = anonymize_text("BDR report", {})
    assert text == "BDR report"
    assert count == 0


def test_anonymize_text_counts_every_match_not_just_distinct_terms():
    text, count = anonymize_text(
        "BDR BDR BDR", {"BDR": "namespace1"}
    )
    assert text == "namespace1 namespace1 namespace1"
    assert count == 3
