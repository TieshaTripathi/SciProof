import json
import logging
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self,record):
        event={'timestamp':datetime.now(timezone.utc).isoformat(),'level':record.levelname,
               'logger':record.name,'message':record.getMessage()}
        for key in ('request_id','run_id','task_id','artifact_id','path','status','error_type'):
            if hasattr(record,key): event[key]=getattr(record,key)
        if record.exc_info: event['exception_type']=record.exc_info[0].__name__
        return json.dumps(event)

def configure_logging():
    logger=logging.getLogger('sciproof')
    if not logger.handlers:
        handler=logging.StreamHandler();handler.setFormatter(JsonFormatter());logger.addHandler(handler)
    logger.setLevel(logging.INFO);logger.propagate=False
