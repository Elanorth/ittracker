-- IT Tracker — pgloader sonrası PostgreSQL düzeltmeleri
--
-- pgloader SQLite → Postgres taşımasından sonra İKİ bilinen sorunu giderir.
-- migrate-sqlite-to-postgres.sh bunları otomatik çalıştırır; bu dosya manuel
-- çalıştırma / başka ortamlarda yeniden uygulama içindir.
--
-- Kullanım:
--   docker exec -i ittracker-db-1 psql -U ittracker -d ittracker < scripts/postgres-post-migration-fix.sql

-- ════════════════════════════════════════════════════════════════════
-- FIX 1: Sequence'ler (auto-increment id)
-- pgloader id kolonlarına sequence/DEFAULT atamıyor → INSERT'te id=NULL
-- → NotNullViolation → edit/delete/create tamamen kırılır.
-- ════════════════════════════════════════════════════════════════════
BEGIN;
DO $$
DECLARE
    t TEXT;
    max_id BIGINT;
    seq_start BIGINT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND column_name = 'id'
          AND column_default IS NULL
        ORDER BY table_name
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(id), 0) FROM %I', t) INTO max_id;
        seq_start := max_id + 1;
        EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I OWNED BY %I.id', t || '_id_seq', t);
        EXECUTE format('ALTER SEQUENCE %I RESTART WITH %s', t || '_id_seq', seq_start);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN id SET DEFAULT nextval(%L::regclass)', t, t || '_id_seq');
        RAISE NOTICE 'sequence: % (next id = %)', t, seq_start;
    END LOOP;
END $$;
COMMIT;

-- ════════════════════════════════════════════════════════════════════
-- FIX 2: Timestamp tipleri (timestamptz → timestamp)
-- pgloader timestamp kolonlarını "with time zone" yapıyor. Uygulama naive
-- datetime.utcnow() kullanıyor → karşılaştırmalar TypeError (offset-naive vs
-- offset-aware) → 500. AT TIME ZONE 'UTC' ile değer UTC olarak korunur.
-- ════════════════════════════════════════════════════════════════════
BEGIN;
DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND data_type = 'timestamp with time zone'
        ORDER BY table_name, column_name
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp without time zone USING %I AT TIME ZONE ''UTC''',
            rec.table_name, rec.column_name, rec.column_name
        );
        RAISE NOTICE 'timestamptz fix: %.%', rec.table_name, rec.column_name;
    END LOOP;
END $$;
COMMIT;
