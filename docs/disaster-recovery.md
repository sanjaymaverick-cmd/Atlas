# Disaster recovery and warm-standby runbook

**Status:** provider-neutral runbook ready; infrastructure provisioning blocked
by Blueprint §25 items 3 and 6.

The owner must confirm the recovery-time and recovery-point objectives and
select a physically independent warm-standby location. Until then, no provider,
region, storage product, replication topology, or failover policy is implied by
this document.

## Required architecture properties

- PostgreSQL major version and Atlas release match the primary.
- Continuous WAL and encrypted backups leave the primary failure domain.
- Backup encryption keys are recoverable independently of the failed primary,
  using the selected KMS boundary.
- The standby accepts no normal application traffic before an authorised
  promotion.
- DNS/TLS, secrets, audit verification, and break-glass access have documented
  recovery paths that do not depend on the primary site.
- Monitoring reports archive age, last successful restore drill, replication
  lag where applicable, and measured recovery duration without exposing
  credentials.

## Quarterly restore drill

1. Record the approved drill window and identify the operator and observer.
2. Restore the latest full backup plus WAL into an isolated network at the
   standby site.
3. Apply the expected Atlas migration revision; do not use ORM schema creation.
4. Run readiness, a synthetic authenticated transaction, and the independent
   audit-chain verifier.
5. Measure the recoverable timestamp (RPO) and elapsed recovery time (RTO).
6. Destroy or archive the synthetic drill environment according to the chosen
   infrastructure policy, then retain the evidence and remediation actions.

## Promotion checklist

Promotion requires explicit owner/incident-commander authorisation. Fence the
primary, establish the final recoverable timestamp, promote the standby, rotate
or reissue site-bound secrets as required, apply DNS/TLS changes, verify
readiness and the audit chain, and only then admit users. Failback is a separate
planned operation; never point both writable sites at the same logical primary.

## Decisions required before provisioning

1. Confirm or revise the proposed RTO/RPO values (§25 item 3).
2. Select the warm-standby physical location and failure-domain separation
   (§25 item 6).
3. Select the KMS/secrets product (§25 item 2) and key-recovery custodians.
4. Name the break-glass holder (§25 item 4) and incident commander role.
5. Approve retention, drill evidence, monitoring, and infrastructure cost.

Once these are decided, the provider-specific infrastructure code can be added
as a separate reviewable slice without changing the application contracts.
