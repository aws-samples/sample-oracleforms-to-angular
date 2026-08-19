# Acceptance Criteria — APEX "Account Details" (P3_*) Behavioural Equivalence

## Purpose
This document defines the behavioural-equivalence acceptance criteria for the modernized
Angular + .NET implementation of the legacy Oracle APEX **Account Details** page. Each recovered
legacy validation rule (identified by APEX validation type and source page item) is mapped to the
modern .NET enforcement point (`AccountService.ValidateAsync`) and to the executable pytest test
that proves the modern behaviour reproduces the legacy behaviour **exactly**, including edge cases
and preserved legacy quirks.

Scope is limited to the Account Details `P3_*` validations. Data-access, insert/update SQL, and
Angular UI wiring are out of scope except where they affect observable validation behaviour.

---

## Traceability Matrix

| # | Legacy Rule (APEX) | APEX Validation Type | Source Item | Legacy Error String (exact) | Modern .NET Location | pytest Test(s) |
|---|--------------------|----------------------|-------------|-----------------------------|----------------------|----------------|
| 1 | Customer name not duplicated (case-insensitive, excluding self) | NOT_EXISTS | `P3_CUSTOMER_NAME` (`P3_ID` for self-exclusion) | `An account with that name already exists.` | `AccountService.ValidateAsync` → `CustomerNameExistsAsync` | `test_duplicate_name_case_insensitive_match`, `test_duplicate_name_excludes_self`, `test_duplicate_name_null_or_empty_passes`, `test_duplicate_name_unique_passes` |
| 2 | Valid Tag Characters | EXPRESSION | `P3_TAGS` | `Tags may not contain the following characters: : ; \ / ? &` | `AccountService.ValidateAsync` → `InvalidTagChars` regex | `test_tags_reject_each_blacklisted_char`, `test_tags_hash_character_rejected_quirk`, `test_tags_null_or_empty_passes`, `test_tags_clean_value_passes` |
| 3 | Website must start with "http" | EXPRESSION | `P3_CUSTOMER_WEB_SITE` | `Please provide a URL that begins with, "http".` | `AccountService.ValidateAsync` → `StartsWithHttp` | `test_website_starts_with_http`, `test_url_null_or_empty_passes`, `test_url_short_value_fails` |
| 4 | LinkedIn must start with "http" | EXPRESSION | `P3_CUSTOMER_LINKEDIN` | `Please provide a URL that begins with, "http".` | `AccountService.ValidateAsync` → `StartsWithHttp` | `test_linkedin_starts_with_http`, `test_url_null_or_empty_passes` |
| 5 | Facebook must start with "http" | EXPRESSION | `P3_CUSTOMER_FACEBOOK` | `Please provide a URL that begins with, "http".` | `AccountService.ValidateAsync` → `StartsWithHttp` | `test_facebook_starts_with_http`, `test_url_null_or_empty_passes` |
| 6 | Twitter must start with "http" | EXPRESSION | `P3_CUSTOMER_TWITTER` | `Please provide a URL that begins with, "http".` | `AccountService.ValidateAsync` → `StartsWithHttp` | `test_twitter_starts_with_http`, `test_url_null_or_empty_passes` |

---

## Preserved Legacy Quirks (Called Out)

- **`#` in regex vs. error text discrepancy (Rule 2).**
  The legacy APEX EXPRESSION validation regex is `'[:;#\/\\\?\&]'`, whose character class
  **includes `#`**. However, the human-readable legacy error message lists only
  `: ; \ / ? &` and **does not mention `#`**. This means a tag value such as `a#b` is
  **rejected** by the legacy rule even though the error text does not name the offending
  character. This behaviour is **intentionally preserved**: the modern regex
  (`@"[:;#/\\?&]"` in .NET, `/[:;#\/\\?&]/` in Angular) still rejects `#`, and the emitted
  error string is byte-for-byte identical to the legacy text (still omitting `#`).
  The test `test_tags_hash_character_rejected_quirk` explicitly locks in this quirk.

- **EXPRESSION validations only fire when the item has a value (Rules 2–6).**
  In APEX, EXPRESSION validations pass for null/empty items. The modern
  `StartsWithHttp` and tag-character checks treat null/empty as **valid**. Tests assert that
  null and empty string pass without error.

- **Case-insensitive duplicate check (Rule 1).**
  Legacy compares `upper(customer_name) = upper(:P3_CUSTOMER_NAME)`. The modern reference
  mirrors this with case-insensitive comparison, and self-exclusion is driven by
  `(:P3_ID is null or :P3_ID != id)`.

---

## Definition of Done (Shadow-Mode Criteria)

The Account Details validation surface is considered behaviourally equivalent and ready to exit
shadow mode when **all** of the following hold:

1. **Full rule coverage.** Every recovered `P3_*` validation (Rules 1–6) has at least one
   passing pytest test proving equivalence, and every test in this suite passes under plain
   `pytest` with **no external services or database**.

2. **Exact error strings.** For every failing input, the modern implementation emits the
   **byte-for-byte identical** legacy error string (including punctuation, quoting, and the
   preserved omission of `#`).

3. **Edge-case parity.** Null and empty inputs pass all EXPRESSION-type validations (Rules 2–6),
   and null/empty customer name passes the duplicate check (Rule 1), matching APEX semantics.

4. **Quirk preservation.** The `#`-in-regex behaviour is reproduced exactly and locked by a
   dedicated regression test; no "cleanup" of the error text or regex is permitted.

5. **Self-exclusion parity.** Updating a record with its own unchanged name does **not** raise a
   duplicate error, while a case-insensitive collision with a *different* record does.

6. **Aggregation parity.** When multiple rules fail, all corresponding errors are collected
   (mirroring the .NET `errors` list in `ValidateAsync`), and none are silently dropped.

7. **Shadow-mode agreement.** Over the observation window, the modern
   `AccountService.ValidateAsync` and the legacy APEX validations produce the **same pass/fail
   decision and identical error strings** for 100% of sampled inputs; any divergence is a defect
   and blocks sign-off.

**Sign-off** requires this suite green in CI, this document reviewed against the recovered APEX
metadata, and zero unexplained shadow-mode divergences on the Account Details page.