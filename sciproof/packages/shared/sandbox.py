from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int = 30
    memory_mb: int = 256
    cpus: float = .5
    network_enabled: bool = False

class Sandbox(Protocol):
    def execute(self, artifact_id: str, limits: SandboxLimits) -> dict: ...

class DisabledSandbox:
    def execute(self, artifact_id: str, limits: SandboxLimits) -> dict:
        return {'status':'DISABLED','reason':'Secure isolated execution runtime not configured','artifact_id':artifact_id}
