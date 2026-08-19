# Live shadow-mode results — Account Details (APEX legacy vs migrated .NET)

Each input was evaluated by TWO independent systems:

- **Legacy**: the 6 validation expressions read verbatim from the deployed APEX app's own metadata (`APEX_APPLICATION_PAGE_VAL`, app 100), executed **by Oracle** against `apex_sample.eba_sales_customers`.
- **Modern**: the live migrated .NET `AccountService`, called over HTTP through CloudFront.

| Case | Legacy (APEX/Oracle) | Modern (.NET) | Verdict |
|---|---|---|---|
| Valid account (all rules pass) | PASS | PASS | ✅ match |
| Duplicate name (case-insensitive) | FAIL | FAIL | ✅ match |
| Tag contains '#' (quirk) | FAIL | FAIL | ✅ match |
| Tag contains '/' | FAIL | FAIL | ✅ match |
| Clean tag with '.' | PASS | PASS | ✅ match |
| URL ftp:// (not http) | FAIL | FAIL | ✅ match |
| URL HTTP:// (uppercase, case-sensitive) | FAIL | FAIL | ✅ match |
| Empty URL (passes) | PASS | PASS | ✅ match |

**Agreement: 8/8** — every decision and every exact error string matched.

## Variant B — browser-driven (the running APEX app itself)

Drove the REAL deployed APEX app (app 100, page 3 "Account Details") in a headless
Chromium via the SSM tunnel (localhost:8080), logged in as ADMIN, opened the Create
Account modal, filled the fields through the APEX item API, clicked Create, and
scraped the actually-rendered inline validation errors. Compared to the live .NET API.

| Case | Legacy APEX (rendered error) | Modern .NET | Verdict |
|---|---|---|---|
| Valid account | PASS (saved) | PASS | ✅ match |
| Duplicate name | "An account with that name already exists." | same | ✅ match |
| Tag with `#` | "Tags may not contain the following characters: : ; \ / ? &" | same | ✅ match |
| Tag with `/` | same tag error | same | ✅ match |
| Clean tag `.` | PASS | PASS | ✅ match |
| URL `ftp://` | 'Please provide a URL that begins with, "http".' | same | ✅ match |
| URL `HTTP://` (uppercase) | same http error | same | ✅ match |
| Clean `http://` | PASS | PASS | ✅ match |

**8/8 match against the live UI.**

### Findings surfaced by driving the real UI (honest notes)
1. **Legacy has a mandatory Territory field** ("Territory must have some value.") that the
   migrated .NET AccountService does NOT enforce. Real gap for a full migration — the POC's
   generated Account domain only covered the recovered name/tag/URL validations, not the
   required-Territory page item. Worth flagging to the client as the kind of thing a
   deeper generate pass (or the shadow harness itself) catches.
2. **False-pass trap:** first browser run showed URL cases "passing" only because the web-site
   field silently didn't fill (collapsed region) — APEX had nothing to validate and saved a
   blank URL. Caught by checking the DB (blank web) and re-running with apex.item().setValue();
   with the value actually set, both URL cases FAIL exactly as expected. Lesson: always confirm
   the input landed before trusting a PASS.

## Territory gap — closed and re-verified (2026-07-31)

Shadow-mode (variant B) surfaced a real omission: the legacy Account Details form
requires a Territory, but the first-generated .NET AccountService did not enforce it.
Closed the gap by adding the required-Territory validation to the migrated stack
(model + AccountService.Validate + Angular territory dropdown + /api/accounts/territories),
redeployed, and re-ran shadow-mode:

| Case | Legacy APEX | Modern .NET | Verdict |
|---|---|---|---|
| Territory missing | FAIL — "Territory must have some value." | FAIL — same string | ✅ match |
| Territory present | PASS | PASS | ✅ match |

The migrated form now matches the legacy form on ALL recovered validations, including
the required-Territory rule that only surfaced by driving the live legacy UI. This is
the intended shadow-mode workflow: run against the real system → find divergence →
fix the migration → re-run to green.
