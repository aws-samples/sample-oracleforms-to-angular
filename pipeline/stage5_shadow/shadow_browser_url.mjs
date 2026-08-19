import { chromium } from 'playwright';
const CASES = [
  {id:'url_ftp',        name:'BrowserurlEps Co',   web:'ftp://x.com'},
  {id:'url_upper_HTTP', name:'BrowserurlZeta Co',  web:'HTTP://x.com'},
  {id:'url_ok_http',    name:'BrowserurlOk Co',    web:'http://good.com'},
];
const b = await chromium.launch();
const pg = await (await b.newContext()).newPage();
await pg.goto('http://localhost:8080/ords/r/sample-app/opportunities/login',{waitUntil:'networkidle',timeout:20000});
// Set APEX_ADMIN_PASSWORD env var to the APEX admin password before running.
await pg.fill('#P101_USERNAME','ADMIN'); await pg.fill('#P101_PASSWORD', process.env.APEX_ADMIN_PASSWORD || '<YOUR_APEX_PASSWORD>');
await Promise.all([pg.waitForURL(u=>!String(u).includes('/login'),{timeout:20000}).catch(()=>{}), pg.click('#B8992829647740156794')]);
const sess=new URL(pg.url()).searchParams.get('session');
for(const c of CASES){
  try{
    await pg.goto(`http://localhost:8080/ords/r/sample-app/opportunities/accounts?session=${sess}`,{waitUntil:'networkidle',timeout:20000});
    await pg.click('#B10497111976710073032'); await pg.waitForTimeout(2000);
    let fr=pg.frames().find(f=>f.url().includes('account-details'));
    // set all values through the APEX item API (reliable across collapsed regions)
    await fr.evaluate((c)=>{
      apex.item('P3_CUSTOMER_NAME').setValue(c.name);
      apex.item('P3_CUSTOMER_WEB_SITE').setValue(c.web);
      try{ apex.item('P3_CUSTOMER_TERRITORY_ID').setValue('1','US Commercial East'); }catch(e){}
    }, c);
    // verify the field really holds the value
    const val = await fr.evaluate(()=>apex.item('P3_CUSTOMER_WEB_SITE').getValue());
    const createBtn = await fr.$('button:has-text("Create"), button.t-Button--hot');
    await createBtn?.click().catch(()=>{});
    await pg.waitForTimeout(2500);
    fr=pg.frames().find(f=>f.url().includes('account-details'));
    let errs=[];
    if(fr) errs=await fr.$$eval('.t-Form-error, li.a-Notification-item, ul.htmldbUlErr li, .t-Alert-content li',
      els=>[...new Set(els.map(e=>e.textContent.trim()).filter(Boolean))]).catch(()=>[]);
    errs=errs.filter(e=>!/territory/i.test(e));
    const stillOpen=!!pg.frames().find(f=>f.url().includes('account-details'));
    console.log('BROWSER::'+c.id+'::webset="'+val+'"::'+(errs.length?'FAIL':(stillOpen?'PASS?':'PASS'))+'::'+errs.join(' | '));
  }catch(e){ console.log('BROWSER::'+c.id+'::ERR::'+e.message.slice(0,70)); }
}
await b.close();
