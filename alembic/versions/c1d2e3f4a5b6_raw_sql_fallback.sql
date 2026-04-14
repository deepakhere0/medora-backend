-- =============================================================================
-- MEDORA — Migration c1d2e3f4a5b6
-- Fallback raw SQL for Supabase Dashboard SQL Editor
-- Run this if Alembic migration fails.
-- All statements use IF NOT EXISTS / IF EXISTS / DO blocks for idempotency.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Add 'doctor' value to userrole enum
--    ALTER TYPE … ADD VALUE cannot run inside a transaction in PostgreSQL,
--    but the Supabase SQL Editor runs each statement in autocommit mode, so
--    this works fine here.
-- -----------------------------------------------------------------------------
ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'doctor';


-- -----------------------------------------------------------------------------
-- 2. Make doctors.organization_id nullable (independent doctors have no org)
-- -----------------------------------------------------------------------------
ALTER TABLE doctors ALTER COLUMN organization_id DROP NOT NULL;


-- -----------------------------------------------------------------------------
-- 3. Add new columns to the doctors table
--    Each ALTER TABLE … ADD COLUMN IF NOT EXISTS is safe to re-run.
-- -----------------------------------------------------------------------------
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS is_independent          BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS self_registered         BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS is_verified             BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS nmc_registration_number VARCHAR(100)  NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS specialty               VARCHAR(100)  NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS consultation_fee        DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS online_consultation_fee DECIMAL(10,2) NOT NULL DEFAULT 0;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS is_available_online     BOOLEAN       NOT NULL DEFAULT false;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS latitude                DOUBLE PRECISION NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS longitude               DOUBLE PRECISION NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS languages_spoken        TEXT          NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS profile_photo_url       TEXT          NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS about_text              TEXT          NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS address                 TEXT          NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS pincode                 VARCHAR(10)   NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS city                    VARCHAR(100)  NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS state                   VARCHAR(100)  NULL;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS average_rating          DECIMAL(3,2)  NOT NULL DEFAULT 0;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS total_reviews           INTEGER       NOT NULL DEFAULT 0;
ALTER TABLE doctors ADD COLUMN IF NOT EXISTS degree                  VARCHAR(200)  NULL;

-- Unique constraint on NMC registration number (global, not per-org)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_doctors_nmc_registration'
    ) THEN
        ALTER TABLE doctors
            ADD CONSTRAINT uq_doctors_nmc_registration
            UNIQUE (nmc_registration_number);
    END IF;
END $$;


-- -----------------------------------------------------------------------------
-- 4. Create the reviews table
--    Uses UUID PK to match the rest of the MEDORA schema.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id       UUID          NOT NULL REFERENCES doctors(id)      ON DELETE CASCADE,
    patient_id      UUID          NOT NULL REFERENCES patients(id)     ON DELETE CASCADE,
    appointment_id  UUID          NULL     REFERENCES appointments(id) ON DELETE SET NULL,
    rating          INTEGER       NOT NULL,
    review_text     TEXT          NULL,
    is_verified     BOOLEAN       NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_reviews_rating_range      CHECK (rating >= 1 AND rating <= 5),
    CONSTRAINT uq_reviews_doctor_appointment UNIQUE (doctor_id, appointment_id)
);


-- -----------------------------------------------------------------------------
-- 5. Create the online_consultations table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS online_consultations (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id           UUID          NOT NULL REFERENCES doctors(id)      ON DELETE CASCADE,
    patient_id          UUID          NOT NULL REFERENCES patients(id)     ON DELETE CASCADE,
    appointment_id      UUID          NULL     REFERENCES appointments(id) ON DELETE SET NULL,
    consultation_type   VARCHAR(20)   NOT NULL DEFAULT 'video',
    status              VARCHAR(20)   NOT NULL DEFAULT 'scheduled',
    scheduled_at        TIMESTAMPTZ   NOT NULL,
    started_at          TIMESTAMPTZ   NULL,
    ended_at            TIMESTAMPTZ   NULL,
    duration_minutes    INTEGER       NULL,
    meeting_room_id     VARCHAR(200)  NULL,
    prescription_text   TEXT          NULL,
    consultation_fee    DECIMAL(10,2) NOT NULL DEFAULT 0,
    payment_status      VARCHAR(20)   NOT NULL DEFAULT 'pending',
    notes               TEXT          NULL,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);


-- -----------------------------------------------------------------------------
-- 6. Performance indexes
-- -----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_doctors_location
    ON doctors (latitude, longitude)
    WHERE latitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_doctors_specialty
    ON doctors (specialty)
    WHERE specialty IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_doctors_independent
    ON doctors (is_independent)
    WHERE is_independent = true;

CREATE INDEX IF NOT EXISTS idx_doctors_verified
    ON doctors (is_verified)
    WHERE is_verified = true;

CREATE INDEX IF NOT EXISTS idx_reviews_doctor
    ON reviews (doctor_id);

CREATE INDEX IF NOT EXISTS idx_consultations_doctor
    ON online_consultations (doctor_id);

CREATE INDEX IF NOT EXISTS idx_consultations_patient
    ON online_consultations (patient_id);
