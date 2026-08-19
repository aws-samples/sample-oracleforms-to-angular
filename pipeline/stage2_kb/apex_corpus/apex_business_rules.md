# Business Rules — Validations (APEX Opportunities CRM)

Validation rules recovered from the APEX export. Each is a rule the modern system must preserve.

## P3_CUSTOMER_NAME not duplicated  (NOT_EXISTS) — page: Account Details
**Error message:** An account with that name already exists.
```sql
select null
from eba_sales_customers
where (:P3_ID is null or :P3_ID != id)
    and upper(customer_name) = upper(:P3_CUSTOMER_NAME)
```

## Valid Tag Characters  (EXPRESSION) — page: Account Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P3_TAGS, '[:;#\/\\\?\&]' )
```

## Website must start with http  (EXPRESSION) — page: Account Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P3_CUSTOMER_WEB_SITE, 1, 4) = 'http'
```

## LinkedIn must start with http  (EXPRESSION) — page: Account Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P3_CUSTOMER_LINKEDIN, 1, 4) = 'http'
```

## FB must start with http  (EXPRESSION) — page: Account Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P3_CUSTOMER_FACEBOOK, 1, 4) = 'http'
```

## Twitter must start with http  (EXPRESSION) — page: Account Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P3_CUSTOMER_TWITTER, 1, 4) = 'http'
```

## Valid Tag Characters  (EXPRESSION) — page: Product Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P5_TAGS, '[:;#\/\\\?\&]' )
```

## P9_TERRITORY_NAME not duplicated  (NOT_EXISTS) — page: Territory Details
**Error message:** A territory with that name already exists.
```sql
select null
from eba_sales_territories
where (:P9_ID is null or :P9_ID != id)
    and upper(territory_name) = upper(:P9_TERRITORY_NAME)
```

## Valid Tag Characters  (EXPRESSION) — page: Territory Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P9_TAGS, '[:;#\/\\\?\&]' )
```

## End after the beginning  (FUNC_BODY_RETURNING_BOOLEAN) — page: Fiscal Quarter Details
**Error message:** First and last dates must be in proper chronological order.
```sql
return to_date(:P13_FIRST_DAY,:APP_DATE_FORMAT) < to_date(:P13_LAST_DAY,:APP_DATE_FORMAT);
```

## Fiscal Year is Numeric  (ITEM_IS_NUMERIC) — page: Fiscal Quarter Details
**Error message:** #LABEL# must be a numeric value.
```sql
P13_FISCAL_YEAR
```

## Quarter is Valid  (EXPRESSION) — page: Fiscal Quarter Details
**Error message:** Period Name must begin with Q1, Q2, Q3, or Q4.
```sql
substr(:P13_PERIOD_NAME,1,2) in ('Q1','Q2','Q3','Q4','q1','q2','q3','q4')
```

## End >= Begin  (EXPRESSION) — page: Revenue by Quarter
**Error message:** Ending Quarter must be greater than or equal to Beginning Quarter.
```sql
to_date(:P14_END_QTR,'YYYYMMDD') >= to_date(:P14_BEGIN_QTR,'YYYYMMDD')
```

## P16_DEAL_STATUS_CODE_ID not in (4, 11)  (EXPRESSION) — page: Opportunity Details
**Error message:** Use the Close Won/Lost button to set #LABEL# to a "closed" value.
```sql
:P16_DEAL_STATUS_CODE_ID in ('4', '11')
```

## P16_DEAL_PROBABILITY is not 0 or 100  (EXPRESSION) — page: Opportunity Details
**Error message:** Use the Close Won/Lost button to set #LABEL# to 0 or 100.
```sql
:P16_DEAL_PROBABILITY in ('0', '100')
```

## P16_DEAL_AMOUNT Not Null  (ITEM_NOT_NULL) — page: Opportunity Details
**Error message:** #LABEL# must have some value.
```sql
P16_DEAL_AMOUNT
```

## Valid Tag Characters  (EXPRESSION) — page: Opportunity Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P16_TAGS, '[:;#\/\\\?\&]' )
```

## cannot update yourself  (NOT_EXISTS) — page: New User Details
**Error message:** You cannot update your own record.
```sql
select 1
  from eba_sales_users
 where upper(username) = :APP_USER
   and upper(username) = upper(:P21_USERNAME)
```

## P21_USERNAME Email is Valid  (REGULAR_EXPRESSION) — page: New User Details
**Error message:** Username is not in a valid email address format. Please note the application's username format below.
```sql
P21_USERNAME
```

## Username is unique  (NOT_EXISTS) — page: New User Details
**Error message:** This username has already been added. Please enter a unique username.
```sql
select
    null
from
    apex_collections
where
    collection_name = 'NEW_USERS'
and
    lower(c001) = lower(:P21_USERNAME)
and
    :P21_SEQUENCE is null;
```

## P27_COMPETITOR_ID not duplicated  (NOT_EXISTS) — page: Competition Details
**Error message:** Selected competition already exists for this opportunity.
```sql
select null
from eba_sales_deal_competition
where deal_id = :P27_DEAL_ID
    and competitor_id = :P27_COMPETITOR_ID
    and (:P27_ID is null or id != :P27_ID)
```

## Valid Tag Characters  (EXPRESSION) — page: Lead Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P29_TAGS, '[:;#\/\\\?\&]' )
```

## P30_REP_ID not duplicated  (NOT_EXISTS) — page: Team Member Details
**Error message:** Selected team member is already associated with this opportunity.
```sql
select null
from eba_sales_deal_team
where ( :P30_ID is null or id = :P30_ID )
    and deal_id = :P30_DEAL_ID
    and rep_id = :P30_REP_ID
```

## Valid Tag Characters  (EXPRESSION) — page: Competitor Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P52_TAGS, '[:;#\/\\\?\&]' )
```

## URL1 must start with http  (EXPRESSION) — page: Competitor Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P52_URL_1, 1, 4) = 'http'
```

## URL2 must start with http  (EXPRESSION) — page: Competitor Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P52_URL_2, 1, 4) = 'http'
```

## URL3 must start with http  (EXPRESSION) — page: Competitor Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P52_URL_3, 1, 4) = 'http'
```

## URL4 must start with http  (EXPRESSION) — page: Competitor Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P52_URL_4, 1, 4) = 'http'
```

## Lead Source not used  (NOT_EXISTS) — page: Lead Source Details
**Error message:** Unable to delete while leads use this source.
```sql
select 1
from eba_sales_leads
where lead_source_id = :P70_ID
```

## P71_ACCOUNT not null when existing  (ITEM_NOT_NULL) — page: Create Opportunity
**Error message:** #LABEL# must have some value.
```sql
P71_ACCOUNT
```

## P71_CUSTOMER_NAME not null when new  (ITEM_NOT_NULL) — page: Create Opportunity
**Error message:** #LABEL# must have some value.
```sql
P71_CUSTOMER_NAME
```

## P71_OPPORTUNITY_NAME not duplicated  (NOT_EXISTS) — page: Create Opportunity
**Error message:** An opportunity with that name already exists.
```sql
select null
from eba_sales_deals
where upper(deal_name) = upper(:P71_OPPORTUNITY_NAME)
```

## P71_CUSTOMER_NAME not duplicated  (NOT_EXISTS) — page: Create Opportunity
**Error message:** An account with that name already exists.
```sql
select null
from eba_sales_customers
where upper(customer_name) = upper(:P71_CUSTOMER_NAME)
```

## P71_TERRITORY_ID not null  (ITEM_NOT_NULL) — page: Create Opportunity
**Error message:** #LABEL# must have some value.
```sql
P71_TERRITORY_ID
```

## Valid Tag Characters  (EXPRESSION) — page: Create Opportunity
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P71_TAGS, '[:;#\/\\\?\&]' )
```

## Valid Tag Characters Opportunity  (EXPRESSION) — page: Create Opportunity
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P71_OPP_TAGS, '[:;#\/\\\?\&]' )
```

## P78_DISPLAY_FROM must be timestamp  (ITEM_IS_TIMESTAMP) — page: Notification Details
**Error message:** #LABEL# must be a valid timestamp.
```sql
P78_DISPLAY_FROM
```

## P78_DISPLAY_UNTIL must be timestamp  (ITEM_IS_TIMESTAMP) — page: Notification Details
**Error message:** #LABEL# must be a valid timestamp.
```sql
P78_DISPLAY_UNTIL
```

## End after the beginning  (FUNC_BODY_RETURNING_BOOLEAN) — page: Notification Details
**Error message:** Display From and To dates must be in proper chronological order.
```sql
if :P78_DISPLAY_FROM is not null and :P78_DISPLAY_UNTIL is not null then
    return to_timestamp(:P78_DISPLAY_FROM,'DD-MON-YYYY HH24:MI:SS') < to_timestamp(:P78_DISPLAY_UNTIL,'DD-MON-YYYY HH24:MI:SS');
else
    return true;
end if;
```

## P99_FILE_BLOB is not null  (ITEM_NOT_NULL) — page: Attachment Details
**Error message:** #LABEL# must have some value.
```sql
P99_FILE_BLOB
```

## Valid Tag Characters  (EXPRESSION) — page: Contact Details
**Error message:** Tags may not contain the following characters: : ; \ / ? &
```sql
not regexp_like( :P106_TAGS, '[:;#\/\\\?\&]' )
```

## LinkedIn must start with http  (EXPRESSION) — page: Contact Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P106_CONTACT_LINKEDIN, 1, 4) = 'http'
```

## FB must start with http  (EXPRESSION) — page: Contact Details
**Error message:** Please provide a URL that begins with, "http".
```sql
substr(:P106_CONTACT_FACEBOOK, 1, 4) = 'http'
```

## P108_PRODUCT_ID not duplicated  (NOT_EXISTS) — page: Product Details
**Error message:** Product is already associated with this deal.
```sql
select null
  from eba_sales_deal_products
 where deal_id = :P108_DEAL_ID
   and product_id = :P108_PRODUCT_ID
   and (:P108_ID is null or id != :P108_ID)
```

## P108_PRODUCT_ID & P108_CLOSE_DATE not duplicated  (NOT_EXISTS) — page: Product Details
**Error message:** Product is already associated with this deal.
```sql
select null
  from eba_sales_deal_products
 where deal_id = :P108_DEAL_ID
   and product_id = :P108_PRODUCT_ID
   and close_date = :P108_CLOSE_DATE
   and (:P108_ID is null or id != :P108_ID)
```

## P108_QUOTE_PRICE is numeric  (ITEM_IS_NUMERIC) — page: Product Details
**Error message:** #LABEL# must contain a numeric value (other than commas and a dollar sign).
```sql
P108_QUOTE_PRICE
```

## P108_TCV is numeric  (ITEM_IS_NUMERIC) — page: Product Details
**Error message:** #LABEL# must contain a numeric value (other than commas and a dollar sign).
```sql
P108_TCV
```

## P114_LINK_TARGET valid URL  (REGULAR_EXPRESSION) — page: Link Details
**Error message:** Invalid URL
```sql
P114_LINK_TARGET
```

## P114 link not duplicated  (NOT_EXISTS) — page: Link Details
**Error message:** Provided link already exists.
```sql
select null
from eba_sales_links
where (:P114_ID is null or id != :P114_ID)
  and (
    (:P114_ENTITY_TYPE = 'OPPORTUNITY' and deal_id = :P114_OPPORTUNITY_ID)
      or (:P114_ENTITY_TYPE = 'LEAD' and lead_id = :P114_LEAD_ID)
      or (:P114_ENTITY_TYPE = 'TERRITORY' and territory_id = :P114_TERRITORY_ID)
      or (:P114_ENTITY_TYPE = 'ACCOUNT' and account_id = :P114_ACCOUNT_ID)
      or (:P114_ENTITY_TYPE = 'CONTACT' and contact_id = :P114_CONTACT_ID)
      or (:P114_ENTITY_TYPE = 'PRODUCT' and product_id = :P114_PRODUCT_ID)
  )
  and upper(link_target) = upper(:P114_LINK_TARGET)
```

## cannot update yourself  (NOT_EXISTS) — page: User Access Control  
**Error message:** You cannot update your own record.
```sql
select null
from eba_sales_users
where upper(username) = :APP_USER
    and id = :P119_ID
    and ( username <> :P119_USERNAME
        or access_level_id <> :P119_ACCESS_LEVEL_ID
        or account_locked <> :P119_ACCOUNT_LOCKED )
```

## P119_USERNAME valid format (email)  (REGULAR_EXPRESSION) — page: User Access Control  
**Error message:** Username is not in a valid email address format. Please note the application's username format below.
```sql
P119_USERNAME
```

## Filename is not null  (ITEM_NOT_NULL) — page: Data Load Source
**Error message:** #LABEL# must have some value.
```sql
P136_FILE_NAME
```

## Uploaded data is not null  (ITEM_NOT_NULL) — page: Data Load Source
**Error message:** #LABEL# must have some value.
```sql
P136_COPY_PASTE
```

## P145_COMPETITOR_ID not duplicated  (NOT_EXISTS) — page: Competition Details
**Error message:** Selected competition already exists for this opportunity.
```sql
select null
from EBA_SALES_ACT_COMPETITION
where customer_id = :P145_CUSTOMER_ID
    and competitor_id = :P145_COMPETITOR_ID
    and (:P145_ID is null or id != :P145_ID)
```

## P146_I_VALIDATE is not null  (ITEM_NOT_NULL) — page: Validation Details
**Error message:** Please check to validate.
```sql
P146_I_VALIDATE
```

## Filename is not null  (ITEM_NOT_NULL) — page: Data Load Source
**Error message:** #LABEL# must have some value.
```sql
P210_FILE_NAME
```

## Paste buffer is not null  (ITEM_NOT_NULL) — page: Data Load Source
**Error message:** #LABEL# must have some value.
```sql
P210_COPY_PASTE
```
