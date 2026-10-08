import re
import uuid
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field

from packages.verification.numeric import DEFAULT_ABSOLUTE_TOLERANCE

PROMPT_VERSION = 'explicit-statistics-v2'
class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_id: str
    claim_text: str
    metric: str
    columns: list[str]
    reported_value: float = Field(allow_inf_nan=False)
    tolerance: float = Field(default=DEFAULT_ABSOLUTE_TOLERANCE, ge=0, le=1)
    relative_tolerance: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    source_page: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)

class Provider(Protocol):
    def extract(self, pages: list[str], columns: list[str]) -> list[Claim]: ...

class LocalProvider:
    identifier = 'local/explicit-statistics-v2'
    def extract(self, pages, columns):
        claims=[]
        for page,text in enumerate(pages,1):
            for m in re.finditer(r'\b(mean|median|std|variance|population_variance|minimum|maximum|mode|sample_size|proportion|percentage)\s+(?:of\s+)?([^\W\d]\w*)\s*(?:=|is|:)\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b',text,re.I):
                claims.append(Claim(claim_id=str(uuid.uuid4()),claim_text=m.group(0),metric=m.group(1).lower(),columns=[m.group(2)],reported_value=float(m.group(3)),source_page=page,confidence=1 if m.group(2) in columns else 0))
            for m in re.finditer(r'\bcorrelation of ([^\W\d]\w*) and ([^\W\d]\w*)\s*(?:=|is|:)\s*(-?\d+(?:\.\d+)?)\b',text,re.I):
                claims.append(Claim(claim_id=str(uuid.uuid4()),claim_text=m.group(0),metric='correlation',columns=[m.group(1),m.group(2)],reported_value=float(m.group(3)),source_page=page,confidence=1 if all(c in columns for c in (m.group(1),m.group(2))) else 0))
            for m in re.finditer(r'\b(accuracy|precision|recall|f1) of ([^\W\d]\w*) and ([^\W\d]\w*)\s*(?:=|is|:)\s*(-?\d+(?:\.\d+)?)\b',text,re.I):
                claims.append(Claim(claim_id=str(uuid.uuid4()),claim_text=m.group(0),metric=m.group(1).lower(),columns=[m.group(2),m.group(3)],reported_value=float(m.group(4)),source_page=page,confidence=1 if all(c in columns for c in (m.group(2),m.group(3))) else 0))
            for m in re.finditer(r'row count\s*(?:=|is|:)\s*(\d+)',text,re.I):
                claims.append(Claim(claim_id=str(uuid.uuid4()),claim_text=m.group(0),metric='row_count',columns=[],reported_value=float(m.group(1)),source_page=page,confidence=1))
        return claims
