"""Bounded parser subprocess. No submitted code is imported or executed."""
import json
import os
import sys

def main():
    if os.name=='posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(20,20))
    from apps.api.storage import validate, MAX_BYTES
    length=int.from_bytes(sys.stdin.buffer.read(4),'big')
    if not 0<length<=4096: return 2
    header=json.loads(sys.stdin.buffer.read(length))
    raw=sys.stdin.buffer.read(MAX_BYTES+1)
    try: metadata=validate(header['filename'],header['kind'],raw)
    except Exception: return 2
    sys.stdout.write(json.dumps(metadata));return 0
if __name__=='__main__': raise SystemExit(main())
