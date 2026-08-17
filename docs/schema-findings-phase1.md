# Schema findings — verified against a live PostgreSQL 16.15

`db/schema.sql` had only been syntax-validated. It has now been applied to a real
database and its audit invariants exercised. It applies cleanly. Five defects
were found, two of them critical.

## 1. CRITICAL — the audit hash chain breaks under multi-row transactions

`audit.compute_record_hash()` selects the predecessor row with:

```sql
SELECT record_hash INTO last_hash FROM audit.audit_events
ORDER BY created_at DESC, id DESC LIMIT 1;
```

Both ordering keys fail:

- `created_at DEFAULT now()` is **transaction-scoped** — every row written in one
  transaction gets an identical timestamp, so `created_at` cannot order them.
- `id` is `gen_random_uuid()` — random, not monotonic. So `id DESC` picks an
  arbitrary row, not the previous one.

Observed with three rows inserted in a single statement: two of them received the
**same `prev_hash`**, forking the chain, and the genesis row sorted last.

```
     prev     |     rec      | action
--------------+--------------+--------
 ce42bd1bd447 | 4028b69c6642 | create   <- prev duplicated
 ce42bd1bd447 | 82d82e7ae836 | update   <- prev duplicated
 000000000000 | ce42bd1bd447 | create   <- genesis, sorts last
```

This defeats the tamper-evidence the chain exists to provide (Blueprint §5.2,
closing Audit Section 16 item 4): a broken chain is indistinguishable from a
tampered one, and normal operation breaks it immediately — any business
transaction that writes more than one audit row hits this.

**Fix — applied.** It has two parts, and the second is easy to get wrong.

*Part 1 — order the chain by a monotonic sequence, not by `created_at, id`.*

*Part 2 — allocate that sequence inside the chain lock.* The obvious
implementation, `seq BIGSERIAL`, **does not work**, and fails silently. A column
`DEFAULT` is evaluated *before* `BEFORE INSERT` triggers run, so sequence numbers
are handed out before the trigger takes its lock. A writer holding `seq=10` can
then acquire the lock after a writer holding `seq=11`, read `seq=11` as the chain
head, and link onto it — leaving `seq` order and hash linkage permanently
disagreeing.

Measured with 8 concurrent writers × 25 rows, `BIGSERIAL` + advisory lock gave
**12 broken links and 7 forks out of 200 rows**. The same test with the sequence
allocated inside the lock gives 0 and 0.

So the sequence is declared standalone and advanced by the trigger itself:

```sql
CREATE SEQUENCE audit.audit_events_seq;          -- no column DEFAULT

-- in audit.compute_record_hash(), in this order:
PERFORM pg_advisory_xact_lock(hashtext('audit.audit_events'));
NEW.seq := nextval('audit.audit_events_seq');
SELECT record_hash INTO last_hash FROM audit.audit_events ORDER BY seq DESC LIMIT 1;
```

The lock is transaction-scoped, so it is held until commit and the read, the
allocation and the insert are atomic with respect to other appenders. Any
verifier must walk rows `ORDER BY seq` — never `created_at` or `id`.

Cost: audit appends are serialised group-wide. That is inherent to a hash chain,
not an artefact of this design, and is not a concern at the transaction volumes
in Blueprint §6. If it ever becomes one, the answer is per-entity chains, not a
weaker lock.

## 2. CRITICAL — the hash depended on the client's session timezone

Separate from the ordering bug, and found the same way. The trigger hashed
`NEW.occurred_at::text`. Casting a `timestamptz` to text renders it through the
**session's** `TimeZone` and `DateStyle` settings, neither of which is a
property of the stored value:

```
SET TimeZone='UTC';              -> 2026-08-17 10:30:00+00
SET TimeZone='Asia/Kolkata';     -> 2026-08-17 16:00:00+05:30
SET TimeZone='America/New_York'; -> 2026-08-17 06:30:00-04
```

Three different strings for one instant, so three different hashes. The
consequence is not theoretical for an India-based group: a record written by a
client session on `Asia/Kolkata` recomputes to a different hash when verified
from UTC, and the chain reports tampering that never happened. Worse, the
failure is silent at write time and only surfaces during an audit — precisely
when a false alarm is most expensive.

**Fix — applied.** Normalise to UTC and format explicitly, which is stable under
both settings and always emits six fractional digits:

```sql
to_char(NEW.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS.US')
```

`atlas/platform/audit/chain.py::format_timestamptz` mirrors this exactly.

## 3. `identity.devices` has no WebAuthn sign counter

Required to detect cloned authenticators — the core anti-replay signal in the
WebAuthn spec. Without it a copied credential is undetectable.

```sql
ALTER TABLE identity.devices ADD COLUMN sign_counter BIGINT NOT NULL DEFAULT 0;
```

## 4. `identity.sessions.step_up_verified` never expires

It is a bare boolean. Once true it stays true for the session's life, so a
step-up performed for one sensitive action silently authorises every later one.
Blueprint §15 treats step-up as per-action, which needs a freshness window.

```sql
ALTER TABLE identity.sessions ADD COLUMN step_up_verified_at TIMESTAMPTZ;
```

## 5. `break_glass_credentials.status` is a value list, not a state machine

`CHECK (status IN ('sealed','invoked','revoked'))` permits `invoked -> sealed`,
i.e. silently re-sealing a one-shot emergency credential after use. The database
cannot express the ordering, so `atlas/modules/identity/break_glass.py` must
enforce `sealed -> invoked -> revoked` and never allow a return to `sealed`.

## Verified working

- All 21 schemas, tables, indexes and triggers create without error.
- Hash chain, after the fix: 200 rows written by 8 concurrent writers produced
  0 broken links, 0 forks, a contiguous `seq` range, and a genesis row anchored
  to 64 zeros. The multi-row single-statement case that originally forked the
  chain now links correctly.
- Append-only enforcement is solid: both `UPDATE` and `DELETE` against
  `audit.audit_events` raise `audit.audit_events is append-only`.
- The `set_updated_at()` auto-attach `DO` block wires every table with an
  `updated_at` column (the "does not exist, skipping" notices are the expected
  `DROP TRIGGER IF EXISTS` no-ops on first run).
