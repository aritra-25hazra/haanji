-- Haanji core schema.
-- Every tenant-owned table carries tenant_id as the first column of its
-- primary key or of a unique index, and row level security is switched on
-- below so a query that forgets its tenant filter returns nothing rather than
-- returning somebody else's data.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    business_name   TEXT NOT NULL,
    pack_id         TEXT NOT NULL,
    pack_version    INT  NOT NULL DEFAULT 1,
    timezone        TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    locale          TEXT NOT NULL DEFAULT 'hi-IN',
    phone_number    TEXT,
    whatsapp_number TEXT,
    plan            TEXT NOT NULL DEFAULT 'TRIAL',
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tenants_status_ck CHECK (status IN ('ACTIVE','SUSPENDED','CLOSED'))
);

CREATE TABLE users (
    user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'OWNER',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, email),
    CONSTRAINT users_role_ck CHECK (role IN ('OWNER','MANAGER','STAFF','READONLY'))
);

CREATE TABLE staff_members (
    staff_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    name       TEXT NOT NULL,
    role       TEXT,
    active     BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (tenant_id, name)
);

CREATE TABLE services (
    service_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    name         TEXT NOT NULL,
    duration_min INT  NOT NULL CHECK (duration_min > 0),
    price_inr    INT  CHECK (price_inr >= 0),
    prep_note    TEXT,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (tenant_id, name)
);

CREATE TABLE service_staff (
    tenant_id  UUID NOT NULL,
    service_id UUID NOT NULL REFERENCES services ON DELETE CASCADE,
    staff_id   UUID NOT NULL REFERENCES staff_members ON DELETE CASCADE,
    PRIMARY KEY (service_id, staff_id)
);

CREATE TABLE working_hours (
    tenant_id   UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    staff_id    UUID REFERENCES staff_members ON DELETE CASCADE,
    weekday     SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    open_min    INT NOT NULL,
    close_min   INT NOT NULL,
    break_start INT,
    break_end   INT,
    CONSTRAINT working_hours_order_ck CHECK (close_min > open_min),
    PRIMARY KEY (tenant_id, staff_id, weekday)
);

CREATE TABLE customers (
    customer_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    phone        TEXT NOT NULL,
    name         TEXT,
    last_service TEXT,
    last_visit   DATE,
    visits       INT NOT NULL DEFAULT 0,
    consent_sms  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, phone)
);

CREATE TABLE appointments (
    appointment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    service_id     UUID NOT NULL REFERENCES services,
    staff_id       UUID NOT NULL REFERENCES staff_members,
    customer_id    UUID REFERENCES customers,
    starts_at      TIMESTAMPTZ NOT NULL,
    ends_at        TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'CONFIRMED',
    source         TEXT NOT NULL DEFAULT 'VOICE',
    receipt_code   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT appointments_window_ck CHECK (ends_at > starts_at),
    CONSTRAINT appointments_status_ck CHECK (status IN ('CONFIRMED','CANCELLED','NO_SHOW','DONE'))
);

-- One staff member cannot be in two places at once. This is a database
-- constraint and not a service-layer check, because the service layer runs in
-- more than one process.
ALTER TABLE appointments ADD CONSTRAINT appointments_no_overlap
    EXCLUDE USING gist (
        staff_id WITH =,
        tstzrange(starts_at, ends_at) WITH &&
    ) WHERE (status = 'CONFIRMED');

CREATE INDEX appointments_tenant_day_ix ON appointments (tenant_id, starts_at);
CREATE INDEX appointments_customer_ix   ON appointments (tenant_id, customer_id);

CREATE TABLE leads (
    lead_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    name       TEXT,
    phone      TEXT,
    intent     TEXT NOT NULL,
    note       TEXT,
    status     TEXT NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX leads_tenant_status_ix ON leads (tenant_id, status, created_at DESC);

CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants ON DELETE CASCADE,
    channel         TEXT NOT NULL,
    caller_phone    TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    outcome         TEXT,
    duration_ms     INT,
    recording_url   TEXT,
    CONSTRAINT conversations_channel_ck CHECK (channel IN ('PHONE','WHATSAPP','WEB')),
    CONSTRAINT conversations_outcome_ck CHECK (outcome IS NULL OR outcome IN
        ('BOOKED','FAQ_ANSWERED','LEAD_CAPTURED','HANDED_OFF','ABANDONED'))
);
CREATE INDEX conversations_tenant_time_ix ON conversations (tenant_id, started_at DESC);

CREATE TABLE turns (
    turn_id           BIGSERIAL PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    conversation_id   UUID NOT NULL REFERENCES conversations ON DELETE CASCADE,
    seq               INT  NOT NULL,
    speaker           TEXT NOT NULL CHECK (speaker IN ('caller','agent')),
    text              TEXT NOT NULL,
    raw_text          TEXT,
    corrections       JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_calls        JSONB NOT NULL DEFAULT '[]'::jsonb,
    speculation       JSONB NOT NULL DEFAULT '{}'::jsonb,
    latency_ms        INT,
    interrupted       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, seq)
);

-- Row level security. Application connections run as a non-superuser role and
-- set haanji.tenant_id per transaction; a query without it sees no rows.
ALTER TABLE tenants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE services       ENABLE ROW LEVEL SECURITY;
ALTER TABLE staff_members  ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE turns          ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['services','staff_members','customers','appointments',
                             'leads','conversations','turns']
    LOOP
        EXECUTE format(
            'CREATE POLICY %1$s_tenant_isolation ON %1$s USING '
            '(tenant_id = current_setting(''haanji.tenant_id'', true)::uuid)', t);
    END LOOP;
    EXECUTE 'CREATE POLICY tenants_self ON tenants USING '
            '(tenant_id = current_setting(''haanji.tenant_id'', true)::uuid)';
END $$;
