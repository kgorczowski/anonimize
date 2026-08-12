from anonymize import validate_pesel, validate_nip, validate_iban, validate_luhn, redact_pii


def test_validate_pesel_accepts_valid_number():
    assert validate_pesel("02031554796") is True


def test_validate_pesel_rejects_bad_checksum():
    assert validate_pesel("02031554797") is False


def test_validate_pesel_rejects_wrong_length():
    assert validate_pesel("123") is False


def test_validate_nip_accepts_valid_number():
    assert validate_nip("2134567890") is True


def test_validate_nip_rejects_bad_checksum():
    assert validate_nip("2134567891") is False


def test_validate_iban_accepts_valid_polish_iban():
    assert validate_iban("PL61109010140000071219812874") is True


def test_validate_iban_rejects_bad_checksum():
    assert validate_iban("PL61109010140000071219812875") is False


def test_validate_luhn_accepts_valid_card_number():
    assert validate_luhn("4111111111111111") is True


def test_validate_luhn_rejects_bad_checksum():
    assert validate_luhn("4111111111111112") is False


def test_redact_pii_masks_email():
    text, count = redact_pii("Contact: jan.kowalski@example.com please")
    assert text == "Contact: [EMAIL] please"
    assert count == 1


def test_redact_pii_masks_valid_pesel_only():
    text, count = redact_pii("PESEL: 02031554796, other: 02031554797")
    assert text == "PESEL: [PESEL], other: 02031554797"
    assert count == 1


def test_redact_pii_masks_valid_nip():
    text, count = redact_pii("NIP 2134567890 na fakturze")
    assert text == "NIP [NIP] na fakturze"
    assert count == 1


def test_redact_pii_masks_iban():
    text, count = redact_pii("IBAN: PL61109010140000071219812874.")
    assert text == "IBAN: [IBAN]."
    assert count == 1


def test_redact_pii_masks_iban_printed_in_groups_of_four():
    """
    The standard printed form. Before the IBAN pattern accepted spaces,
    CARD_PATTERN grabbed the 16 digits in the middle and the country
    code, check digits and account tail leaked in cleartext.
    """
    text, count = redact_pii("IBAN: PL61 1090 1014 0000 0712 1981 2874")
    assert text == "IBAN: [IBAN]"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_masks_lowercase_iban():
    text, count = redact_pii("IBAN: pl61109010140000071219812874")
    assert text == "IBAN: [IBAN]"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_masks_grouped_iban_followed_by_prose():
    text, count = redact_pii(
        "Konto PL61 1090 1014 0000 0712 1981 2874 w PKO"
    )
    assert text == "Konto [IBAN] w PKO"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_masks_grouped_iban_with_short_final_group():
    # 22-character German IBAN: the last printed group is 2 chars long.
    text, count = redact_pii("Konto DE89 3704 0044 0532 0130 00 w banku")
    assert text == "Konto [IBAN] w banku"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_iban_followed_by_word_pl():
    text, count = redact_pii(
        "Nr konta: PL61 1090 1014 0000 0712 1981 2874 Bank Pekao SA"
    )
    assert text == "Nr konta: [IBAN] Bank Pekao SA"
    assert count == 1


def test_redact_pii_iban_followed_by_word_es():
    text, count = redact_pii(
        "Konto ES91 2100 0418 4502 0005 1332 bank koniec"
    )
    assert "ES91" not in text
    assert "2100 0418 4502 0005 1332" not in text
    assert "[IBAN]" in text
    assert count == 1


def test_redact_pii_iban_followed_by_four_digit_number():
    """
    A trailing number is the same trap as a trailing word: it looks
    exactly like one more group of the account number.
    """
    text, count = redact_pii(
        "Konto PL61 1090 1014 0000 0712 1981 2874 1234 PLN"
    )
    assert text == "Konto [IBAN] 1234 PLN"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_masks_two_ibans_on_one_line():
    """
    The candidate span around the first IBAN reaches into the second
    one. Resuming the scan after the whole over-matched span (what
    re.sub does) would skip the second IBAN and leak it in cleartext.
    """
    text, count = redact_pii(
        "Dwa: PL61 1090 1014 0000 0712 1981 2874 oraz "
        "ES91 2100 0418 4502 0005 1332 koniec"
    )
    assert text == "Dwa: [IBAN] oraz [IBAN] koniec"
    assert count == 2


def test_redact_pii_masks_iban_standing_behind_a_failed_candidate():
    """
    Short words chain into a candidate span that swallows the real IBAN
    behind them. Discarding the failed candidate whole would leave the
    IBAN unredacted - and CARD_PATTERN then mislabels its middle 16
    digits, which is the original leak this pattern exists to prevent.
    """
    text, count = redact_pii(
        "AB12 not a real iban PL61 1090 1014 0000 0712 1981 2874"
    )
    assert text == "AB12 not a real iban [IBAN]"
    assert "[CARD]" not in text
    assert count == 1


def test_redact_pii_does_not_redact_iban_shaped_text_that_is_not_an_iban():
    """
    Nothing here passes the checksum, so nothing may be redacted - the
    over-matching candidate pattern must not become an over-redacting
    one.
    """
    original = "AB12 not a real iban at all bank account number here"
    text, count = redact_pii(original)
    assert text == original
    assert "[IBAN]" not in text
    assert count == 0


def test_redact_pii_masks_card_number_with_spaces():
    text, count = redact_pii("Card 4111 1111 1111 1111 exp 12/30")
    assert text == "Card [CARD] exp 12/30"
    assert count == 1


def test_redact_pii_masks_ipv4_address():
    text, count = redact_pii("Server at 192.168.1.10 responded")
    assert text == "Server at [IP] responded"
    assert count == 1


def test_redact_pii_masks_phone_number():
    text, count = redact_pii("Zadzwon: +48 123 456 789 dzisiaj")
    assert text == "Zadzwon: [PHONE] dzisiaj"
    assert count == 1


def test_redact_pii_does_not_merge_digits_across_newlines():
    """
    \\s in the phone pattern used to match newlines, so three separate
    lines of numbers collapsed into a single [PHONE] token and the
    document structure was destroyed.
    """
    text, count = redact_pii("Counts:\n100\n200\n300\ndone\n")
    assert text == "Counts:\n100\n200\n300\ndone\n"
    assert count == 0


def test_redact_pii_does_not_merge_digits_across_tabs():
    text, count = redact_pii("a\t100\t200\t300\tb")
    assert text == "a\t100\t200\t300\tb"
    assert count == 0


def test_redact_pii_returns_zero_for_clean_text():
    text, count = redact_pii("Nothing sensitive here.")
    assert text == "Nothing sensitive here."
    assert count == 0


def test_redact_pii_counts_multiple_matches():
    text, count = redact_pii("a@b.com and c@d.com")
    assert text == "[EMAIL] and [EMAIL]"
    assert count == 2
