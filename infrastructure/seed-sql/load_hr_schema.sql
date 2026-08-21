-- =============================================================================
-- load_hr_schema.sql  (BUG-4 seed artifact — minimal)
-- Run as SYSTEM against XEPDB1 by DatabaseStack EC2 UserData.
-- The ORDERS "after" app needs no HR/APEX data; app_data + the ORDERS schema are
-- created by app_data_packages.sql. The Oracle HR sample is installed separately
-- by the DatabaseStack from github.com/oracle/db-sample-schemas. This placeholder
-- keeps the bootstrap's `@load_hr_schema.sql` step valid.
-- =============================================================================
WHENEVER SQLERROR CONTINUE
ALTER SESSION SET CONTAINER = XEPDB1;
SELECT 'load_hr_schema: noop for ORDERS after' AS note FROM dual;
