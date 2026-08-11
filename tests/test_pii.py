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


def test_redact_pii_returns_zero_for_clean_text():
    text, count = redact_pii("Nothing sensitive here.")
    assert text == "Nothing sensitive here."
    assert count == 0


def test_redact_pii_counts_multiple_matches():
    text, count = redact_pii("a@b.com and c@d.com")
    assert text == "[EMAIL] and [EMAIL]"
    assert count == 2
