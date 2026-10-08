"""Isolated real services with filesystem controls available only to test runner.

No test-control HTTP endpoint is added to the application.
"""
import json
import os
from pathlib import Path
import signal
import time
from datetime import timedelta
from sqlalchemy import select
from apps.api.database import make_database
from apps.api.models import VerificationRun, ResearchArtifact, ResearchProject, now, RunState
from scripts.validation_stack import ValidationStack
from tests.test_api import pdf

def main():
    root=Path(__file__).resolve().parents[1]
    control=root/'.runtime/e2e-control';control.mkdir(parents=True,exist_ok=True)
    responses=control/'responses';responses.mkdir(exist_ok=True)
    request_file=control/'request.json';request_file.unlink(missing_ok=True)
    ready=control/'ready.json';ready.unlink(missing_ok=True)
    fixtures=root/'.runtime/e2e-fixtures';fixtures.mkdir(exist_ok=True)
    for name,text in [('paper','mean of x = 2; row count = 3'),('conflict','mean of x = 99'),
                      ('unverifiable','mean of missing_column = 2'),('unsupported','Regression demonstrates the hypothesis.'),
                      ('many','; '.join(['mean of x = 2']*1000))]:
        (fixtures/(name+'.pdf')).write_bytes(pdf(text))
    (fixtures/'data.csv').write_bytes(b'x\n1\n2\n3')
    with ValidationStack(api_port=8000) as stack:
        stack.start_worker();stack.start_beat()
        engine,sessions=make_database(stack.env['DATABASE_URL'])
        ready.write_text(json.dumps({'status':'ready','api_url':'http://localhost:8000',
            'runtime':'PostgreSQL + authenticated Redis + prefork Celery + beat'}),encoding='utf-8')
        pending_kill=None;deadline=time.monotonic()+2700
        print('Real E2E stack ready',flush=True)
        while time.monotonic()<deadline:
            if pending_kill:
                with sessions.begin() as db:
                    run=db.get(VerificationRun,pending_kill)
                    if run and run.job_status==RunState.RUNNING:
                        worker=stack.processes['worker']
                        os.killpg(worker.pid,signal.SIGKILL);worker.wait(timeout=10)
                        stack.processes.pop('worker')
                        # Clock-age the genuine interrupted run to exercise the 300s recovery policy quickly.
                        run.started_at=now()-timedelta(seconds=301)
                        pending_kill=None
                if pending_kill is None: stack.start_worker()
            if request_file.exists():
                request=json.loads(request_file.read_text(encoding='utf-8'));request_file.unlink()
                command=request['command'];result={'status':'ok'}
                try:
                    if command=='pause-worker': os.killpg(stack.processes['worker'].pid,signal.SIGSTOP)
                    elif command=='resume-worker': os.killpg(stack.processes['worker'].pid,signal.SIGCONT)
                    elif command=='kill-on-running':
                        pending_kill=request['run_id'];os.killpg(stack.processes['worker'].pid,signal.SIGCONT)
                    elif command=='tamper-artifact':
                        with sessions() as db:
                            a=db.get(ResearchArtifact,request['artifact_id'])
                            if not a: raise ValueError('Unknown test artifact')
                            (Path(stack.env['STORAGE_ROOT'])/a.storage_reference).write_bytes(b'test-corruption')
                    elif command=='assert-failed-empty':
                        with sessions() as db:
                            run=db.get(VerificationRun,request['run_id'])
                            if run.job_status!=RunState.FAILED or run.scientific_report is not None: raise ValueError('Interrupted run was not empty FAILED')
                            result['error_code']=run.error_code
                    elif command=='restart-api':
                        stack.stop('api')
                        import sys
                        stack.start('api',[sys.executable,'-m','uvicorn','apps.api.main:app','--host','127.0.0.1','--port',8000])
                        import httpx
                        stack.wait(lambda:httpx.get(stack.api_url+'/health/ready').status_code==200)
                    elif command=='shutdown':
                        (responses/(request['id']+'.json')).write_text(json.dumps(result),encoding='utf-8');break
                    else: raise ValueError('Unknown test control')
                except Exception as error: result={'status':'failed','error_type':type(error).__name__}
                (responses/(request['id']+'.json')).write_text(json.dumps(result),encoding='utf-8')
            time.sleep(.1)
        ready.unlink(missing_ok=True);engine.dispose()
    return 0
if __name__=='__main__': raise SystemExit(main())
