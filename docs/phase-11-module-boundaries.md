# Phase 11 provider-neutral safety boundary

Phase 11 hosting remains an open Blueprint §25 owner decision. No model vendor,
external endpoint, local runtime, model weights, or data-processing terms are
selected by this implementation. The inference provider contract defaults to a
disabled provider and must fail closed until explicit owner sign-off is recorded.

The safety foundation may classify structured requests, enforce the four-level
authority model, construct instruction/data-separated prompts, refuse suspected
prompt injection, apply a minimum confidence threshold, assemble opaque evidence
references, and audit allowed or blocked attempts. It may not approve, pay,
send, modify final records, sign, delete, change permissions, or approve devices.

Raw prompts, retrieved document text, model responses, recommendations, secrets,
and provider payloads are not persisted in AI or audit tables. Persistence uses
digests, lengths, enumerated action/reason codes, scope IDs, confidence, and
controlled Documents references only.
