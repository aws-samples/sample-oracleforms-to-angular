ALTER SESSION SET CONTAINER=XEPDB1;
set serveroutput on size unlimited
set feedback off
set define off
DECLARE
  FUNCTION name_taken(p VARCHAR2) RETURN NUMBER IS x NUMBER; BEGIN
    EXECUTE IMMEDIATE 'select count(*) from apex_sample.eba_sales_customers where upper(customer_name)=upper(:n)'
      INTO x USING p; RETURN x; END;
  FUNCTION tag_ok(p VARCHAR2) RETURN NUMBER IS x NUMBER; BEGIN
    IF p IS NULL THEN RETURN 1; END IF;
    EXECUTE IMMEDIATE q'{select case when (not regexp_like(:t, '[:;#\/\\\?\&]')) then 1 else 0 end from dual}'
      INTO x USING p; RETURN x; END;
  FUNCTION url_ok(p VARCHAR2) RETURN NUMBER IS x NUMBER; BEGIN
    IF p IS NULL THEN RETURN 1; END IF;
    EXECUTE IMMEDIATE q'{select case when (substr(:w,1,4)='http') then 1 else 0 end from dual}'
      INTO x USING p; RETURN x; END;
  PROCEDURE run(id VARCHAR2, nm VARCHAR2, tags VARCHAR2, web VARCHAR2) IS errs VARCHAR2(4000):=''; BEGIN
    IF name_taken(nm) > 0 THEN errs:=errs||'An account with that name already exists.|'; END IF;
    IF tag_ok(tags)=0 THEN errs:=errs||'Tags may not contain the following characters: : ; \ / ? &|'; END IF;
    IF url_ok(web)=0 THEN errs:=errs||'Please provide a URL that begins with, "http".|'; END IF;
    DBMS_OUTPUT.PUT_LINE('LEGACY::'||id||'::'||CASE WHEN errs='' THEN 'PASS' ELSE errs END);
  END;
BEGIN
  run('valid_all','Shadowtest Alpha Co','vip gold','http://a.com');
  run('dup_name','Madison Materials',NULL,NULL);
  run('tag_hash','Shadowtest Beta Co','vip#gold',NULL);
  run('tag_slash','Shadowtest Gamma Co','a/b',NULL);
  run('tag_clean_dot','Shadowtest Delta Co','abc.def',NULL);
  run('url_ftp','Shadowtest Eps Co',NULL,'ftp://x.com');
  run('url_upper_HTTP','Shadowtest Zeta Co',NULL,'HTTP://x.com');
  run('url_empty_ok','Shadowtest Eta Co',NULL,NULL);
END;
/
