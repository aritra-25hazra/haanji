-- The Pramaan Ledger.
-- Receipts are append-only by construction: there is no UPDATE path in the
-- application, and the trigger below refuses one at the database level too.

CREATE TABLE tenant_keys (
    key_id      TEXT PRIMARY KEY,
    tenant_id   UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    public_key  TEXT NOT NULL,
    key_ref     TEXT NOT NULL,        -- handle into the sealed key store, not the key
    algorithm   TEXT NOT NULL DEFAULT 'Ed25519',
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    retired_at  TIMESTAMPTZ
);
CREATE INDEX tenant_keys_tenant_ix ON tenant_keys (tenant_id, active);

CREATE TABLE receipts (
    receipt_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    seq                  BIGINT NOT NULL,
    conversation_id      UUID,
    action               TEXT NOT NULL,
    action_args          JSONB NOT NULL,
    confirmation         JSONB NOT NULL,
    transcript_excerpt   TEXT NOT NULL,
    agent_config_version INT NOT NULL,
    occurred_at          TIMESTAMPTZ NOT NULL,
    prev_hash            BYTEA NOT NULL,
    payload_hash         BYTEA NOT NULL,
    chain_hash           BYTEA NOT NULL,
    signature            BYTEA NOT NULL,
    key_id               TEXT NOT NULL REFERENCES tenant_keys,
    short_code           TEXT NOT NULL,
    UNIQUE (tenant_id, seq),
    UNIQUE (tenant_id, short_code)
);
CREATE INDEX receipts_tenant_time_ix ON receipts (tenant_id, occurred_at DESC);
CREATE INDEX receipts_conversation_ix ON receipts (conversation_id);

CREATE TABLE daily_anchors (
    tenant_id   UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    day         DATE NOT NULL,
    first_seq   BIGINT NOT NULL,
    last_seq    BIGINT NOT NULL,
    merkle_root BYTEA NOT NULL,
    signature   BYTEA NOT NULL,
    key_id      TEXT NOT NULL REFERENCES tenant_keys,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, day)
);

CREATE OR REPLACE FUNCTION receipts_are_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'receipts are append-only; % is not permitted', TG_OP;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER receipts_no_update BEFORE UPDATE OR DELETE ON receipts
    FOR EACH ROW EXECUTE FUNCTION receipts_are_append_only();

ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;
CREATE POLICY receipts_tenant_isolation ON receipts USING
    (tenant_id = current_setting('haanji.tenant_id', true)::uuid);
