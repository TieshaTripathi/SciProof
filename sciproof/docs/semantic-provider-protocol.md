# Optional semantic provider protocol

The optional provider boundary is independent of deterministic verification. The default is disabled. A configured HTTP provider is a vendor-neutral semantic gateway, not an assumption that arbitrary vendor APIs accept SciProof's schema. A deployment must supply an adapter endpoint implementing this contract; no live credentials are shipped or required for tests.

Requests use HTTPS, bearer authentication, JSON, a configured model and one operation: `extract_claims`, `map_claim_to_dataset`, `explain_finding`, or `extract_methodology`. Each includes a prompt template/version and bounded input. Mapping requests include explicit claims and field names, never dataset rows. Private/restricted metadata is withheld unless an administrator deliberately enables `AI_ALLOW_PRIVATE`; this flag is an external processing policy, not IPFS publication permission.

Responses must match the supplied strict JSON schema. Mapping proposals identify existing claim IDs, metrics, candidate columns, confidence, reason and initial `PROPOSED` state. Deterministic acceptance requires exact agreement with the original explicit metric and fields, a supported rule and adequate confidence. Ambiguous, unsupported or invented fields remain rejected/unresolved. Accepted mappings confirm consistency only: they cannot replace a calculated value or change deterministic scores.

Persist audit provider/model/template/schema versions, timestamps, validated results, failure code and retry count. Never persist bearer tokens or raw requests. Provider errors must yield a failed optional audit while scientific checks, evidence and provenance still commit. No live provider outcome is claimed until a configured service is actually exercised.
