# APEX Opportunities CRM — Dependency Map (AI-extracted)

Cross-artifact dependency graph from the APEX export. These edges are the migration seams.

## Summary
- Pages: 138
- Tables: 47
- Packages: 4
- Access Edges: 61
- Call Edges: 12

## Pages that call PL/SQL packages
- `Username Format` calls `EBA_SALES_ACL_API (PACKAGE BODY)` (via Set Username Format Preference)
- `Username Format` calls `EBA_SALES_ACL_API (PACKAGE)` (via Set Username Format Preference)
- `Administration` calls `EBA_SALES_ACL_API (PACKAGE BODY)` (via ENABLE_ACCESS_CONTROL)
- `Administration` calls `EBA_SALES_ACL_API (PACKAGE)` (via ENABLE_ACCESS_CONTROL)
- `Application Preferences` calls `EBA_SALES_FW (PACKAGE)` (via Save Preference Values)
- `Manage Sample Data` calls `EBA_SALES_DATA (PACKAGE)` (via reset data)
- `Access Control Configuration` calls `EBA_SALES_ACL_API (PACKAGE BODY)` (via ACCESS CONTROL ENABLED)
- `Access Control Configuration` calls `EBA_SALES_ACL_API (PACKAGE)` (via ACCESS CONTROL ENABLED)
- `Add Multiple Users` calls `EBA_SALES_ACL_API (PACKAGE BODY)` (via Create Collections)
- `Add Multiple Users` calls `EBA_SALES_ACL_API (PACKAGE)` (via Create Collections)
- `Getting Started` calls `EBA_SALES_FW (PACKAGE)` (via Set Username Format based on current user's username)
- `Getting Started` calls `EBA_SALES_DATA (PACKAGE)` (via Process Page Data)