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
    total_price       NUMERIC(10,2) NOT NULL,
    currency          TEXT NOT NULL,
    guest_name        TEXT NOT NULL,
    guest_email       TEXT NOT NULL,
    guest_phone       TEXT,
    special_requests  TEXT,
    status            TEXT NOT NULL DEFAULT 'confirmed',   -- confirmed | cancelled
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nights consumed by each booking. Availability = room_rates.units - confirmed booking nights.
CREATE TABLE IF NOT EXISTS booking_nights (
    booking_id      TEXT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    room_type_id    TEXT NOT NULL REFERENCES room_types(id),
    stay_date       DATE NOT NULL,
    PRIMARY KEY (booking_id, stay_date)
);

CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels (city);
CREATE INDEX IF NOT EXISTS idx_room_types_hotel ON room_types (hotel_id);
CREATE INDEX IF NOT EXISTS idx_rates_date ON room_rates (stay_date);
CREATE INDEX IF NOT EXISTS idx_booking_nights_room_date ON booking_nights (room_type_id, stay_date);
CREATE INDEX IF NOT EXISTS idx_bookings_email ON bookings (guest_email);
