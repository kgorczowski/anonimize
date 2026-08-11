from anonymize import validate_pesel, validate_nip, validate_iban, validate_luhn


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
