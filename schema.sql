-- ═══════════════════════════════════════════════════════════════════
--  VetDose — Schema Supabase
--  Ejecuta este script en: Supabase Dashboard → SQL Editor → New query
-- ═══════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────
--  1. MEDICAMENTOS_BASE
--     Almacena el catálogo oficial de medicamentos importado de AEMPS.
--     Se rellena automáticamente desde la app si la tabla está vacía.
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medicamentos_base (
  id                   TEXT        PRIMARY KEY,          -- nregistro AEMPS, ej. "EU/2/22/288/003"
  nombre               TEXT        NOT NULL,
  pactivos             TEXT,                             -- principio(s) activo(s)
  url_ficha            TEXT,                             -- URL PDF ficha técnica AEMPS
  via_administracion   TEXT,
  forma_farmaceutica   TEXT,
  dispensacion         TEXT,
  antibiotico          BOOLEAN     DEFAULT false,
  labtitular           TEXT,
  -- Dosis extraídas automáticamente del PDF de la ficha técnica (script Python)
  dosis_perro          JSONB,                           -- {valor, max, unidad, texto}
  dosis_gato           JSONB,
  posologia_raw        TEXT,                            -- extracto de texto de la sección 4
  created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_med_base_pactivos   ON medicamentos_base USING gin(to_tsvector('spanish', coalesce(pactivos,'')));
CREATE INDEX IF NOT EXISTS idx_med_base_nombre     ON medicamentos_base USING gin(to_tsvector('spanish', coalesce(nombre,'')));
CREATE INDEX IF NOT EXISTS idx_med_base_antibiotico ON medicamentos_base (antibiotico);

-- ──────────────────────────────────────────────────────────────────
--  2. DOSIS_PERSONALIZADAS
--     Dosis clínicas que el veterinario configura manualmente.
--     Sustituye al IndexedDB local de la versión anterior.
-- ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dosis_personalizadas (
  medicamento_id          TEXT        PRIMARY KEY
                                      REFERENCES medicamentos_base(id)
                                      ON DELETE CASCADE,

  -- Perro
  perro_dosis             NUMERIC,                      -- mg/kg (o la unidad que corresponda)
  perro_unidad            TEXT        DEFAULT 'mg/kg',
  perro_concentracion     NUMERIC,
  perro_conc_unidad       TEXT        DEFAULT 'mg/ml',
  perro_priorizar         BOOLEAN     DEFAULT false,    -- sobreescribe dosis AEMPS en calc.

  -- Gato
  gato_dosis              NUMERIC,
  gato_unidad             TEXT        DEFAULT 'mg/kg',
  gato_concentracion      NUMERIC,
  gato_conc_unidad        TEXT        DEFAULT 'mg/ml',
  gato_priorizar          BOOLEAN     DEFAULT false,

  -- Notas del veterinario
  notas                   TEXT,

  updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger: actualizar updated_at automáticamente en cada UPDATE
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_dosis_updated_at
  BEFORE UPDATE ON dosis_personalizadas
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ──────────────────────────────────────────────────────────────────
--  3. ROW LEVEL SECURITY (RLS)
--     Habilitar RLS y crear políticas para anon key pública.
--     Ajusta según tus necesidades (p.ej. auth.uid() si añades login).
-- ──────────────────────────────────────────────────────────────────
ALTER TABLE medicamentos_base      ENABLE ROW LEVEL SECURITY;
ALTER TABLE dosis_personalizadas   ENABLE ROW LEVEL SECURITY;

-- Lectura pública (la anon key puede leer)
CREATE POLICY "read_all_medicamentos"
  ON medicamentos_base FOR SELECT USING (true);

CREATE POLICY "read_all_dosis"
  ON dosis_personalizadas FOR SELECT USING (true);

-- Escritura restringida a la anon key (ajusta si añades autenticación)
CREATE POLICY "write_dosis"
  ON dosis_personalizadas FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "write_medicamentos"
  ON medicamentos_base FOR ALL USING (true) WITH CHECK (true);

-- ──────────────────────────────────────────────────────────────────
--  4. VISTA ÚTIL: medicamentos con su dosis personalizada (JOIN)
-- ──────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_medicamentos_con_dosis AS
SELECT
  m.*,
  d.perro_dosis,         d.perro_unidad,
  d.perro_concentracion, d.perro_conc_unidad, d.perro_priorizar,
  d.gato_dosis,          d.gato_unidad,
  d.gato_concentracion,  d.gato_conc_unidad,  d.gato_priorizar,
  d.notas                AS notas_veterinario,
  d.updated_at           AS dosis_updated_at
FROM medicamentos_base m
LEFT JOIN dosis_personalizadas d ON d.medicamento_id = m.id;
