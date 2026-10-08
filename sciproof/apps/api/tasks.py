import os
import logging
from apps.api.task_signing import sign_task, valid_task
from datetime import timedelta
from celery import Celery
from sqlalchemy import select, update
from apps.api.database import make_database
from apps.api.models import VerificationRun, RunState, now
from apps.api.storage_providers import configured_storage
from apps.api.verification_service import execute_run
from apps.api.logging_config import configure_logging

configure_logging()

celery=Celery('sciproof',broker=os.getenv('REDIS_URL','redis://localhost:6379/0'))
celery.conf.update(task_serializer='json',accept_content=['json'],task_ignore_result=True,
    broker_connection_timeout=3,broker_transport_options={'socket_timeout':3,'socket_connect_timeout':3,'visibility_timeout':300},
    worker_prefetch_multiplier=1,task_acks_late=True,task_reject_on_worker_lost=True,
    task_time_limit=120,task_soft_time_limit=110,
    beat_schedule={'recover-queued-runs':{'task':'sciproof.dispatch_pending','schedule':30.0}})

@celery.task(name='sciproof.verify',bind=True)
def verify_task(self,run_id,signature):
    if not valid_task(run_id,signature): raise ValueError('Invalid verification task envelope')
    logging.getLogger('sciproof').info('verification_task_started',extra={'run_id':run_id,'task_id':self.request.id})
    engine,sessions=make_database()
    try: execute_run(run_id,sessions,configured_storage())
    finally: engine.dispose()

@celery.task(name='sciproof.dispatch_pending')
def dispatch_pending():
    engine,sessions=make_database()
    try:
        # Hard worker limit is 120s; reclaim only after 300s to avoid overlapping workers.
        with sessions.begin() as db:
            db.execute(update(VerificationRun).where(VerificationRun.job_status==RunState.RUNNING,
                       VerificationRun.started_at<now()-timedelta(seconds=300)).values(
                       job_status=RunState.FAILED,error_code='WORKER_TIMEOUT',finished_at=now()))
            ids=list(db.scalars(select(VerificationRun.id).where(VerificationRun.job_status==RunState.QUEUED).limit(100)))
        for rid in ids: enqueue(rid)
    finally: engine.dispose()

def enqueue(run_id): verify_task.apply_async(args=[run_id,sign_task(run_id)],retry=False,argsrepr='[authenticated verification envelope]')
