"""Limit incoming bytes, including chunked multipart bodies, before parsing."""
from starlette.exceptions import HTTPException

class BodyLimitMiddleware:
    def __init__(self,app,max_bytes): self.app=app;self.max_bytes=max_bytes
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        count=0
        async def bounded_receive():
            nonlocal count
            message=await receive()
            if message['type']=='http.request':
                count+=len(message.get('body',b''))
                if count>self.max_bytes: raise HTTPException(413,'Request exceeds upload limit')
            return message
        await self.app(scope,bounded_receive,send)
