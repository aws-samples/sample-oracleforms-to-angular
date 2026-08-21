-- =============================================================================
-- apex_sample_seed.sql  (BUG-14 seed artifact)
-- Run as SYSTEM against XEPDB1 by DatabaseStack EC2 UserData, after
-- app_data_packages.sql. Idempotent (guarded creates, MERGE upserts).
--
-- Provisions the APEX-path data the modern "after" app reads:
--   * apex_sample.eba_sales_territories / eba_sales_customers — a faithful
--     subset of the APEX Opportunities export DDL (audit + business columns;
--     the export's FLEX_* spare columns are omitted), with the EBA-style
--     BEFORE INSERT trigger that generates huge synthetic ids from SYS_GUID —
--     which is why the API handles ids as strings (see AccountService).
--   * app_data.report_registry — one row per converted Interactive Report;
--     the config-driven Reports API serves whatever is registered here.
--
-- The legacy APEX runtime itself is NOT installed by this sample: like the
-- Oracle Forms "before" (docs/FORMS_BEFORE_ENV.md), running the original APEX
-- app is a bring-your-own-environment exercise. This seed provides the shared
-- DATA so the modern Accounts/Reports pages work on a fresh deploy.
-- =============================================================================
WHENEVER SQLERROR CONTINUE
ALTER SESSION SET CONTAINER = XEPDB1;

DECLARE n NUMBER; BEGIN
  SELECT COUNT(*) INTO n FROM dba_users WHERE username = 'APEX_SAMPLE';
  IF n = 0 THEN EXECUTE IMMEDIATE 'CREATE USER apex_sample IDENTIFIED BY ChangeMe_2026'; END IF;
END;
/
ALTER USER apex_sample QUOTA UNLIMITED ON USERS;
-- Nothing ever connects AS apex_sample (the API uses app_data via grants), so
-- the schema account stays locked — no live credential to manage or leak.
ALTER USER apex_sample ACCOUNT LOCK;

ALTER SESSION SET CURRENT_SCHEMA = apex_sample;

DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE eba_sales_territories (
      id                     NUMBER PRIMARY KEY,
      row_version_number     NUMBER,
      row_key                VARCHAR2(255),
      territory_name         VARCHAR2(255) NOT NULL,
      territory_description  VARCHAR2(4000),
      territory_type         VARCHAR2(255),
      tags                   VARCHAR2(4000),
      created_by             VARCHAR2(255),
      created                TIMESTAMP(6) WITH TIME ZONE,
      updated_by             VARCHAR2(255),
      updated                TIMESTAMP(6) WITH TIME ZONE,
      CONSTRAINT eba_sales_terr_terr_cc CHECK
        (territory_type IN ('STATE','NAMED_ACCOUNT','KEY_ACCOUNT','COUNTRY','REGION'))
    )]';
EXCEPTION WHEN e_exists THEN NULL; END;
/
DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE eba_sales_customers (
      id                          NUMBER PRIMARY KEY,
      row_version_number          NUMBER,
      row_key                     VARCHAR2(255),
      customer_name               VARCHAR2(255),
      tags                        VARCHAR2(4000),
      customer_web_site           VARCHAR2(512),
      customer_number_of_emp      NUMBER,
      customer_facebook           VARCHAR2(1000),
      customer_linkedin           VARCHAR2(1000),
      customer_twitter            VARCHAR2(1000),
      customer_description        VARCHAR2(4000),
      customer_territory_id       NUMBER,
      customer_is_key_account_yn  VARCHAR2(1) NOT NULL,
      created_by                  VARCHAR2(255),
      created                     TIMESTAMP(6) WITH TIME ZONE,
      updated_by                  VARCHAR2(255),
      updated                     TIMESTAMP(6) WITH TIME ZONE,
      CONSTRAINT eba_sales_cust_ck_key_acct CHECK (customer_is_key_account_yn IN ('Y','N')),
      CONSTRAINT eba_sales_cust_terr_fk FOREIGN KEY (customer_territory_id)
        REFERENCES eba_sales_territories(id)
    )]';
EXCEPTION WHEN e_exists THEN NULL; END;
/

-- EBA id + audit pattern: SYS_GUID as a 39-digit NUMBER (overflows Int64 —
-- the reason the modern API round-trips ids as strings).
CREATE OR REPLACE TRIGGER apex_sample.eba_sales_customers_biu
BEFORE INSERT OR UPDATE ON apex_sample.eba_sales_customers FOR EACH ROW
BEGIN
  IF INSERTING AND :new.id IS NULL THEN
    :new.id := TO_NUMBER(SYS_GUID(), 'XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX');
  END IF;
  IF INSERTING THEN
    :new.row_key := SYS_GUID();
    :new.created := SYSTIMESTAMP;
    :new.created_by := NVL(SYS_CONTEXT('USERENV','SESSION_USER'), 'SAMPLE_USER');
  END IF;
  :new.row_version_number := NVL(:new.row_version_number, 0) + 1;
  :new.updated := SYSTIMESTAMP;
  :new.updated_by := NVL(SYS_CONTEXT('USERENV','SESSION_USER'), 'SAMPLE_USER');
END;
/

-- ---- representative seed dataset ------------------------------------------
DECLARE n NUMBER; BEGIN
  SELECT COUNT(*) INTO n FROM eba_sales_territories;
  IF n = 0 THEN
    INSERT INTO eba_sales_territories (id, territory_name, territory_type, territory_description)
      SELECT 1, 'Canada',         'COUNTRY', 'Canadian named accounts'   FROM dual UNION ALL
      SELECT 2, 'United States',  'COUNTRY', 'US named accounts'         FROM dual UNION ALL
      SELECT 3, 'France',         'COUNTRY', 'France'                    FROM dual UNION ALL
      SELECT 4, 'Germany',        'COUNTRY', 'Germany'                   FROM dual UNION ALL
      SELECT 5, 'Japan',          'COUNTRY', 'Japan'                     FROM dual UNION ALL
      SELECT 6, 'Australia',      'COUNTRY', 'Australia'                 FROM dual UNION ALL
      SELECT 7, 'EMEA Majors',    'REGION',  'Cross-border EMEA majors'  FROM dual UNION ALL
      SELECT 8, 'Key Accounts',   'KEY_ACCOUNT', 'Global key accounts'   FROM dual;
  END IF;
END;
/
DECLARE
  n NUMBER;
  PROCEDURE cust(p_name VARCHAR2, p_tags VARCHAR2, p_web VARCHAR2, p_terr NUMBER,
                 p_key VARCHAR2, p_emp NUMBER) IS
  BEGIN
    INSERT INTO eba_sales_customers
      (customer_name, tags, customer_web_site, customer_territory_id,
       customer_is_key_account_yn, customer_number_of_emp)
    VALUES (p_name, p_tags, p_web, p_terr, p_key, p_emp);
  END;
BEGIN
  SELECT COUNT(*) INTO n FROM eba_sales_customers;
  IF n = 0 THEN
    cust('Madison Materials',      'manufacturing, midwest', 'http://www.madisonmaterials.example.com', 2, 'Y', 3200);
    cust('Aurora Analytics',       'saas, analytics',        'http://www.auroraanalytics.example.com',  1, 'N', 240);
    cust('Beacon Logistics',       'transport',              'http://www.beaconlogistics.example.com',  2, 'N', 1800);
    cust('Cascade Foods',          'retail, food',           'http://www.cascadefoods.example.com',     1, 'Y', 5400);
    cust('Delta Mining Services',  'mining, services',       'http://www.deltamining.example.com',      6, 'Y', 950);
    cust('Ebisu Robotics',         'robotics',               'http://www.ebisurobotics.example.com',    5, 'N', 430);
    cust('Fjord Marine',           'marine',                 'http://www.fjordmarine.example.com',      4, 'N', 310);
    cust('Gaillard et Fils',       'distribution',           'http://www.gaillardetfils.example.com',   3, 'N', 120);
    cust('Harbour Steel',          'steel, heavy',           'http://www.harboursteel.example.com',     6, 'Y', 2700);
    cust('Isar Precision GmbH',    'precision, oem',         'http://www.isarprecision.example.com',    4, 'Y', 880);
    cust('Juniper Retail Group',   'retail',                 'http://www.juniperretail.example.com',    2, 'N', 6400);
    cust('Kootenay Timber',        'forestry',               'http://www.kootenaytimber.example.com',   1, 'N', 510);
    COMMIT;
  END IF;
END;
/

GRANT SELECT, INSERT, UPDATE ON apex_sample.eba_sales_customers  TO app_data;
GRANT SELECT                 ON apex_sample.eba_sales_territories TO app_data;

-- ---- report_registry: config-driven Reports API -----------------------------
ALTER SESSION SET CURRENT_SCHEMA = app_data;

DECLARE
  e_exists EXCEPTION; PRAGMA EXCEPTION_INIT(e_exists, -955);
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE report_registry (
      report_key   VARCHAR2(64) PRIMARY KEY,
      title        VARCHAR2(200) NOT NULL,
      base_sql     CLOB NOT NULL,
      columns_json CLOB NOT NULL,
      source_page  NUMBER
    )]';
EXCEPTION WHEN e_exists THEN NULL; END;
/

MERGE INTO report_registry r USING (SELECT 'accounts' k FROM dual) s ON (r.report_key = s.k)
WHEN NOT MATCHED THEN INSERT (report_key, title, base_sql, columns_json, source_page) VALUES (
  'accounts', 'Accounts',
  'SELECT TO_CHAR(c.id) AS id, c.customer_name, c.tags, t.territory_name,' ||
  ' c.customer_is_key_account_yn AS key_account, c.customer_number_of_emp AS employees' ||
  ' FROM apex_sample.eba_sales_customers c' ||
  ' LEFT JOIN apex_sample.eba_sales_territories t ON t.id = c.customer_territory_id',
  '[{"key":"customer_name","label":"Customer","sortable":true,"type":"text"},' ||
  '{"key":"tags","label":"Tags","sortable":false,"type":"text"},' ||
  '{"key":"territory_name","label":"Territory","sortable":true,"type":"text"},' ||
  '{"key":"key_account","label":"Key Account","sortable":true,"type":"text"},' ||
  '{"key":"employees","label":"Employees","sortable":true,"type":"number"}]',
  3);

MERGE INTO report_registry r USING (SELECT 'countries' k FROM dual) s ON (r.report_key = s.k)
WHEN NOT MATCHED THEN INSERT (report_key, title, base_sql, columns_json, source_page) VALUES (
  'countries', 'Countries',
  'SELECT t.territory_name AS country, COUNT(c.id) AS customers,' ||
  ' SUM(CASE WHEN c.customer_is_key_account_yn = ''Y'' THEN 1 ELSE 0 END) AS key_accounts,' ||
  ' NVL(SUM(c.customer_number_of_emp), 0) AS total_employees' ||
  ' FROM apex_sample.eba_sales_territories t' ||
  ' LEFT JOIN apex_sample.eba_sales_customers c ON c.customer_territory_id = t.id' ||
  ' WHERE t.territory_type = ''COUNTRY''' ||
  ' GROUP BY t.territory_name',
  '[{"key":"country","label":"Country","sortable":true,"type":"text"},' ||
  '{"key":"customers","label":"Customers","sortable":true,"type":"number"},' ||
  '{"key":"key_accounts","label":"Key Accounts","sortable":true,"type":"number"},' ||
  '{"key":"total_employees","label":"Total Employees","sortable":true,"type":"number"}]',
  17);
COMMIT;

-- verification
SELECT 'APEX_SEED_OK territories=' || (SELECT COUNT(*) FROM apex_sample.eba_sales_territories)
    || ' customers='  || (SELECT COUNT(*) FROM apex_sample.eba_sales_customers)
    || ' reports='    || (SELECT COUNT(*) FROM app_data.report_registry)
FROM dual;
