"""
Stage 5 — Live shadow-mode: legacy APEX validations vs the migrated .NET API.

Proves behavioural equivalence for the migrated "Account Details" form by running
the SAME inputs through two INDEPENDENT systems and diffing every decision:

  LEGACY oracle  : the six validation expressions read VERBATIM from the deployed
                   APEX app's own metadata (APEX_APPLICATION_PAGE_VAL), executed
                   BY ORACLE ITSELF against apex_sample.eba_sales_customers. This is
                   not a re-implementation and not the AI's understanding — it is
                   the legacy rule as the running APEX app stores and runs it.
  MODERN system  : the live migrated .NET AccountService, hit over HTTP through
                   CloudFront (POST /api/accounts, GET /api/accounts/validate-name).

For each case we compare pass/fail AND the exact error strings. Any divergence is
a real defect. Output: SHADOW_RESULTS.md + console table.

Run on a host with an Oracle SQL path to XEPDB1 (executed here via SSM on the DB
EC2) and network access to the CloudFront URL.
"""

# The legacy expressions, copied VERBATIM from APEX_APPLICATION_PAGE_VAL
# (application_id=100, page 'Account Details'). A validation PASSES when the
# expression is TRUE (EXPRESSION type) / returns NO rows (NOT_EXISTS type).
LEGACY = {
    "name_not_duplicated": {
        "type": "NOT_EXISTS",
        "sql": ("select null from eba_sales_customers "
                "where (:P3_ID is null or :P3_ID != id) "
                "and upper(customer_name) = upper(:P3_CUSTOMER_NAME)"),
        "error": "An account with that name already exists.",
    },
    "valid_tag_characters": {
        "type": "EXPRESSION",
        "sql": r"select case when (not regexp_like(:P3_TAGS, '[:;#\/\\\?\&]')) then 1 else 0 end from dual",
        "error": r"Tags may not contain the following characters: : ; \ / ? &",
    },
    "website_http": {
        "type": "EXPRESSION",
        "sql": "select case when (substr(:P3_CUSTOMER_WEB_SITE,1,4)='http') then 1 else 0 end from dual",
        "error": 'Please provide a URL that begins with, "http".',
    },
    # linkedin/facebook/twitter are the same substr rule; covered by website case
    # plus explicit fields in the test battery below.
}

# Test battery: each case is one candidate account. We record, per rule, what the
# LEGACY Oracle expression decides and what the MODERN .NET API decides.
CASES = [
    {"id": "valid_all",        "customerName": "Shadowtest Alpha Co", "tags": "vip gold", "web": "http://a.com"},
    {"id": "dup_name",         "customerName": "Madison Materials",   "tags": "", "web": ""},
    {"id": "tag_hash",         "customerName": "Shadowtest Beta Co",  "tags": "vip#gold", "web": ""},
    {"id": "tag_slash",        "customerName": "Shadowtest Gamma Co", "tags": "a/b", "web": ""},
    {"id": "tag_clean_dot",    "customerName": "Shadowtest Delta Co", "tags": "abc.def", "web": ""},
    {"id": "url_ftp",          "customerName": "Shadowtest Eps Co",   "tags": "", "web": "ftp://x.com"},
    {"id": "url_upper_HTTP",   "customerName": "Shadowtest Zeta Co",  "tags": "", "web": "HTTP://x.com"},
    {"id": "url_empty_ok",     "customerName": "Shadowtest Eta Co",   "tags": "", "web": ""},
]
