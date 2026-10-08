"""Optional semantic proposals. No provider can write deterministic results."""
import os
from datetime import datetime, timezone
from typing import Literal, Protocol
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, ConfigDict, Field
from packages.verification.rules import RULES

TEMPLATE='sciproof-semantic'; PROMPT_VERSION='1'; SCHEMA_VERSION='1'
def timestamp(): return datetime.now(timezone.utc).isoformat()

class MappingProposal(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    claim_id:str=Field(max_length=100)
    metric:str=Field(max_length=100)
    candidate_columns:list[str]=Field(max_length=10)
    mapping_confidence:float=Field(ge=0,le=1,allow_inf_nan=False)
    reason:str=Field(max_length=2000)
    status:Literal['PROPOSED']='PROPOSED'
class MappingResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    mappings:list[MappingProposal]=Field(max_length=1000)
class TextResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    text:str=Field(max_length=10000)
class ExtractedClaim(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    text:str=Field(max_length=2000)
    source_page:int=Field(ge=1)
    metric:str=Field(max_length=100)
    candidate_columns:list[str]=Field(max_length=10)
    confidence:float=Field(ge=0,le=1,allow_inf_nan=False)
    status:Literal['PROPOSED']='PROPOSED'
class ExtractionResponse(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    claims:list[ExtractedClaim]=Field(max_length=1000)

class AIProvider(Protocol):
    identifier:str
    model:str | None
    def extract_claims(self,pages): ...
    def map_claim_to_dataset(self,claims,columns): ...
    def explain_finding(self,finding): ...
    def extract_methodology(self,pages): ...

class DisabledAIProvider:
    identifier='disabled';model=None
    def extract_claims(self,pages): return ExtractionResponse(claims=[])
    def map_claim_to_dataset(self,claims,columns): return MappingResponse(mappings=[])
    def explain_finding(self,finding): return TextResponse(text='Semantic explanation not run')
    def extract_methodology(self,pages): return TextResponse(text='Semantic methodology extraction not run')

class DeterministicFallbackProvider(DisabledAIProvider):
    identifier='local/deterministic-fallback'
    def map_claim_to_dataset(self,claims,columns):
        return MappingResponse(mappings=[MappingProposal(claim_id=c['claim_id'],metric=c['metric'],
            candidate_columns=c['columns'],mapping_confidence=1.0,
            reason='Exact explicit field reference; no semantic inference') for c in claims[:1000]])

class HttpSemanticProvider:
    identifier='http-semantic'
    def __init__(self,endpoint,token,model,timeout=10,transport=None):
        parsed=urlparse(endpoint)
        if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('AI_ENDPOINT must be an HTTPS service URL without embedded credentials')
        if not token or not model or not 0<timeout<=30: raise ValueError('Invalid AI model, credential or timeout')
        self.endpoint=endpoint;self.token=token;self.model=model;self.timeout=timeout;self.transport=transport
    def request(self,operation,payload,schema):
        with httpx.Client(timeout=self.timeout,transport=self.transport,follow_redirects=False) as client:
            with client.stream('POST',self.endpoint,headers={'Authorization':'Bearer '+self.token},json={
                'operation':operation,'model':self.model,'prompt_template_id':TEMPLATE,'prompt_version':PROMPT_VERSION,
                'input':payload,'output_schema':schema.model_json_schema()}) as response:
                response.raise_for_status()
                raw=bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw)>1_000_000: raise ValueError('AI_RESPONSE_TOO_LARGE')
        if not raw: raise ValueError('AI_EMPTY_RESPONSE')
        return schema.model_validate_json(raw)
    def extract_claims(self,pages):
        return self.request('extract_claims',{'pages':[p[:10000] for p in pages[:20]]},ExtractionResponse)
    def map_claim_to_dataset(self,claims,columns):
        # No observations or manuscript bodies leave through the pipeline's mapping capability.
        explicit=[{k:c[k] for k in ('claim_id','metric','columns')} for c in claims[:1000]]
        return self.request('map_claim_to_dataset',{'claims':explicit,'columns':columns[:1000]},MappingResponse)
    def explain_finding(self,finding): return self.request('explain_finding',{'finding':str(finding)[:2000]},TextResponse)
    def extract_methodology(self,pages): return self.request('extract_methodology',{'pages':[p[:10000] for p in pages[:20]]},TextResponse)

def configured_provider():
    if os.getenv('AI_ENABLED','false')!='true': return DisabledAIProvider()
    provider=os.getenv('AI_PROVIDER','disabled')
    if provider=='local': return DeterministicFallbackProvider()
    if provider=='http': return HttpSemanticProvider(os.getenv('AI_ENDPOINT',''),os.getenv('AI_API_TOKEN',''),
        os.getenv('AI_MODEL',''),float(os.getenv('AI_TIMEOUT_SECONDS','10')))
    raise ValueError('AI_PROVIDER must be local or http when AI_ENABLED=true')

def augment(claims,columns,visibilities,provider=None):
    provider=provider or configured_provider()
    audit={'provider':provider.identifier,'model':provider.model,'prompt_template_id':TEMPLATE,
           'prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,'request_timestamp':timestamp(),
           'response_timestamp':None,'status':'NOT_RUN','result':[], 'failure_reason':None,'retry_count':0}
    if isinstance(provider,DisabledAIProvider) and not isinstance(provider,DeterministicFallbackProvider): return audit
    if provider.identifier!='local/deterministic-fallback' and any(v!='PUBLIC' for v in visibilities) and os.getenv('AI_ALLOW_PRIVATE','false')!='true':
        audit['failure_reason']='PRIVATE_PROCESSING_NOT_ENABLED';return audit
    try:
        response=MappingResponse.model_validate(provider.map_claim_to_dataset(claims,columns).model_dump())
        originals={c['claim_id']:c for c in claims}
        results=[];seen=set()
        for proposal in response.mappings:
            p=proposal.model_dump();original=originals.get(p['claim_id'])
            if p['claim_id'] in seen or not original or p['metric'] not in RULES or any(c not in columns for c in p['candidate_columns']):
                p['status']='REJECTED'
            elif p['mapping_confidence']<.8 or p['candidate_columns']!=original['columns'] or p['metric']!=original['metric']:
                p['status']='UNRESOLVED'
            else: p['status']='ACCEPTED_BY_RULES'
            seen.add(p['claim_id']);results.append(p)
        audit.update(status='COMPLETED',result=results)
    except httpx.TimeoutException: audit.update(status='FAILED',failure_reason='PROVIDER_TIMEOUT')
    except httpx.HTTPStatusError as error:
        audit.update(status='FAILED',failure_reason='PROVIDER_RATE_LIMIT' if error.response.status_code==429 else 'PROVIDER_UNAVAILABLE')
    except httpx.RequestError: audit.update(status='FAILED',failure_reason='PROVIDER_UNAVAILABLE')
    except Exception: audit.update(status='FAILED',failure_reason='INVALID_PROVIDER_OUTPUT')
    audit['response_timestamp']=timestamp()
    return audit
