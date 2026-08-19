# PL/SQL Processes (APEX Opportunities CRM)

Server-side PL/SQL logic recovered from the APEX processes.

## Set Initial Begin and End  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Revenue by Quarter
_tables: ['EBA_SALES_SALES_PERIODS']_
```plsql
begin
  for c1 in (
  select first_day
    from eba_sales_sales_periods
   where sysdate-270 between first_day and last_day
  )
  loop
     :P14_BEGIN_QTR := to_char(c1.first_day,'YYYYMMDD');
  end loop;

  for c2 in (
  select last_day
    from eba_sales_sales_periods
   where sysdate between first_day and last_day
  )
  loop
     :P14_END_QTR := to_char(c2.last_day,'YYYYMMDD');
  end loop;
end;
```

## Set Username Format Preference  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Username Format
```plsql
eba_sales_acl_api.set_preference_value (
    p_preference_name  => 'USERNAME_FORMAT',
    p_preference_value => :P15_USERNAME_FORMAT);
```

## Add User to Collection  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: New User Details
```plsql
apex_collection.add_member(
    p_collection_name => 'NEW_USERS',
    p_c001            => lower(:P21_USERNAME),
    p_n001            => :P21_ACCESS_LEVEL_ID);
```

## Update User in Collection  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: New User Details
```plsql
apex_collection.update_member(
    p_collection_name => 'NEW_USERS',
    p_c001            => lower(:P21_USERNAME),
    p_n001            => :P21_ACCESS_LEVEL_ID,
    p_seq             => :P21_SEQUENCE);
```

## Remove User from Collection  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: New User Details
```plsql
apex_collection.delete_member(p_collection_name => 'NEW_USERS', p_seq => :P21_SEQUENCE);
```

## Proxy P22_ENTITY_ID on create  [NATIVE_PLSQL @ ON_SUBMIT_BEFORE_COMPUTATION] — page: Comment Details
```plsql
apex_util.set_session_state('P22_' || :P22_ENTITY_TYPE || '_ID', :P22_ENTITY_ID);
```

## Init page  [NATIVE_PLSQL @ AFTER_HEADER] — page: Contact
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
  entity_type,
  contact_id,
    app_username
) values (
  'CONTACT',
  :P24_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and contact_id = :P24_ID;
```

## ENABLE_ACCESS_CONTROL  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Administration
_tables: ['EBA_SALES_USERS']_
```plsql
-- Set AC flag
eba_sales_acl_api.set_preference_value('ACCESS_CONTROL_ENABLED','Y');
-- Seed user table with current user as an administrator or set the current user as administrator
declare
   l_user_exists boolean := false;
   l_access_level_id number := null;
begin
   for c1 in (select access_level_id
              from eba_sales_users
              where username = :APP_USER)
   loop
     l_user_exists := true;
     l_access_level_id := c1.access_level_id;
   end loop;

   if not l_user_exists then
       insert into eba_sales_users(username, access_level_id) values (:APP_USER, 3);   
   else
       if nvl(l_access_level_id,0) != 3 then
          update eba_sales_users
          set access_level_id = 3
          where username = :APP_USER;
       end if;
   end if;
end;
```

## Save Preference Values  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Application Preferences
```plsql
eba_sales_fw.set_preference_value('REP_TITLE', :P35_REP_TITLE);

:REP_TITLE := apex_escape.html(eba_sales_fw.get_preference_value('REP_TITLE'));

eba_sales_fw.set_preference_value('REP_TITLE_RAW', :P35_REP_TITLE);

:REP_TITLE_RAW := eba_sales_fw.get_preference_value('REP_TITLE_RAW');

eba_sales_fw.set_preference_value('SALES_LDR_TITLE', :P35_SALES_LDR_TITLE);

:SALES_LDR_TITLE := apex_escape.html(eba_sales_fw.get_preference_value('SALES_LDR_TITLE'));
```

## set timezone  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Time Zone Preference
_tables: ['EBA_SALES_TZ_PREF']_
```plsql
declare
   c integer := 0;
begin
   for c1 in (select id, timezone_preference 
              from eba_sales_tz_pref 
              where userid = :APP_USER) loop
      update eba_sales_tz_pref
      set timezone_preference = nvl(:P43_TIMEZONE,'UTC')
      where id = c1.id;
      c := c + 1;
   end loop;
   if c = 0 then
      insert into eba_sales_tz_pref (userid, timezone_preference)
      values (:APP_USER,:P43_TIMEZONE);
   end if;
   APEX_UTIL.SET_SESSION_TIME_ZONE (  
          P_TIME_ZONE => :P43_TIMEZONE); 
   commit;
end;
```

## Set Application Title  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Rename Application
_tables: ['DUAL', 'EBA_SALES_PREFERENCES', 'SET']_
```plsql
:APPLICATION_TITLE := :P45_APPLICATION_TITLE;

merge into eba_sales_preferences dst
using ( select 'APPLICATION_TITLE' preference_name, :P45_APPLICATION_TITLE preference_value from dual ) src
on ( dst.preference_name = src.preference_name )
when matched then
    update set dst.preference_value = src.preference_value
when not matched then
    insert ( preference_name, preference_value )
    values ( src.preference_name, src.preference_value );

merge into eba_sales_preferences dst
using ( select 'APPLICATION_SUBTITLE' preference_name, :P45_APPLICATION_SUBTITLE preference_value from dual ) src
on ( dst.preference_name = src.preference_name )
when matched then
    update set dst.preference_value = src.preference_value
when not matched then
    insert ( preference_name, preference_value )
    values ( src.preference_name, src.preference_value );
```

## Init page  [NATIVE_PLSQL @ AFTER_HEADER] — page: Product
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
  entity_type,
  product_id,
    app_username
) values (
  'PRODUCT',
  :P61_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and product_id = :P61_ID;
```

## convert lead to opportunity  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Convert to Opportunity
_tables: ['EBA_SALES_DEALS', 'EBA_SALES_DEAL_NOTES', 'EBA_SALES_LEADS', 'LEAD', 'L_ID', 'L_SALES_LEAD_REC']_
```plsql
declare

  l_id             number;
  l_sales_lead_rec eba_sales_leads%rowtype;
  l_message        varchar2(4000);

begin

  insert into eba_sales_deals (
    deal_name,
    customer_id,
    salesrep_id_01,
    deal_amount,
    deal_close_date,
    deal_status_code_id
  ) values (
    :P63_OPPORTUNITY,
    :P63_ACCOUNT,
    :P63_SALES_REP,
    :P63_AMOUNT,
    to_date(:P63_CLOSE_DATE,'DD-MON-YYYY'),
    :P63_STATUS
  )
  returning id 
  into l_id;

  update eba_sales_leads 
  set opportunity_id = l_id, 
    lead_status_id = 5 
  where id = :P63_LEAD_ID;
/*
  select *
  into l_sales_lead_rec
  from eba_sales_leads 
  where id = :P63_LEAD_ID;

  l_message := 'converted from lead ' || l_sales_lead_rec.row_key;

  insert into eba_sales_deal_notes(
    deal_id,
    note
  ) values (
    l_id,
    l_message
  );
 */
end;
```

## create opportunity  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Create Opportunity
_tables: ['EBA_SALES_CUSTOMERS', 'EBA_SALES_DEALS', 'EBA_SALES_DEAL_COMPETITION', 'EBA_SALES_DEAL_PRODUCTS', 'EBA_SALES_DEAL_TEAM', 'L_ACCOUNT_ID', 'L_OPP_ID', 'THE']_
```plsql
declare
    l_account_id   number;
    l_opp_id       number;
    
    la_product     apex_application_global.vc_arr2;
    la_team        apex_application_global.vc_arr2;
    la_competition apex_application_global.vc_arr2;
begin
    if :P71_NEW_OR_EXISTING = 'NEW' then
        insert into eba_sales_customers (
        customer_name,
        customer_territory_id,
        customer_web_site,
        customer_duns,
        customer_sic,
        customer_stock_symb,
        customer_is_key_account_yn,
        default_rep_id,
        customer_description,
        tags              
        )
        values (
        :P71_CUSTOMER_NAME,
        :P71_TERRITORY_ID,
        :P71_CUSTOMER_WEB_SITE,
        :P71_CUSTOMER_DUNS,
        :P71_CUSTOMER_SIC,
        :P71_CUSTOMER_STOCK_SYMB,
        :P71_CUSTOMER_IS_KEY_ACCOUNT_YN,
        :P71_DEFAULT_REP_ID,
        :P71_CUSTOMER_DESCRIPTION,
        :P71_TAGS
        ) returning id into l_account_id;
    else
        l_account_id := :P71_ACCOUNT;
    end if;
    
    insert into EBA_SALES_DEALS (
    DEAL_NAME,
    CUSTOMER_ID,
    SALESREP_ID_01,
    DEAL_AMOUNT,
    DEAL_CLOSE_DATE,
    DEAL_STATUS_CODE_ID,
    SPONSOR_CONTACT_ID,
    VP_ID,
    DEAL_SUMMARY,
    TAGS,
    SVP_ID
    )
    values (
    :P71_OPPORTUNITY_NAME,
    l_account_id,
    :P71_SALESREP,
    :P71_AMOUNT,
    :P71_CLOSE_DATE,
    :P71_STATUS,
    :P71_SPONSOR_CONTACT_ID,
    :P71_SVP,
    :P71_DEAL_SUMMARY,
    :P71_OPP_TAGS,
    :P71_SVP
    )
    returning id into l_opp_id;
    
    :P71_OPP_ID := l_opp_id; -- used to branch later
    
-- The code below is remarked out because this functionality was removed from the wizard
-- Allan 21-NOV-2016
/*
    -- add products
    if :P73_PRODUCTS is not null then
        la_product := apex_util.string_to_table(:P73_PRODUCTS);
        for i in 1..la_product.count
        loop
            insert into eba_sales_deal_products (deal_id, product_id) values (l_opp_id, la_product(i));
        end loop;
    end if;
  
    -- team
    if :P72_TEAM is not null then
        la_team := apex_util.string_to_table(:P72_TEAM);
        for i in 1..la_team.count
        loop
            insert into eba_sales_deal_team (deal_id, REP_ID) values (l_opp_id, la_team(i));
        end loop;
    end if;

    -- competition
    if :P72_COMPETITION is not null then
        la_competition := apex_util.string_to_table(:P72_COMPETITION);
        for i in 1..la_competition.count
        loop
            insert into eba_sales_deal_competition (deal_id, competitor_id) values (l_opp_id, la_competition(i));
        end loop;
    end if;
*/
end;
```

## close as lost  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Close Opportunity
_tables: ['EBA_SALES_DEALS', 'EBA_SALES_DEAL_STATUS_CODES']_
```plsql
for c1 in (
select id
from EBA_SALES_DEAL_STATUS_CODES
where CORRESPONDING_PROB_PCT = 0) loop

update EBA_SALES_DEALS 
set DEAL_STATUS_CODE_ID = c1.id, DEAL_PROBABILITY = 0
where id = :P79_ID;

end loop;
commit;
```

## close as won  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Close Opportunity
_tables: ['EBA_SALES_DEALS', 'EBA_SALES_DEAL_STATUS_CODES']_
```plsql
for c1 in (
select id
from EBA_SALES_DEAL_STATUS_CODES
where CORRESPONDING_PROB_PCT = 100) loop

update EBA_SALES_DEALS 
set DEAL_STATUS_CODE_ID = c1.id ,
    DEAL_CLOSE_DATE = least (sysdate, deal_close_date),
    DEAL_PROBABILITY = 100
where id = :P79_ID;

end loop;
commit;
```

## Init page  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Opportunity
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
    entity_type,
    opp_id,
    app_username  
) values (
    'OPPORTUNITY',
    :P80_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and opp_id = :P80_ID;
```

## Init Page  [NATIVE_PLSQL @ AFTER_HEADER] — page: Territory
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
  entity_type,
  territory_id,
    app_username
) values (
  'TERRITORY',
  :P93_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and territory_id = :P93_ID;
```

## Init page  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Account
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
  entity_type,
  cust_id,
    app_username
) values (
  'ACCOUNT',
  :P94_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and cust_id = :P94_ID;
```

## Proxy P99_ENTITY_ID on create  [NATIVE_PLSQL @ ON_SUBMIT_BEFORE_COMPUTATION] — page: Attachment Details
```plsql
apex_util.set_session_state('P99_' || :P99_ENTITY_TYPE || '_ID', :P99_ENTITY_ID);
```

## Set Username Cookie  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Login
```plsql
apex_authentication.send_login_username_cookie (
    p_username => lower(:P101_USERNAME) );
```

## Login  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Login
```plsql
apex_authentication.login(
    p_username => :P101_USERNAME,
    p_password => :P101_PASSWORD );
```

## Get Username Cookie  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Login
```plsql
:P101_USERNAME := apex_authentication.get_login_username_cookie;
```

## Update  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Build Options
_tables: ['APEX_APPLICATION_BUILD_OPTIONS']_
```plsql
for i in 1..apex_application.g_f01.count loop
    for c1 in ( select application_id, build_option_name, build_option_status
                from apex_application_build_options
                where apex_application.g_f01(i) = build_option_id
                   and application_Id = :APP_ID) loop
        if c1.build_option_status != apex_application.g_f03(i) then
            apex_util.set_build_option_status(  p_application_id => :APP_ID,
                                                p_id => apex_application.g_f01(i),
                                                p_build_status => upper(apex_application.g_f03(i)) );
        end if;
        if c1.build_option_name = 'Opportunity Amount Set at Product Level' and upper(apex_application.g_f03(i)) = 'EXCLUDE' then
            :AMT_HDR := 'Amount';
        elsif c1.build_option_name = 'Opportunity Amount Set at Product Level' and upper(apex_application.g_f03(i)) = 'INCLUDE' then
            :AMT_HDR := 'Annual Recurring Revenue';
        end if;
    end loop;
end loop;
```

## Proxy P114_ENTITY_ID on create  [NATIVE_PLSQL @ ON_SUBMIT_BEFORE_COMPUTATION] — page: Link Details
```plsql
apex_util.set_session_state('P114_' || :P114_ENTITY_TYPE || '_ID', :P114_ENTITY_ID);
```

## add country  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Country Details
_tables: ['EBA_SALES_TERR_MAP']_
```plsql
insert into eba_sales_terr_map
(territory_id, country_id)
values
(:P124_TERRITORY_ID, :P124_COUNTRY);
```

## Add state  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: State Details
_tables: ['EBA_SALES_TERR_MAP']_
```plsql
insert into eba_sales_terr_map
(territory_id, state_id)
values
(:P126_TERRITORY_ID, :P126_STATE);
```

## Init page  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Lead
_tables: ['EBA_SALES_CLICKS']_
```plsql
insert into eba_sales_clicks (
  entity_type,
  lead_id,
    app_username
) values (
  'LEAD',
  :P133_ID,
    lower(:APP_USER)
);

delete from eba_sales_clicks 
where view_timestamp < (sysdate - 90) 
  and lead_id = :P133_ID;
```

## Set Theme Style  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Application Appearance
_tables: ['APEX_APPLICATION_THEMES']_
```plsql
if :P141_DESKTOP_THEME_STYLE_ID is not null then
    for c1 in (select theme_number
               from apex_application_themes
               where application_id = :app_id
               and ui_type_name   = 'DESKTOP'
               and is_current = 'Yes')
    loop
        apex_theme.set_current_style (
            p_theme_number   => c1.theme_number,
            p_id => :P141_DESKTOP_THEME_STYLE_ID
            );
    end loop;
end if;
```

## Enable / Disable End User Style  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Application Appearance
_tables: ['APEX_APPLICATION_THEMES']_
```plsql
declare
  l_enabled boolean := case when :P141_END_USER_STYLE = 'Yes' then true else false end;
begin
  for c1 in (
    select ui.theme_number
      from apex_application_themes t, apex_applications ui
     where ui.application_id = t.application_id 
       and ui.theme_number   = t.theme_number 
       and t.application_id  = :app_id
       and t.is_current      = 'Yes'
  ) loop
    if l_enabled then 
      apex_theme.enable_user_style ( p_application_id => :APP_ID, p_theme_number => c1.theme_number );
    else
      apex_theme.disable_user_style ( p_application_id => :APP_ID, p_theme_number => c1.theme_number );
      apex_theme.clear_all_users_style(:APP_ID);
    end if; 
  end loop;
end;
```

## reset data  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Manage Sample Data
```plsql
eba_sales_data.remove_sample;
eba_sales_data.load_sample;
```

## remove sample data  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Manage Sample Data
```plsql
eba_sales_data.remove_sample;
```

## Load Sample Data  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Manage Sample Data
```plsql
eba_sales_data.load_sample;
```

## Create validation  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Validation Details
_tables: ['EBA_SALES_VERIFICATIONS']_
```plsql
declare

  l_verification_rec eba_sales_verifications%rowtype;

begin

  l_verification_rec.verification_comment := :P146_VERIFICATION_COMMENT;
  l_verification_rec.entity_type := :P146_ENTITY_TYPE;
  l_verification_rec.verified_by := lower(:APP_USER);

  case :P146_ENTITY_TYPE
    when 'LEAD'
    then
      l_verification_rec.lead_id := :P146_ENTITY_ID;
    when 'OPPORTUNITY'
    then
      l_verification_rec.opp_id := :P146_ENTITY_ID;
    when 'ACCOUNT'
    then
      l_verification_rec.cust_id := :P146_ENTITY_ID;
    when 'TERRITORY'
    then
      l_verification_rec.territory_id := :P146_ENTITY_ID;
    when 'CONTACT'
    then
      l_verification_rec.contact_id := :P146_ENTITY_ID;
    when 'PRODUCT'
    then
      l_verification_rec.product_id := :P146_ENTITY_ID;
  end case;
  
  
  insert into eba_sales_verifications values l_verification_rec;

end;
```

## Init page  [NATIVE_PLSQL @ BEFORE_HEADER] — page: Validation Details
```plsql
:P146_ENTITY_TYPE_LOWER := lower(:P146_ENTITY_TYPE);
```

## ACCESS CONTROL ENABLED  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Access Control Configuration
_tables: ['EBA_SALES_USERS', 'L_COUNT']_
```plsql
begin
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_ENABLED',
        p_preference_value => :P151_AC_ENABLED);
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_SCOPE',
        p_preference_value => (case 
                                   when :P151_AC_ENABLED = 'Y' then :P151_ACCESS_CONTROL_SCOPE
                                   else 'ACL_ONLY' 
                               end) );

    -- Seed user table with current user as an administrator or set the current user as administrator
    declare
       l_count number;
    begin
        select count(*) 
            into l_count 
        from eba_sales_users
        where username = :APP_USER;
        if l_count = 0 then
            insert into eba_sales_users(username, access_level_id) values (:APP_USER, 3);   
        else
            update eba_sales_users
            set access_level_id = 3
            where username = :APP_USER;
        end if;
    end;
end;
```

## ACCESS CONTROL DISABLED  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Access Control Configuration
```plsql
begin
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_ENABLED',
        p_preference_value => :P151_AC_ENABLED);
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_SCOPE',
        p_preference_value => (case 
                                   when :P151_AC_ENABLED = 'Y' then :P151_ACCESS_CONTROL_SCOPE
                                   else 'ACL_ONLY' 
                               end) );
end;
```

## ACCESS CONTROL UNCHANGED  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Access Control Configuration
```plsql
begin
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_ENABLED',
        p_preference_value => :P151_AC_ENABLED);
    eba_sales_acl_api.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_SCOPE',
        p_preference_value => (case 
                                   when :P151_AC_ENABLED = 'Y' then :P151_ACCESS_CONTROL_SCOPE
                                   else 'ACL_ONLY' 
                               end) );
end;
```

## Set Username Format  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Access Control Configuration
```plsql
eba_sales_acl_api.set_preference_value (
    p_preference_name  => 'USERNAME_FORMAT',
    p_preference_value => case nvl(:P151_USERNAME_FORMAT,'N') 
                            when 'Y' then 'EMAIL'
                            when 'N' then 'STRING' 
                          end);
```

## Create Collections  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Add Multiple Users
_tables: ['EBA_SALES_USERS', 'L_USERNAME', 'WWV_FLOW_COLLECTIONS']_
```plsql
declare
    l_line      varchar2(32767);
    l_emails    wwv_flow_global.vc_arr2;
    l_username  varchar2(4000);
    l_at        number;
    l_dot       number;
    l_valid     boolean := true;
    l_domain    varchar2(4000);
begin
    ---------------------
    -- create collections
    --
    apex_collection.CREATE_OR_TRUNCATE_COLLECTION ('EBA_SALES_BULK_USER_INVALID');
    apex_collection.CREATE_OR_TRUNCATE_COLLECTION ('EBA_SALES_BULK_USER_VALID');
    apex_collection.CREATE_OR_TRUNCATE_COLLECTION ('EBA_SALES_BULK_USER_CREATE');

    --------------------------------------------
    -- replace delimiting characters with commas
    --
    l_line := :P153_PRELIM_USERS;
    l_line := replace(l_line,chr(10),' ');
    l_line := replace(l_line,chr(13),' ');
    l_line := replace(l_line,chr(9),' ');
    l_line := replace(l_line,'<',' ');
    l_line := replace(l_line,'>',' ');
    l_line := replace(l_line,';',' ');
    l_line := replace(l_line,':',' ');
    l_line := replace(l_line,'(',' ');
    l_line := replace(l_line,')',' ');
    l_line := replace(l_line,' ',',');

    -----------------------------------------
    -- get one comma separated line of emails
    --
    for j in 1..1000 loop
        if instr(l_line,',,') > 0 then
           l_line := replace(l_line,',,',',');
        else
           exit;
        end if;
    end loop;

    -------------------------
    -- get an array of emails
    --
    l_emails := wwv_flow_utilities.string_to_table(l_line,',');

    -----------------------------
    -- add emails to a collection
    --
    l_username := null;
    l_domain := null;
    l_at := 0;
    l_dot := 0;
    for j in 1..l_emails.count loop
        l_valid := true;
        l_username := trim(l_emails(j));

        if l_username is not null then
            if eba_sales_acl_api.get_preference_value('USERNAME_FORMAT') = 'EMAIL' then
              -----------
              -- Validate
              --
              l_at := instr(nvl(l_username,'x'),'@');
              l_domain := substr(l_username,l_at+1);
              l_dot := instr(l_domain,'.');
              if l_at < 2 then
                  -- invalid email
                  apex_collection.add_member(
                      p_collection_name => 'EBA_SALES_BULK_USER_INVALID',
                      p_c001            => l_username,
                      p_c002            => apex_lang.message('MISSING_AT_SIGN'));
                  commit;
                  l_valid := false;
              end if;

              if l_dot = 0 and l_valid then
                  apex_collection.add_member(
                      p_collection_name => 'EBA_SALES_BULK_USER_INVALID',
                      p_c001            => l_username,
                      p_c002            => apex_lang.message('MISSING_DOT'));
                  commit;
                  l_valid := false;
              end if;
            end if;

            l_username := trim(l_username);
            l_username := trim(both '.' from l_username);
            l_username := replace(l_username,' ',null);
            l_username := replace(l_username,chr(10),null);
            l_username := replace(l_username,chr(9),null);
            l_username := replace(l_username,chr(13),null);
            l_username := replace(l_username,chr(49824),null);

            if l_valid and length(l_username) > 255 then
                apex_collection.add_member(
                    p_collection_name => 'EBA_SALES_BULK_USER_INVALID',
                    p_c001            => upper(l_username),
                    p_c002            => apex_lang.message('USERNAME_TOO_LONG'));
                commit;
                l_valid := false;
            end if;

            if l_valid then
                for c1 in (select /* APEX76a66f */ username
                             from eba_sales_users
                            where upper(username) = upper(l_username)
                )
                loop
                    wwv_flow_collection.add_member(
                        p_collection_name => 'EBA_SALES_BULK_USER_INVALID',
                        p_c001            => upper(l_username),
                        p_c002            => apex_lang.message('ALREADY_IN_ACL'));
                    commit;
                    l_valid := false;
                    exit;
                end loop;
            end if;

            if l_valid then
                for c1 in (select /* APEXeaf772 */  c001
                             from wwv_flow_collections
                            where collection_name = 'EBA_SALES_BULK_USER_VALID'
                              and c001 = upper(l_username))
                loop
                    apex_collection.add_member(
                        p_collection_name => 'EBA_SALES_BULK_USER_INVALID',
                        p_c001            => upper(l_username),
                        p_c002            => apex_lang.message('DUPLICATE_USER'));
                        commit;
                    l_valid := false;
                    exit;
                end loop;
            end if;

            if l_valid then
                apex_collection.add_member(
                    p_collection_name => 'EBA_SALES_BULK_USER_VALID',
                    p_c001            => upper(l_username));
                    commit;
            end if;

        end if;
        l_username := null;
    end loop;
end;
```

## Add Users to ACL  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Add Multiple Users
_tables: ['APEX_COLLECTIONS', 'EBA_SALES_USERS']_
```plsql
for c in
(
    select
        c001       as username,
        :P153_ROLE as access_level_id
    from
        apex_collections
    where
        collection_name = 'EBA_SALES_BULK_USER_VALID'
)
loop
    insert into eba_sales_users
    (username, access_level_id)
    values
    (c.username, c.access_level_id);
end loop;

---------------------
-- delete collections
--
wwv_flow_collection.DELETE_COLLECTION('EBA_SALES_BULK_USER_INVALID');
wwv_flow_collection.DELETE_COLLECTION('EBA_SALES_BULK_USER_VALID');
wwv_flow_collection.DELETE_COLLECTION('EBA_SALES_BULK_USER_CREATE');
```

## Reset User Collection  [NATIVE_PLSQL @ AFTER_HEADER] — page: Getting Started
```plsql
apex_collection.truncate_collection(p_collection_name => 'NEW_USERS');
```

## Create NEW_USERS Collection  [NATIVE_PLSQL @ AFTER_HEADER] — page: Getting Started
```plsql
apex_collection.create_or_truncate_collection(p_collection_name => 'NEW_USERS');
```

## Add Current User to Collection  [NATIVE_PLSQL @ AFTER_HEADER] — page: Getting Started
```plsql
apex_collection.add_member(
    p_collection_name => 'NEW_USERS',
    p_c001            => lower(:APP_USER),
    p_n001            => 3);
```

## Set Username Format based on current user's username  [NATIVE_PLSQL @ AFTER_HEADER] — page: Getting Started
```plsql
if instr(:APP_USER,'@') > 0 then
    eba_sales_fw.set_preference_value ('USERNAME_FORMAT','EMAIL');
else
    eba_sales_fw.set_preference_value ('USERNAME_FORMAT','STRING');
end if;
```

## Process Page Data  [NATIVE_PLSQL @ AFTER_SUBMIT] — page: Getting Started
_tables: ['APEX_APPLICATION_BUILD_OPTIONS', 'APEX_COLLECTIONS', 'EBA_SALES_USERS']_
```plsql
begin
    -- Enable ACL
    eba_sales_fw.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_ENABLED',
        p_preference_value => 'Y' );
    
    -- Set ACL Scope
    eba_sales_fw.set_preference_value (
        p_preference_name  => 'ACCESS_CONTROL_SCOPE',
        p_preference_value => :P1000_ACL_CONFIG );

    -- Define Username Preference
    if instr(:APP_USER,'@') > 0 then
        eba_sales_fw.set_preference_value (
            p_preference_name  => 'USERNAME_FORMAT',
            p_preference_value => :P1000_USERNAME_FORMAT );
    end if;
    
    -- Add Users
    begin
        insert into eba_sales_users
        (username, access_level_id, account_locked)
        select
                c001 as username,
                n001 as access_level_id,
                'N'  as account_locked
            from
                apex_collections
            where
                collection_name = 'NEW_USERS'
            and
                lower(c001) not in (select distinct lower(username) from eba_sales_users);
    exception
      when others then
        null;
    end;

    -- Get rid of the collection
    apex_collection.delete_collection(p_collection_name => 'NEW_USERS');

    -- Load Sample Data
    if :P1000_LOAD_SAMPLE_YN = 'Y' then
        eba_sales_data.load_sample;
    end if;

    -- Set Build Options
    for i in 1..apex_application.g_f01.count
    loop
        for c1 in ( select application_id, build_option_name, build_option_status
                    from apex_application_build_options
                    where apex_application.g_f01(i) = build_option_id
                       and application_Id = :APP_ID)
        loop
            if c1.build_option_status != apex_application.g_f03(i) then
                apex_util.set_build_option_status(  p_application_id => :APP_ID,
                                                    p_id => apex_application.g_f01(i),
                                                    p_build_status => upper(apex_application.g_f03(i)) );
            end if;
        end loop;
    end loop;

    -- Set First Run to No
    eba_sales_fw.set_preference_value (
        p_preference_name  => 'FIRST_RUN',
        p_preference_value => 'NO' );
end;
```
