-- Tenant knowledge base (retrieved by the search_knowledge tool) and the
-- Bhasha Bridge lexicon, which is derived data: it can always be rebuilt from
-- the catalogue, so it carries a build version rather than being authoritative.

CREATE TABLE knowledge_entries (
    entry_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    tags       TEXT[] NOT NULL DEFAULT '{}',
    embedding  vector(384),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX knowledge_tenant_ix ON knowledge_entries (tenant_id);
CREATE INDEX knowledge_embedding_ix ON knowledge_entries
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE lexicon_entries (
    lexicon_entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    surface       TEXT NOT NULL,
    entry_type    TEXT NOT NULL CHECK (entry_type IN ('SERVICE','STAFF','PLACE','BRAND','PHRASE')),
    variants      TEXT[] NOT NULL DEFAULT '{}',
    phonetic_keys TEXT[] NOT NULL DEFAULT '{}',
    weight        REAL NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0.2 AND 3.0),
    build_version INT  NOT NULL DEFAULT 1,
    UNIQUE (tenant_id, surface, entry_type)
);
CREATE INDEX lexicon_keys_ix ON lexicon_entries USING gin (phonetic_keys);

CREATE TABLE correction_events (
    event_id        BIGSERIAL PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    conversation_id UUID,
    from_token      TEXT NOT NULL,
    to_surface      TEXT NOT NULL,
    asr_confidence  REAL NOT NULL,
    ngram           SMALLINT NOT NULL DEFAULT 1,
    led_to_booking  BOOLEAN,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX correction_events_tenant_ix ON correction_events (tenant_id, created_at DESC);

CREATE TABLE speculation_events (
    event_id        BIGSERIAL PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    conversation_id UUID,
    predicted_tool  TEXT NOT NULL,
    confidence      REAL NOT NULL,
    hit             BOOLEAN,
    saved_ms        INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX speculation_events_tenant_ix ON speculation_events (tenant_id, created_at DESC);

ALTER TABLE knowledge_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE lexicon_entries   ENABLE ROW LEVEL SECURITY;
CREATE POLICY knowledge_tenant_isolation ON knowledge_entries USING
    (tenant_id = current_setting('haanji.tenant_id', true)::uuid);
CREATE POLICY lexicon_tenant_isolation ON lexicon_entries USING
    (tenant_id = current_setting('haanji.tenant_id', true)::uuid);
