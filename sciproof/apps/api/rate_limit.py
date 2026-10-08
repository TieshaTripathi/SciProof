"""Bounded per-process fallback limiter; deploy shared edge limits too."""
from collections import OrderedDict, deque
from threading import Lock
import time

class RequestLimiter:
    def __init__(self): self.buckets=OrderedDict();self.lock=Lock()
    def allow(self,client,group,limit):
        moment=time.monotonic();key=(client,group)
        with self.lock:
            bucket=self.buckets.setdefault(key,deque())
            self.buckets.move_to_end(key)
            while bucket and bucket[0]<=moment-60: bucket.popleft()
            while len(self.buckets)>5000: self.buckets.popitem(last=False)
            if len(bucket)>=limit: return False
            bucket.append(moment);return True
