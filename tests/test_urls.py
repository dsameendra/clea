import pytest

from clea.urls import default_path_prefix, in_scope, looks_like_non_html, normalize_url, url_terms


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Example.COM", "https://example.com/"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:8080/a", "http://example.com:8080/a"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&b=2&a=1&fbclid=z", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a/./b/../c/", "https://example.com/a/c/"),
        ("https://user:pw@example.com/", "https://example.com/"),
        ("https://example.com//double//slash", "https://example.com/double/slash"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "mailto:a@b.c", "javascript:alert(1)", "ftp://x.org/", "data:text/html,hi", "http://", "https://exa mple.com:99999/"])
def test_normalize_rejects(raw):
    assert normalize_url(raw) is None


def test_normalize_relative():
    assert normalize_url("../x?q=1#f", base="https://e.com/a/b/c") == "https://e.com/a/x?q=1"


def test_scope():
    assert default_path_prefix("https://docs.python.org/3/tutorial/index.html") == "/3/tutorial/"
    assert default_path_prefix("https://example.com") == "/"
    assert in_scope("https://www.example.com/a", "example.com", "/")
    assert in_scope("https://docs.python.org/3/tutorial/x.html", "docs.python.org", "/3/tutorial/")
    assert not in_scope("https://docs.python.org/3/library/", "docs.python.org", "/3/tutorial/")
    assert not in_scope("https://evil.com/example.com", "example.com", "/")
    assert not in_scope("https://sub.example.com/", "example.com", "/")


def test_non_html_and_terms():
    assert looks_like_non_html("https://e.com/report.PDF")
    assert not looks_like_non_html("https://e.com/page")
    assert url_terms("https://www.flask.palletsprojects.com/en/quickstart/index.html") == "flask palletsprojects en quickstart"


def test_google_srsltid_is_stripped():
    assert normalize_url("https://shop.example/?srsltid=AYCX9vJ&page=2") == "https://shop.example/?page=2"
