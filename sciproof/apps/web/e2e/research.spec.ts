import {test,expect,Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {readFile,writeFile,rename} from 'node:fs/promises';
import {resolve} from 'node:path';

const root=resolve(__dirname,'../../..');
const fixture=(name:string)=>resolve(root,'.runtime/e2e-fixtures',name);
const API='http://localhost:8000/api/v1';
const password='browser-evidence-password';
async function control(command:string,fields:Record<string,string>={}){
  const id=randomUUID(),directory=resolve(root,'.runtime/e2e-control');
  const temporary=resolve(directory,id+'.tmp');
  await writeFile(temporary,JSON.stringify({id,command,...fields}));
  await rename(temporary,resolve(directory,'request.json'));
  const resultFile=resolve(directory,'responses',id+'.json');
  await expect.poll(async()=>{try{return JSON.parse(await readFile(resultFile,'utf8')).status}catch{return 'waiting'}},{timeout:30000}).toBe('ok');
  return JSON.parse(await readFile(resultFile,'utf8')) as {status:string;error_code?:string};
}
async function register(page:Page){
  const email=`browser-${randomUUID()}@example.org`;
  await page.goto('/');await page.getByRole('button',{name:'Start a research project'}).click();
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Continue'}).click();
  await expect(page.getByRole('heading',{name:'Your research projects'})).toBeVisible();
  return email;
}
async function newVersion(page:Page,title='Browser research'){
  await page.getByLabel('New project title').fill(title);
  await page.getByRole('button',{name:'Create project',exact:true}).click();
  const project=page.locator('article').filter({has:page.getByRole('heading',{name:title,exact:true})});
  await project.getByRole('button',{name:'Upload a new version'}).click();
  await expect(page.getByRole('heading',{name:'Bring your evidence.'})).toBeVisible();
}
async function uploadInputs(page:Page,paper='paper.pdf'){
  await page.getByLabel('Manuscript PDF').setInputFiles(fixture(paper));
  await page.getByLabel('Dataset',{exact:true}).setInputFiles(fixture('data.csv'));
}
async function verify(page:Page){
  const response=page.waitForResponse(r=>r.url().endsWith('/verify')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Verify research'}).click();
  return response;
}
test.beforeAll(async({request})=>{
  const readiness=await request.get(API+'/health/ready');
  expect(readiness.status()).toBe(200);
  expect((await readiness.json()).verification_mode).toBe('celery');
});

test('complete persisted research workflow through actual broker',async({page})=>{
  const email=await register(page);await newVersion(page,'Persistent evidence');await uploadInputs(page);
  await control('pause-worker');
  try{
    const queued=await verify(page);expect(queued.status()).toBe(202);
    expect((await queued.json()).job_status).toBe('QUEUED');
    await expect(page.getByRole('status')).toHaveText('Run state: QUEUED');
  }finally{await control('resume-worker')}
  await expect(page.getByRole('heading',{name:'Overall grade: B'})).toBeVisible();
  await expect(page.getByText('statistical reproducibility',{exact:true})).toBeVisible();
  await page.locator('summary').first().click();
  await expect(page.getByRole('heading',{name:'Evidence',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Finding explanation'})).toBeVisible();
  await expect(page.getByText('Manuscript page 1 · Fields: x')).toBeVisible();
  const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Download audit report'}).click();
  const download=await downloadPromise;expect(download.suggestedFilename()).toBe('sciproof-report.json');
  const report=JSON.parse(await readFile((await download.path())!,'utf8'));
  expect(report.job_status).toBe('COMPLETED');expect(report.checks[0].outcome).toBe('SUPPORTED');
  expect(report.checks[0].artifact_id).toBeTruthy();expect(report.checks[0].evidence_id).toBeTruthy();
  await expect(page.getByText(report.provenance.provenance_hash,{exact:true})).toBeVisible();
  await page.screenshot({path:resolve(root,'.runtime/e2e-report.png')});
  await page.getByRole('button',{name:'Back to projects'}).click();
  await page.getByRole('button',{name:'View verification history'}).click();
  await expect(page.getByText('VERSION 1 · COMPLETED')).toBeVisible();
  await page.getByRole('button',{name:'Logout'}).click();
  await page.getByLabel('Email',{exact:true}).fill(email);await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Continue'}).click();
  await expect(page.getByRole('heading',{name:'Persistent evidence',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'View verification history'}).click();
  await page.getByRole('button',{name:'Open report'}).click();
  await expect(page.getByText(report.provenance.provenance_hash,{exact:true})).toBeVisible();
});

test('invalid login shows a safe error',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Sign in'}).click();
  await page.getByLabel('Email',{exact:true}).fill('missing@example.org');
  await page.getByLabel('Password',{exact:true}).fill('wrong-long-password');
  await page.getByRole('button',{name:'Continue'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toHaveText('Invalid credentials');
});

test('another browser account cannot access project or report',async({page,browser})=>{
  await register(page);await newVersion(page,'Owner only');await uploadInputs(page);
  const response=await verify(page);const rid=(await response.json()).id;
  await expect(page.getByRole('heading',{name:'Overall grade: B'})).toBeVisible();
  const projects=await page.evaluate(async api=>(await fetch(api+'/projects',{credentials:'include'})).json(),API);
  const context=await browser.newContext();const outsider=await context.newPage();await register(outsider);
  const codes=await outsider.evaluate(async({api,pid,rid})=>{
    const results=await Promise.all([fetch(`${api}/projects/${pid}/versions`,{credentials:'include'}),fetch(`${api}/runs/${rid}`,{credentials:'include'})]);
    return results.map(r=>r.status);
  },{api:API,pid:projects[0].id,rid});
  expect(codes).toEqual([404,404]);await expect(outsider.getByRole('heading',{name:'Owner only'})).toHaveCount(0);await context.close();
});

test('invalid file type and oversized file are rejected',async({page})=>{
  await register(page);await newVersion(page);
  await page.getByLabel('Dataset',{exact:true}).setInputFiles(fixture('data.csv'));
  await page.getByLabel('Manuscript PDF').setInputFiles({name:'invalid.txt',mimeType:'text/plain',buffer:Buffer.from('not a PDF')});
  await page.getByRole('button',{name:'Verify research'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toHaveText('Unsupported file format for manuscript.');
  await page.getByLabel('Manuscript PDF').setInputFiles({name:'oversized.pdf',mimeType:'application/pdf',buffer:Buffer.alloc(20*1024*1024+1)});
  await page.getByRole('button',{name:'Verify research'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toHaveText('Maximum 20 MB per file.');
});

test('missing dataset cannot submit a browser form',async({page})=>{
  await register(page);await newVersion(page);
  await page.getByLabel('Manuscript PDF').setInputFiles(fixture('paper.pdf'));
  await page.getByRole('button',{name:'Verify research'}).click();
  expect(await page.getByLabel('Dataset',{exact:true}).evaluate((element:HTMLInputElement)=>element.validity.valueMissing)).toBe(true);
  await expect(page.getByRole('heading',{name:'Bring your evidence.'})).toBeVisible();
});

for(const [paper,status,outcome,grade] of [
  ['conflict.pdf','FAILED VERIFICATION','CONFLICTING','E'],
  ['unverifiable.pdf','INSUFFICIENT EVIDENCE','UNVERIFIABLE','E'],
  ['unsupported.pdf','INSUFFICIENT EVIDENCE',null,'E'],
] as const){
  test(`scientific outcome for ${paper}`,async({page})=>{
    await register(page);await newVersion(page);await uploadInputs(page,paper);await verify(page);
    await expect(page.getByRole('heading',{name:`Overall grade: ${grade}`})).toBeVisible();
    await expect(page.getByText(status,{exact:true})).toBeVisible();
    if(outcome)await expect(page.locator('summary').first()).toContainText(outcome);
    else await expect(page.getByText('No supported claim syntax found.',{exact:false})).toBeVisible();
  });
}

test('API transport outage shows retryable error',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Sign in'}).click();
  await page.route('**/api/v1/auth/login',route=>route.abort('connectionrefused'));
  await page.getByLabel('Email',{exact:true}).fill('retry@example.org');await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Continue'}).click();
  await expect(page.getByRole('main').getByRole('alert')).toHaveText('The API is temporarily unavailable. Please retry.');
});

test('artifact corruption produces a persisted failed job',async({page})=>{
  await register(page);await newVersion(page);await uploadInputs(page);await control('pause-worker');
  let rid='';
  try{
    const response=await verify(page);const queued=await response.json();rid=queued.id;
    const artifacts=await page.evaluate(async({api,vid})=>(await fetch(`${api}/versions/${vid}/artifacts`,{credentials:'include'})).json(),{api:API,vid:queued.version_id});
    await control('tamper-artifact',{artifact_id:artifacts.find((a:{artifact_type:string})=>a.artifact_type==='DATASET').id});
  }finally{await control('resume-worker')}
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Verification failed.');
  expect((await control('assert-failed-empty',{run_id:rid})).error_code).toBe('VERIFICATION_PROCESSING_FAILED');
});

test('actual worker loss produces scheduler timeout state',async({page})=>{
  await register(page);await newVersion(page);await uploadInputs(page,'many.pdf');await control('pause-worker');
  const queued=await verify(page);const rid=(await queued.json()).id;
  await control('kill-on-running',{run_id:rid});
  await expect(page.getByRole('main').getByRole('alert')).toContainText('Verification failed.',{timeout:90000});
  expect((await control('assert-failed-empty',{run_id:rid})).error_code).toBe('WORKER_TIMEOUT');
  await page.getByRole('button',{name:'View verification history'}).click();
  await expect(page.getByText('VERSION 1 · FAILED')).toBeVisible();
});
