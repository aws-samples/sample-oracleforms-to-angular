import { chromium } from 'playwright';
const ALL = [
  {id:'valid_all',      name:'BrowsertestAlpha Co', tags:'vip gold', web:'http://a.com'},
  {id:'dup_name',       name:'Madison Materials',   tags:'', web:''},
  {id:'tag_hash',       name:'BrowsertestBeta Co',  tags:'vip#gold', web:''},
  {id:'tag_slash',      name:'BrowsertestGamma Co', tags:'a/b', web:''},
  {id:'tag_clean_dot',  name:'BrowsertestDelta Co', tags:'abc.def', web:''},
  {id:'url_ftp',        name:'BrowsertestEps Co',   tags:'', web:'ftp://x.com'},
  {id:'url_upper_HTTP', name:'BrowsertestZeta Co',  tags:'', web:'HTTP://x.com'},
  {id:'url_empty_ok',   name:'BrowsertestEta Co',   tags:'', web:''},
];
const batch = process.argv[2]==='2' ? ALL.slice(4) : ALL.slice(0,4);
const b = await chromium.launch();
const pg = await (await b.newContext()).newPage();
await pg.goto('http://localhost:8080/ords/r/sample-app/opportunities/login',{waitUntil:'networkidle',timeout:20000});
// Set APEX_ADMIN_PASSWORD env var to the APEX admin password before running.
await pg.fill('#P101_USERNAME','ADMIN'); await pg.fill('#P101_PASSWORD', process.env.APEX_ADMIN_PASSWORD || '<YOUR_APEX_PASSWORD>');
await Promise.all([pg.waitForURL(u=>!String(u).includes('/login'),{timeout:20000}).catch(()=>{}), pg.click('#B8992829647740156794')]);
const sess=new URL(pg.url()).searchParams.get('session');

for(const c of batch){
  try{
    await pg.goto(`http://localhost:8080/ords/r/sample-app/opportunities/accounts?session=${sess}`,{waitUntil:'networkidle',timeout:20000});
    await pg.click('#B10497111976710073032'); await pg.waitForTimeout(2000);
    let fr=pg.frames().find(f=>f.url().includes('account-details'));
    await fr.fill('#P3_CUSTOMER_NAME', c.name).catch(()=>{});
    if(c.tags) await fr.fill('#P3_TAGS', c.tags).catch(()=>{});
    if(c.web)  await fr.fill('#P3_CUSTOMER_WEB_SITE', c.web).catch(()=>{});
    // satisfy the required Territory (popup LOV) by setting its item value via APEX JS
    await fr.evaluate(()=>{ try{ apex.item('P3_CUSTOMER_TERRITORY_ID').setValue('1','US Commercial East'); }catch(e){} });
    const createBtn = await fr.$('button:has-text("Create"), button.t-Button--hot');
    await createBtn?.click().catch(()=>{});
    await pg.waitForTimeout(2500);
    fr=pg.frames().find(f=>f.url().includes('account-details'));
    let errs=[];
    if(fr){
      errs = await fr.$$eval('.t-Form-error, li.a-Notification-item, ul.htmldbUlErr li, .t-Alert-content li, span.t-Form-error',
        els=>[...new Set(els.map(e=>e.textContent.trim()).filter(Boolean))]).catch(()=>[]);
    }
    // ignore the Territory error if it still leaks; we care about name/tag/url
    errs = errs.filter(e=>!/territory/i.test(e));
    const stillOpen = !!pg.frames().find(f=>f.url().includes('account-details'));
    const decision = errs.length ? 'FAIL' : (stillOpen ? 'PASS(dlg-open,no-target-err)' : 'PASS');
    console.log('BROWSER::'+c.id+'::'+decision+'::'+errs.join(' | '));
  }catch(e){ console.log('BROWSER::'+c.id+'::ERR::'+e.message.slice(0,60)); }
}
await b.close();
