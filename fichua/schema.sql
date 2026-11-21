-- Fichua schema — portable Postgres SQL (Supabase, AWS RDS/Aurora) that also runs on SQLite.
-- Idempotent: safe to run on every deploy. Paste into Supabase SQL editor if you prefer.

CREATE TABLE IF NOT EXISTS hotels (
    id              TEXT PRIMARY KEY,              -- hotel_code from the Excel, e.g. NBO-001
    hotel_group     TEXT,                          -- owner group; future partner logins scope by this
    name            TEXT NOT NULL,
    city            TEXT NOT NULL,
    country         TEXT,
    address         TEXT,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    star_rating     INTEGER,
    guest_rating    NUMERIC(3,1),
    review_count    INTEGER DEFAULT 0,
    property_type   TEXT,
    description     TEXT,
    amenities       TEXT,                          -- comma separated
    image_urls      TEXT,                          -- comma separated
    currency        TEXT DEFAULT 'USD',
    check_in_time   TEXT,
    check_out_time  TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS room_types (
    id                  TEXT PRIMARY KEY,          -- room_code, e.g. NBO-001-DLX
    hotel_id            TEXT NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    max_guests          INTEGER NOT NULL,
    bed_type            TEXT,
    size_sqm            INTEGER,
    description         TEXT,
    amenities           TEXT,
    image_urls          TEXT,
    breakfast_included  BOOLEAN DEFAULT FALSE,
    free_cancellation   BOOLEAN DEFAULT TRUE
);

-- One row per room type per night: the sell price and how many rooms exist to sell.
CREATE TABLE IF NOT EXISTS room_rates (
    room_type_id    TEXT NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    stay_date       DATE NOT NULL,
    price           NUMERIC(10,2) NOT NULL,
    units           INTEGER NOT NULL,
    PRIMARY KEY (room_type_id, stay_date)
);

CREATE TABLE IF NOT EXISTS bookings (
    id                TEXT PRIMARY KEY,
    reference         TEXT NOT NULL UNIQUE,         -- shown to the guest, e.g. FCH-7K2Q9M
    access_token      TEXT NOT NULL,                -- lets the guest open their booking without login
    hotel_id          TEXT NOT NULL REFERENCES hotels(id),
    room_type_id      TEXT NOT NULL REFERENCES room_types(id),
    check_in          DATE NOT NULL,
    check_out         DATE NOT NULL,
    nights            INTEGER NOT NULL,
    guests            INTEGER NOT NULL,
    rooms             INTEGER DEFAULT 1,              -- rooms of this type in the booking
    total_price       NUMERIC(10,2) NOT NULL,
    currency          TEXT NOT NULL,
    guest_name        TEXT NOT NULL,
    guest_email       TEXT NOT NULL,
    guest_phone       TEXT,
    special_requests  TEXT,
    status            TEXT NOT NULL DEFAULT 'confirmed',   -- confirmed | cancelled
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nights consumed by each booking. Availability = rooms to sell - the units booked that night.
CREATE TABLE IF NOT EXISTS booking_nights (
    booking_id      TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    room_type_id    TEXT NOT NULL REFERENCES room_types(id),
    stay_date       DATE NOT NULL,
    units           INTEGER DEFAULT 1,                    -- rooms taken that night (the booking's rooms)
    PRIMARY KEY (booking_id, stay_date)
);

-- Partner accounts. One account owns one hotel for now (hotels.owner_id).
CREATE TABLE IF NOT EXISTS partner_users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    name            TEXT,
    phone           TEXT,
    access_code     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Codes Fichua hands out: they gate partner sign-up and can grant a free Hotel Manager licence.
CREATE TABLE IF NOT EXISTS access_codes (
    code            TEXT PRIMARY KEY,
    plan            TEXT NOT NULL DEFAULT 'manager',     -- listing | manager
    free_until      DATE,
    max_uses        INTEGER NOT NULL DEFAULT 1,
    uses            INTEGER NOT NULL DEFAULT 0,
    expires_on      DATE,
    note            TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Admin-editable settings (commission, payout timing, exchange rates, ...).
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT
);

-- Photos uploaded by partners, stored in the database (portable; move to object storage later).
CREATE TABLE IF NOT EXISTS media (
    id              TEXT PRIMARY KEY,
    owner_type      TEXT NOT NULL,                        -- hotel | room
    owner_id        TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    data            BYTEA NOT NULL,
    label           TEXT,
    sort            INTEGER DEFAULT 0,
    thumb           BYTEA,                                -- ~800 px JPEG copy for cards (made in the browser)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Changes a partner makes in the calendar. Wins over Excel rates and the room's standard price.
CREATE TABLE IF NOT EXISTS rate_overrides (
    room_type_id    TEXT NOT NULL REFERENCES room_types(id) ON DELETE CASCADE,
    stay_date       DATE NOT NULL,
    price           NUMERIC(10,2),
    units           INTEGER,
    closed          BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (room_type_id, stay_date)
);

CREATE TABLE IF NOT EXISTS payments (
    id              TEXT PRIMARY KEY,
    booking_id      TEXT NOT NULL REFERENCES bookings(id),
    provider        TEXT NOT NULL,                        -- test | stripe
    provider_ref    TEXT,                                 -- Stripe payment_intent id
    amount          NUMERIC(10,2) NOT NULL,
    currency        TEXT NOT NULL,
    status          TEXT NOT NULL,                        -- paid | refunded
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payouts (
    id              TEXT PRIMARY KEY,
    booking_id      TEXT NOT NULL REFERENCES bookings(id),
    hotel_id        TEXT NOT NULL REFERENCES hotels(id),
    amount          NUMERIC(10,2) NOT NULL,
    currency        TEXT NOT NULL,
    status          TEXT NOT NULL,                        -- scheduled | due | sent | cancelled | recover
    due_at          TIMESTAMP,
    sent_at         TIMESTAMP,
    method          TEXT,                                 -- test | manual | stripe
    note            TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Every WhatsApp message Fichua sends (or would send), so the admin can see them all.
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    booking_id      TEXT,
    hotel_id        TEXT,
    role            TEXT NOT NULL,                        -- guest | hotel | admin
    to_phone        TEXT,
    language        TEXT,
    kind            TEXT,
    body            TEXT NOT NULL,
    template        TEXT,                                 -- approved WhatsApp template name
    params          TEXT,                                 -- JSON list of its parameters
    status          TEXT NOT NULL,                        -- queued | sent | failed | not_sent
    error           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at         TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels (city);
CREATE INDEX IF NOT EXISTS idx_media_owner ON media (owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_payouts_status ON payouts (status, due_at);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_room_types_hotel ON room_types (hotel_id);
CREATE INDEX IF NOT EXISTS idx_rates_date ON room_rates (stay_date);
CREATE INDEX IF NOT EXISTS idx_booking_nights_room_date ON booking_nights (room_type_id, stay_date);
CREATE INDEX IF NOT EXISTS idx_bookings_email ON bookings (guest_email);

-- Named Fichua admin accounts. Until the first one exists, the shared ADMIN_PASSWORD signs in.
CREATE TABLE IF NOT EXISTS admin_users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    totp_secret     TEXT,                                 -- two-step login, once confirmed
    totp_pending    TEXT,                                 -- secret being set up, not confirmed yet
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at   TIMESTAMP
);

-- Rate limits (failed sign-ins, sign-ups, checkouts), kept in the database so they hold across instances.
CREATE TABLE IF NOT EXISTS login_attempts (
    id              TEXT PRIMARY KEY,
    scope           TEXT NOT NULL,                        -- admin | partner | join | booking
    key             TEXT NOT NULL,                        -- IP address, or IP + email
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts (scope, key, created_at);
