"""Real PostgreSQL + Redis + prefork Celery + beat failure/recovery gate."""
import json
import time
from pathlib import Path
import httpx
from sqlalchemy import select, func
from apps.api.database import make_database
from apps.api.models import *
from scripts.validation_stack import ValidationStack
from tests.test_api import pdf

def main():
    with ValidationStack() as stack:
        engine,sessions=make_database(stack.env['DATABASE_URL'])
        with httpx.Client(base_url=stack.api_url,timeout=30) as client:
            credentials={'email':'queue@example.org','password':'a-long-test-password'}
            assert client.post('/auth/signup',json=credentials).status_code==200
            assert client.post('/auth/login',json=credentials).status_code==200
            def submit():
                pid=client.post('/projects',json={'title':'Real queue validation'}).json()['id']
                vid=client.post(f'/projects/{pid}/versions').json()['id']
                # Multiple claims make RUNNING observable without artificial progress.
                paper=pdf(' '.join(['mean of x = 2']*40))
                for kind,name,raw in [('manuscript','paper.pdf',paper),('dataset','data.csv',b'x\n1\n2\n3')]:
                    response=client.post(f'/versions/{vid}/artifacts/{kind}',files={'file':(name,raw)})
                    assert response.status_code==200,response.text
                response=client.post(f'/versions/{vid}/verify')
                assert response.status_code==202,response.text
                return response.json()['id']
            rid=submit()
            with sessions() as db:
                assert db.get(VerificationRun,rid).job_status==RunState.QUEUED
                assert db.scalar(select(func.count()).select_from(Claim))==0
            stack.start_worker()
            seen=['QUEUED']
            def complete():
                state=client.get('/runs/'+rid).json()['job_status']
                if state!=seen[-1]: seen.append(state)
                return state=='COMPLETED'
            stack.wait(complete,120)
            assert 'RUNNING' in seen,seen
            # Duplicate actual broker delivery, not direct service invocation.
            import os
            os.environ.update(stack.env)
            from apps.api.tasks import enqueue, verify_task
            for _ in range(3): enqueue(rid)
            time.sleep(2)
            def assert_counts(run_id):
                with sessions() as db:
                    run=db.get(VerificationRun,run_id)
                    assert run.job_status==RunState.COMPLETED and run.attempts==1
                    expected=len(run.scientific_report['claims'])
                    for model in (Claim,Evidence,VerificationCheck):
                        assert db.scalar(select(func.count()).select_from(model).where(model.run_id==run_id))==expected
                    assert db.scalar(select(func.count()).select_from(VerificationScore).where(VerificationScore.run_id==run_id))==6
                    assert db.scalar(select(func.count()).select_from(ProvenanceRecord).where(ProvenanceRecord.run_id==run_id))==1
                    assert db.scalar(select(func.count()).select_from(VerificationFinding).where(VerificationFinding.run_id==run_id))>0
            assert_counts(rid)
            # A forged envelope must be rejected by the actual broker consumer.
            verify_task.apply_async(args=[rid,'0'*64],retry=False,argsrepr='[invalid validation envelope]')
            stack.wait(lambda:'Invalid verification task envelope' in (stack.folder/'worker.log').read_text(),30)
            assert_counts(rid)
            stack.stop('redis')
            recovered=submit()
            with sessions() as db: assert db.get(VerificationRun,recovered).job_status==RunState.QUEUED
            stack.start_redis();stack.start_beat()
            stack.wait(lambda:client.get('/runs/'+recovered).json()['job_status']=='COMPLETED',180)
            assert_counts(recovered)
            result={'runtime':'Linux prefork Celery + Redis + PostgreSQL','lifecycle':seen,
                    'duplicate_deliveries':3,'redis_outage_recovered':True,'single_completion_verified':True,
                    'signed_task_envelopes':True,'forged_task_rejected_by_worker':True,'scheduler_redispatch':True}
            Path('docs/async-validation-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result))
        engine.dispose()
    return 0

if __name__=='__main__': raise SystemExit(main())
