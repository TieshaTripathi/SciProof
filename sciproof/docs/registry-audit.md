# Preserved registry audit

The existing SciProofRegistry source is retained. Its immutable attestor limits writes to one configured signer. Research/version identifiers key a record whose nonzero researcher field prevents replacement. Nonzero identifiers, provenance, artifact summary and researcher are enforced; score is bounded to 10,000 and status to 0–4. It stores only hashes, address, timestamp and compact score/status. No PDFs, dataset bytes, secrets or manuscript metadata are included. Attested identifies research/version/provenance/researcher in an event.

No pausing or attestor rotation exists, so paused-state tests do not apply. A compromised or unavailable attestor cannot be rotated in the deployed contract; production needs a deliberate governance/key-custody decision. The researcher address is an explicit public association, not proof of wallet ownership or verified identity. Contract authorization establishes who submitted an attestation, not scientific validity.

Timestamp uses uint64(block.timestamp), safe within ordinary chain timestamps; the compiler's narrowing-cast lint is retained as an acknowledged warning. No external calls occur during attestation, so there is no reentrancy surface in this function. Duplicate refusal preserves all original fields. Deployment and signing are separate from scientific completion.

Foundry 1.8.5 and Solidity 0.8.24 were actually provisioned with the official release checksum and used to compile/test the original four tests in Phase A. Expanded tests and backend/local-chain results are recorded in the phase ledger. This is a focused engineering review, not an independent smart-contract security audit.
