// The owner console is a CLI, not an HTTP surface.
//
// There is no API route to approve a device, seal a break-glass credential or
// verify the audit chain, and this screen deliberately does not pretend
// otherwise. Those operations require `is_owner` plus a fresh step-up, and
// exposing them over HTTP is a security decision for the owner to take
// explicitly — not something a frontend should quietly introduce.
//
// So this page documents the commands instead. It exists because the most
// common reason a new device cannot sign in is that nobody knew approval was
// a CLI step.

const COMMANDS: { title: string; note: string; command: string }[] = [
  {
    title: "List devices awaiting approval",
    note: "A newly enrolled passkey lands here and cannot sign in until approved.",
    command: "python -m atlas.owner_console.cli devices pending",
  },
  {
    title: "Approve a device",
    note: "Requires the approving owner's user UUID. Writes an audit event.",
    command:
      "python -m atlas.owner_console.cli devices approve <device-id> --owner-id <owner-uuid>",
  },
  {
    title: "Revoke a device",
    note: "Use when a device is lost, or when a clone is suspected.",
    command:
      "python -m atlas.owner_console.cli devices revoke <device-id> --actor-id <actor-uuid>",
  },
  {
    title: "Verify the audit chain",
    note: "Walks the hash chain and recomputes it. Exits non-zero if broken.",
    command: "python -m atlas.owner_console.cli audit verify",
  },
  {
    title: "Seal a break-glass credential",
    note: "The sealed reference points at a physically secured item, never the secret itself.",
    command:
      "python -m atlas.owner_console.cli break-glass seal --holder-id <uuid> --owner-id <uuid> --sealed-reference '<where it is kept>'",
  },
];

export function OwnerConsoleScreen() {
  return (
    <section className="stack">
      <header className="page-head">
        <div>
          <h2>Owner console</h2>
          <p className="muted">Administered from the command line, by design.</p>
        </div>
      </header>

      <p className="banner banner-info">
        These operations are not exposed over HTTP. They require owner status and a fresh
        passkey step-up, and putting them behind a browser session is a decision for the
        repository owner to make deliberately — so this page documents them rather than
        performing them.
      </p>

      <div className="stack">
        {COMMANDS.map((entry) => (
          <article className="card" key={entry.title}>
            <h3>{entry.title}</h3>
            <p className="muted">{entry.note}</p>
            <pre className="code">{entry.command}</pre>
          </article>
        ))}
      </div>

      <p className="muted">
        Every command needs <code>ATLAS_DATABASE_URL</code> set, and each writes its own audit
        event in the same transaction as the change it makes.
      </p>
    </section>
  );
}
