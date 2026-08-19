import re
import pytest

# ---------------------------------------------------------------------------
# Inline pure-Python reference module mirroring the generated .NET AccountService.
#
# NOTE: The legacy APEX "Valid Tag Characters" regex class is [:;#\/\\\?\&],
# which INCLUDES '#'. The legacy error message text does NOT list '#'
# ("Tags may not contain the following characters: : ; \ / ? &"), yet the
# regex still REJECTS a '#'. The modern .NET / Angular code preserves the
# legacy BEHAVIOUR (rejecting '#'), not the message wording. These tests
# encode that legacy-correct behaviour as the oracle.
# ---------------------------------------------------------------------------

# Mirrors .NET: new(@"[:;#/\\?&]") and Angular: /[:;#\/\\?&]/
_INVALID_TAG_CHARS = re.compile(r"[:;#/\\?&]")

# Exact legacy error strings.
ERR_DUPLICATE_NAME = "An account with that name already exists."
ERR_INVALID_TAGS = r"Tags may not contain the following characters: : ; \ / ? &"
ERR_MUST_START_HTTP = 'Please provide a URL that begins with, "http".'


def has_invalid_tag_chars(tags):
    """Mirrors regexp_like(:P3_TAGS, '[:;#\\/\\\\\\?\\&]').
    Returns False for None/empty (APEX EXPRESSION passes when no value)."""
    if tags is None or tags == "":
        return False
    return _INVALID_TAG_CHARS.search(tags) is not None


def starts_with_http(value):
    """Mirrors substr(:PX, 1, 4) = 'http'.
    None/empty returns True (passes) -- APEX EXPRESSION validations only fire
    when the item has a value."""
    if value is None or value == "":
        return True
    return len(value) >= 4 and value[0:4] == "http"


def customer_name_is_duplicate(name, existing_rows, exclude_id):
    """Mirrors:
        select null from eba_sales_customers
        where (:P3_ID is null or :P3_ID != id)
          and upper(customer_name) = upper(:P3_CUSTOMER_NAME)
    Case-insensitive, excluding self by id. None/empty name never collides."""
    if name is None or name == "":
        return False
    target = name.upper()
    for row in existing_rows:
        row_id = row.get("id")
        row_name = row.get("customer_name")
        # (:P3_ID is null or :P3_ID != id)
        if exclude_id is not None and exclude_id == row_id:
            continue
        if row_name is not None and row_name.upper() == target:
            return True
    return False


def validate_account(account, existing_rows):
    """Mirrors AccountService.ValidateAsync ordering and messages."""
    errors = []

    name = account.get("customer_name")
    if name is not None and name != "":
        if customer_name_is_duplicate(name, existing_rows, account.get("id")):
            errors.append(ERR_DUPLICATE_NAME)

    tags = account.get("tags")
    if tags is not None and tags != "" and has_invalid_tag_chars(tags):
        errors.append(ERR_INVALID_TAGS)

    if not starts_with_http(account.get("customer_web_site")):
        errors.append(ERR_MUST_START_HTTP)
    if not starts_with_http(account.get("customer_linkedin")):
        errors.append(ERR_MUST_START_HTTP)
    if not starts_with_http(account.get("customer_facebook")):
        errors.append(ERR_MUST_START_HTTP)
    if not starts_with_http(account.get("customer_twitter")):
        errors.append(ERR_MUST_START_HTTP)

    return errors


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

EXISTING_ROWS = [
    {"id": 1, "customer_name": "Acme Corporation"},
    {"id": 2, "customer_name": "Globex"},
    {"id": 3, "customer_name": "Initech"},
]


def _valid_account(**overrides):
    base = {
        "id": None,
        "customer_name": "Brand New Co",
        "tags": "enterprise vip",
        "customer_web_site": "http://example.com",
        "customer_linkedin": "https://linkedin.com/x",
        "customer_facebook": "http://fb.com/x",
        "customer_twitter": "https://twitter.com/x",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# (1) Duplicate customer name (case-insensitive, excluding self)
# ---------------------------------------------------------------------------

def test_duplicate_name_exact_match_yields_legacy_error():
    acct = _valid_account(id=None, customer_name="Acme Corporation")
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [ERR_DUPLICATE_NAME]


def test_duplicate_name_is_case_insensitive():
    acct = _valid_account(id=None, customer_name="aCmE cORPORATION")
    errors = validate_account(acct, EXISTING_ROWS)
    assert ERR_DUPLICATE_NAME in errors
    assert errors == [ERR_DUPLICATE_NAME]


def test_differently_cased_existing_name_still_collides():
    rows = [{"id": 10, "customer_name": "GLOBEX"}]
    assert customer_name_is_duplicate("globex", rows, exclude_id=None) is True


def test_excluding_self_same_id_does_not_collide():
    # Editing row 1 with the same name must NOT collide with itself.
    acct = _valid_account(id=1, customer_name="Acme Corporation")
    errors = validate_account(acct, EXISTING_ROWS)
    assert ERR_DUPLICATE_NAME not in errors
    assert errors == []


def test_different_id_same_name_still_collides():
    acct = _valid_account(id=99, customer_name="Acme Corporation")
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [ERR_DUPLICATE_NAME]


def test_empty_name_never_collides():
    assert customer_name_is_duplicate("", EXISTING_ROWS, exclude_id=None) is False
    assert customer_name_is_duplicate(None, EXISTING_ROWS, exclude_id=None) is False


# ---------------------------------------------------------------------------
# (2) Valid Tag Characters -- legacy class [:;#/\\?&] INCLUDING '#'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_char",
    [":", ";", "#", "\\", "/", "?", "&"],
)
def test_forbidden_tag_char_is_rejected(bad_char):
    tags = "vip" + bad_char + "gold"
    assert has_invalid_tag_chars(tags) is True
    acct = _valid_account(tags=tags)
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [ERR_INVALID_TAGS]


def test_hash_char_is_rejected_even_though_message_omits_it():
    # The legacy regex rejects '#', but the error message text does not list '#'.
    # Modern code preserves the legacy behaviour, not the message wording.
    assert has_invalid_tag_chars("tag#one") is True
    acct = _valid_account(tags="tag#one")
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [ERR_INVALID_TAGS]
    assert "#" not in ERR_INVALID_TAGS  # confirms the message omits '#'


@pytest.mark.parametrize(
    "clean_tags",
    ["enterprise vip", "gold-tier", "region_apac", "level1 level2", "abc.def"],
)
def test_clean_tags_pass(clean_tags):
    assert has_invalid_tag_chars(clean_tags) is False
    acct = _valid_account(tags=clean_tags)
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == []


def test_empty_or_null_tags_pass():
    assert has_invalid_tag_chars("") is False
    assert has_invalid_tag_chars(None) is False
    assert validate_account(_valid_account(tags=""), EXISTING_ROWS) == []
    assert validate_account(_valid_account(tags=None), EXISTING_ROWS) == []


# ---------------------------------------------------------------------------
# (3) URL fields must start with 'http'
# ---------------------------------------------------------------------------

URL_FIELDS = [
    "customer_web_site",
    "customer_linkedin",
    "customer_facebook",
    "customer_twitter",
]


@pytest.mark.parametrize("field", URL_FIELDS)
def test_non_http_url_yields_legacy_error(field):
    acct = _valid_account(**{field: "www.example.com"})
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [ERR_MUST_START_HTTP]


@pytest.mark.parametrize("field", URL_FIELDS)
@pytest.mark.parametrize("empty_value", [None, ""])
def test_empty_url_passes(field, empty_value):
    # APEX EXPRESSION validations only fire when the item has a value.
    acct = _valid_account(**{field: empty_value})
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == []


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://x.com", True),
        ("https://x.com", True),  # 'http' prefix of 'https'
        ("http", True),
        ("htt", False),
        ("ftp://x.com", False),
        ("HTTP://x.com", False),  # case-sensitive, matching Oracle substr = 'http'
        (None, True),
        ("", True),
    ],
)
def test_starts_with_http_reference(value, expected):
    assert starts_with_http(value) is expected


def test_multiple_bad_urls_produce_ordered_errors():
    acct = _valid_account(
        customer_web_site="www.a.com",
        customer_linkedin="www.b.com",
        customer_facebook="http://ok.com",
        customer_twitter="www.c.com",
    )
    errors = validate_account(acct, EXISTING_ROWS)
    # Ordered: website, linkedin, twitter (facebook ok) -> 3 identical messages.
    assert errors == [ERR_MUST_START_HTTP, ERR_MUST_START_HTTP, ERR_MUST_START_HTTP]


# ---------------------------------------------------------------------------
# (4) Fully valid account yields zero errors
# ---------------------------------------------------------------------------

def test_fully_valid_account_has_no_errors():
    acct = _valid_account()
    assert validate_account(acct, EXISTING_ROWS) == []


def test_combined_multiple_rule_failures_ordering():
    acct = _valid_account(
        id=None,
        customer_name="Initech",          # duplicate
        tags="bad#tag",                    # invalid tag char (incl '#')
        customer_web_site="www.no-http",   # bad url
    )
    errors = validate_account(acct, EXISTING_ROWS)
    assert errors == [
        ERR_DUPLICATE_NAME,
        ERR_INVALID_TAGS,
        ERR_MUST_START_HTTP,
    ]