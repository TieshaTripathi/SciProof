"use client";
import {useState} from 'react';
import Link from 'next/link';

const API=(process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000')+'/api/v1';
type Project={id:string;title:string};
type Job={id:string;job_status:string;error_code?:string};
type HistoricalRun=Job & {version_number:number;verification_status:string|null};
type Report=Job & {
  status:string;classification:string;scores:Record<string,number>;
  ai?:{semantic?:{status:string;provider:string}};
  checks:{claim_id:string;claim_text:string;outcome:string;reported_value:number;calculated_value:number|null;explanation:string;source_page:number;artifact_id:string;evidence_id:string;input_fields:string[];method:string;rule_version:string;tolerance:number;relative_tolerance:number;absolute_difference:number|null;relative_difference:number|null;comparison_method:string;rule_context:Record<string,unknown>;software_versions:Record<string,string>}[];
  findings:string[];provenance:{provenance_hash:string};attestation:{status:string}
};
type Screen='landing'|'login'|'signup'|'dashboard'|'upload'|'processing'|'history'|'report';
async function api<T>(path:string,body?:unknown):Promise<T>{
  let response:Response;
  try{response=await fetch(API+path,{credentials:'include',method:body?'POST':'GET',
    headers:body instanceof FormData?{}:{'Content-Type':'application/json'},
    body:body instanceof FormData?body:body?JSON.stringify(body):undefined});}
  catch{throw new Error('The API is temporarily unavailable. Please retry.')}
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please check your input');
  return data as T;
}
async function awaitReport(job:Job,onState:(state:string)=>void):Promise<Report>{
  const deadline=Date.now()+5*60*1000;
  let current=job;onState(current.job_status);
  while(current.job_status!=='COMPLETED'){
    if(current.job_status==='FAILED')throw new Error('Verification failed. Your evidence remains sealed; create a new version for corrected inputs.');
    if(Date.now()>deadline)throw new Error('Verification is still processing. Reopen it from project history. Run ID: '+current.id);
    await new Promise(resolve=>setTimeout(resolve,1500));
    current=await api<Job>('/runs/'+current.id);onState(current.job_status);
  }
  return current as Report;
}

function Landing({start}:{start:()=>void}){
  return <><div className="eyebrow">EVIDENCE BEFORE ASSURANCE</div><h1>Great research.<br/><em>Verifiable evidence.</em></h1>
    <p className="lead">Trace scientific claims to their data. Reproduce the numbers. Build an auditable record of what your evidence supports.</p>
    <button className="primary" onClick={start}>Start a research project →</button>
    <div className="grid">{[
      ['01 / VERIFY','Numbers you can reproduce','Deterministic checks with explicit methods and tolerances.'],
      ['02 / UNDERSTAND','Evidence with context','Review supported, conflicting and unverifiable claims.'],
      ['03 / PRESERVE','A traceable research record','Encrypted private artifacts and canonical provenance.']
    ].map(([number,title,description])=><article key={number}><b>{number}</b><h2>{title}</h2><p>{description}</p></article>)}</div></>;
}
function ReportView({report,back}:{report:Report;back:()=>void}){
  function download(){
    const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='sciproof-report.json';link.click();URL.revokeObjectURL(url);
  }
  return <><div className="eyebrow">VERIFICATION REPORT</div><h1>Evidence, made visible.</h1>
    <p className="badge">{report.status.replaceAll('_',' ')}</p><h2>Overall grade: {report.classification}</h2><p>Confidence summarizes performed checks; it does not certify scientific validity.</p>
    <div className="grid">{Object.entries(report.scores).map(([dimension,value])=><article key={dimension}><b>{dimension.replaceAll('_',' ')}</b><h2>{value.toFixed(1)}<small> / 100</small></h2></article>)}</div>
    <h2>Claim-by-claim findings</h2>{!report.checks.length&&<p>No supported claim syntax found. Additional evidence and explicit mappings are required.</p>}
    {report.checks.map(check=><details key={check.claim_id}><summary>{check.claim_text} · {check.outcome}</summary>
      <article><h3>Evidence</h3><p>Reported {check.reported_value} · Calculated {check.calculated_value??'Unavailable'}</p>
      <p>Manuscript page {check.source_page} · Fields: {check.input_fields.join(', ')||'Entire dataset'}</p>
      <p>Rule: {check.method} · Version {check.rule_version}</p><p>Artifact: <span className="hash">{check.artifact_id}</span></p><p>Evidence: <span className="hash">{check.evidence_id}</span></p>
      <p>Absolute difference: {check.absolute_difference??'Undefined'} · Relative difference: {check.relative_difference??'Undefined'}</p>
      <p>Absolute tolerance: {check.tolerance} · Relative tolerance: {check.relative_tolerance} · Comparison: {check.comparison_method}</p>
      <h3>Finding explanation</h3><p>{check.explanation}</p><pre>{JSON.stringify(check.rule_context,null,2)}</pre><p>Software: {Object.entries(check.software_versions).map(([name,value])=>`${name} ${value}`).join(', ')}</p></article></details>)}
    {report.findings.map(finding=><p key={finding}>{finding}</p>)}
    <article><b>PROVENANCE SHA-256</b><p className="hash">{report.provenance.provenance_hash}</p><p>Attestation: {report.attestation.status}</p><p>Optional semantic layer: {report.ai?.semantic?.status||'NOT_RUN'} ({report.ai?.semantic?.provider||'disabled'}). Deterministic evidence determines this result.</p></article>
    <button className="primary" onClick={download}>Download audit report</button><button onClick={back}>Back to projects</button></>;
}

export default function Home(){
  const [screen,setScreen]=useState<Screen>('landing');
  const [error,setError]=useState('');
  const [projects,setProjects]=useState<Project[]>([]);
  const [history,setHistory]=useState<HistoricalRun[]>([]);
  const [vid,setVid]=useState('');
  const [report,setReport]=useState<Report|null>(null);
  const [busy,setBusy]=useState(false);
  const [authenticated,setAuthenticated]=useState(false);
  const [jobState,setJobState]=useState('QUEUED');
  async function action(fn:()=>Promise<void>){
    setBusy(true);setError('');
    try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  async function openReport(job:Job,fallback:Screen){
    setScreen('processing');
    try{setReport(await awaitReport(job,setJobState));setScreen('report')}catch(e){setScreen(fallback);throw e}
  }
  return <><header><Link href="/" className="brand">◈ SciProof</Link><span>RESEARCH INTEGRITY INFRASTRUCTURE</span>{authenticated?<button disabled={busy} onClick={()=>void action(async()=>{await api('/auth/logout',{});setAuthenticated(false);setProjects([]);setHistory([]);setReport(null);setVid('');setScreen('login')})}>Logout</button>:<button disabled={busy} onClick={()=>setScreen('login')}>Sign in →</button>}</header>
    <main>{error&&<p role="alert" className="error">{error}</p>}
      {screen==='landing'&&<Landing start={()=>setScreen('signup')}/>}
      {(screen==='login'||screen==='signup')&&<section className="panel"><div className="eyebrow">YOUR RESEARCH WORKSPACE</div><h1>{screen==='login'?'Welcome back.':'Create your account.'}</h1>
        <form onSubmit={event=>{event.preventDefault();const data=new FormData(event.currentTarget);void action(async()=>{
          const credentials={email:data.get('email'),password:data.get('password')};
          if(screen==='signup')await api('/auth/signup',credentials);
          await api('/auth/login',credentials);setAuthenticated(true);setProjects(await api<Project[]>('/projects'));setReport(null);setHistory([]);setScreen('dashboard');
        })}}><label>Email<input name="email" type="email" required/></label><label>Password<input name="password" type="password" minLength={12} required/></label><p>Use at least 12 characters.</p><button disabled={busy} className="primary">Continue →</button></form>
        <button disabled={busy} onClick={()=>setScreen(screen==='login'?'signup':'login')}>{screen==='login'?'Create an account':'Already have an account?'}</button></section>}
      {screen==='dashboard'&&<><div className="eyebrow">WORKSPACE / RESEARCH</div><h1>Your research projects</h1>
        <form onSubmit={event=>{event.preventDefault();const title=new FormData(event.currentTarget).get('title');void action(async()=>{
          await api('/projects',{title});setProjects(await api<Project[]>('/projects'));
        })}}><label>New project title<input name="title" required maxLength={200}/></label><button disabled={busy} className="primary">Create project</button></form>
        <div className="grid">{projects.map(project=><article key={project.id}><b>PRIVATE RESEARCH</b><h2>{project.title}</h2>
          <button disabled={busy} onClick={()=>void action(async()=>{const version=await api<{id:string}>(`/projects/${project.id}/versions`,{});setVid(version.id);setScreen('upload')})}>Upload a new version →</button>
          <button disabled={busy} onClick={()=>void action(async()=>{setHistory(await api<HistoricalRun[]>(`/projects/${project.id}/runs`));setScreen('history')})}>View verification history</button></article>)}</div></>}
      {screen==='history'&&<><div className="eyebrow">RESEARCH / VERIFICATION HISTORY</div><h1>Follow every version.</h1>
        {!history.length&&<p>No verification runs yet.</p>}{history.map(run=><article key={run.id}><b>VERSION {run.version_number} · {run.job_status}</b><p>{run.verification_status?.replaceAll('_',' ')||'Awaiting verification'}</p><p className="hash">Run {run.id}</p>
          {run.job_status==='FAILED'?<p>Processing failed. Create a new version to retry with corrected evidence.</p>:<button disabled={busy} onClick={()=>void action(async()=>openReport(await api<Job>('/runs/'+run.id),'history'))}>Open report →</button>}</article>)}
        <button disabled={busy} onClick={()=>setScreen('dashboard')}>Back to projects</button></>}
      {screen==='upload'&&<section className="panel"><div className="eyebrow">NEW RESEARCH VERSION</div><h1>Bring your evidence.</h1><p>Artifacts remain private and encrypted. Maximum 20 MB per file.</p>
        <form onSubmit={event=>{event.preventDefault();const data=new FormData(event.currentTarget);void action(async()=>{
          for(const kind of ['manuscript','dataset','analysis']){
            const file=data.get(kind) as File;
            if(file?.size>20*1024*1024)throw new Error('Maximum 20 MB per file.');
            if(file?.size && !({manuscript:/\.pdf$/i,dataset:/\.(csv|json|parquet)$/i,analysis:/\.(py|ipynb)$/i}[kind as 'manuscript'|'dataset'|'analysis']).test(file.name))throw new Error('Unsupported file format for '+kind+'.');
          }
          for(const kind of ['manuscript','dataset','analysis']){const file=data.get(kind) as File;if(file?.size){const payload=new FormData();payload.append('file',file);await api(`/versions/${vid}/artifacts/${kind}`,payload)}}
          await openReport(await api<Job>(`/versions/${vid}/verify`,{}),'dashboard');
        })}}><label>Manuscript PDF<input type="file" name="manuscript" accept=".pdf" required/></label><label>Dataset<input type="file" name="dataset" accept=".csv,.json,.parquet" required/></label><label>Analysis code (stored; execution disabled)<input type="file" name="analysis" accept=".py,.ipynb"/></label><button disabled={busy} className="primary">{busy?'Uploading…':'Verify research →'}</button></form></section>}
      {screen==='processing'&&<section aria-live="polite"><div className="eyebrow">VERIFICATION IN PROGRESS</div><h1>Following the evidence.</h1><p role="status">Run state: {jobState}</p><p>The worker checks your evidence and builds a persisted report. You can reopen the run from project history.</p></section>}
      {screen==='report'&&report&&<ReportView report={report} back={()=>setScreen('dashboard')}/>}
    </main><footer>SciProof · Verifiable Research. Reproducible Evidence.</footer></>;
}
