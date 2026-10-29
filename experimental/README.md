# experimental/

Code that compiles and has tests but is **not part of the running system**.

## core-api — a Java 21 / Spring Boot 3 control plane

A second implementation of the platform's durable side (tenants, bookings,
receipts, packs) over PostgreSQL with row-level security, written early in the
project when the plan was a Java control plane in front of the Python engine.
The plan changed: the engine's serve mode became the whole platform (SQLite,
one process, see `engine/haanji/server.py` and `docs/console-api.md`), the
console reads only the engine, and nothing ever called this service.

It is kept here because the ArchUnit rules, the Flyway schema and the Java
port of the Pramaan ledger are useful references for the day the data moves
to PostgreSQL, and removed from the compose stack, the Prometheus scrape
config, the console's proxies and CI so that it cannot mislead anyone about
what runs. Known gaps if it is ever revived: no endpoint mints a JWT, signing
keys live in process memory, RLS is not `FORCE`d, and there is no
cross-language fixture proving the two ledgers hash identically.

    cd experimental/core-api && mvn -B verify
