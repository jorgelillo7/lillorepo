"""Tests for the literal-credential-in-a-URL check."""

from scripts import check_url_secrets as check


def test_a_literal_token_in_a_query_is_reported():
    # Built from a variable so this file does not itself hold a literal
    # credential URL. Not two adjacent strings: Ruff's formatter joins those.
    name = "auth"
    text = f"GET https://api.example.com/v1/data?{name}=abc123XYZ&limit=5"
    assert check.offenders(text) == [(1, "auth")]


def test_every_credential_like_name_is_caught():
    for name in ("token", "access_token", "api_key", "apikey", "key", "secret"):
        assert check.offenders(f"https://x.io/p?{name}=s3cr3tvalue") == [(1, name)]


def test_placeholders_pass():
    for value in ("<JP_TOKEN>", "${KEY}", "{token}", "YOUR_KEY", "...", "xxxx"):
        assert check.offenders(f"https://x.io/p?auth={value}") == []


def test_a_parameter_that_only_ends_like_a_credential_passes():
    assert check.offenders("https://x.io/p?monkey=banana&passkeyword=1") == []


def test_prose_without_a_url_passes():
    assert check.offenders("pass auth=abc123 to the client") == []
