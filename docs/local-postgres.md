# Running PostgreSQL locally without Docker or root

The integration tests need a real PostgreSQL instance — the behaviour they
verify (the hash-chain trigger, the append-only triggers, the CHECK
constraints) lives in the database, so mocking it would only assert that the
mock behaves as written.

If you have Docker, use it:

```bash
docker run -d --name atlas-pg -p 5432:5432 \
  -e POSTGRES_USER=atlas -e POSTGRES_PASSWORD=atlas -e POSTGRES_DB=atlas_test \
  postgres:16-alpine

export ATLAS_TEST_DATABASE_URL=postgresql://atlas:atlas@localhost:5432/atlas_test
```

## When Docker and sudo are both unavailable

This was the situation on the WSL2 machine the project was first built on:
Docker Desktop's WSL integration was off, and `sudo` had no terminal to
authenticate against, so `apt-get install postgresql` was not an option
either. A conda-forge build installs entirely under `$HOME` and needs neither.

```bash
# 1. micromamba, user-local
mkdir -p ~/.local/micromamba && cd ~/.local/micromamba
curl -fsSL https://micro.mamba.pm/api/micromamba/linux-64/latest -o mm.tar.bz2
python3 -c "
import tarfile, bz2, io, os
data = bz2.decompress(open('mm.tar.bz2','rb').read())
tarfile.open(fileobj=io.BytesIO(data)).extract('bin/micromamba', path='.', filter='data')
os.chmod('bin/micromamba', 0o755)"

# 2. PostgreSQL 16
export MAMBA_ROOT_PREFIX=~/.local/micromamba/root
~/.local/micromamba/bin/micromamba create -y -n atlaspg -c conda-forge postgresql=16
export PATH="$MAMBA_ROOT_PREFIX/envs/atlaspg/bin:$PATH"

# 3. Initialise and start a cluster on a non-default port
export PGDATA=~/.local/atlas-pgdata
initdb -D "$PGDATA" -U atlas --auth=trust -E UTF8
pg_ctl -D "$PGDATA" -o "-p 55432 -k /tmp" -l /tmp/pg.log start

# 4. Create the test database
psql -h /tmp -p 55432 -U atlas -d postgres -c "CREATE DATABASE atlas_test"
export ATLAS_TEST_DATABASE_URL="postgresql://atlas@/atlas_test?host=/tmp&port=55432"
```

`tar -xj` needs a `bzip2` binary that a minimal WSL image may not have, hence
the Python decompression step — Python's `bz2` module is built in.

Then:

```bash
make test
```

Stop the cluster with `pg_ctl -D "$PGDATA" stop`.

## Notes

- The test fixture drops and recreates every Atlas schema before applying
  `db/schema.sql`, so repeated runs against the same database are safe.
- Integration tests **skip** when `ATLAS_TEST_DATABASE_URL` is unset, so the
  unit suite still runs on a machine with no database. CI always sets it and
  runs `test_audit_hash_chain_integrity.py` by name, so a skip there cannot be
  mistaken for a pass.

## WSL: keep the virtualenv off the Windows drive

If the repository lives on a Windows drive (`/mnt/c`, `/mnt/d`, ...), create the
virtualenv on the Linux filesystem instead:

```bash
make install ATLAS_VENV=~/.atlas-venv
make test    ATLAS_VENV=~/.atlas-venv
```

DrvFs — the filesystem behind `/mnt/...` — has very high per-file latency, and
SQLAlchemy is thousands of small modules. From `/mnt`, `import sqlalchemy` alone
took **over 40 seconds** on the machine this was built on, with under 3 seconds
of CPU: pytest appeared to hang before it ever opened a database connection.
The same import from `~` takes well under a second once warm.

Worth knowing because the symptom looks like a deadlock rather than slow I/O,
and it sends you looking in the wrong place.
