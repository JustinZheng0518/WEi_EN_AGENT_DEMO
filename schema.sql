CREATE TABLE IF NOT EXISTS documents (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 sha256 text NOT NULL UNIQUE CHECK (length(sha256)=64),
 filename text NOT NULL, source_path text NOT NULL, language text NOT NULL DEFAULT 'en',
 catalog_version text NOT NULL DEFAULT '2025',
 page_start integer NOT NULL CHECK(page_start>0),
 page_end integer NOT NULL CHECK(page_end>=page_start),
 page_count integer NOT NULL CHECK(page_count=page_end-page_start+1)
);
CREATE TABLE IF NOT EXISTS pages (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 document_id bigint NOT NULL REFERENCES documents(id),
 local_page integer NOT NULL CHECK(local_page>0),
 global_page integer NOT NULL UNIQUE CHECK(global_page>0),
 printed_page text,
 width_pt double precision NOT NULL, height_pt double precision NOT NULL,
 native_text text NOT NULL DEFAULT '', ocr_text text,
 ocr_status text NOT NULL DEFAULT 'pending' CHECK(ocr_status IN ('pending','done','failed')),
 ocr_engine text, ocr_error text, ocr_artifact text,
 UNIQUE(document_id,local_page)
);
CREATE INDEX IF NOT EXISTS pages_search_idx ON pages USING gin(to_tsvector('english', coalesce(ocr_text,native_text)));
CREATE TABLE IF NOT EXISTS evidence (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 evidence_key text NOT NULL UNIQUE,
 page_id bigint NOT NULL REFERENCES pages(id),
 region jsonb NOT NULL CHECK(jsonb_typeof(region)='array' AND jsonb_array_length(region)=4),
 quotation text NOT NULL,
 method text NOT NULL CHECK(method IN ('ocr','visual_transcription','native')),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict')),
 reviewed_by text, reviewed_at timestamptz,
 CHECK(review_status<>'reviewed' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS product_families (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 code text NOT NULL UNIQUE, name text NOT NULL, category text NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 family_id bigint NOT NULL REFERENCES product_families(id),
 model text NOT NULL, order_number text NOT NULL UNIQUE,
 category text NOT NULL, gender text CHECK(gender IN ('male','female','none')),
 termination text, contact_count integer CHECK(contact_count>0),
 pe_contacts integer CHECK(pe_contacts>=0), housing_size text,
 evidence_id bigint NOT NULL REFERENCES evidence(id),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict')),
 UNIQUE(model,order_number)
);
CREATE INDEX IF NOT EXISTS products_filter_idx ON products(category,contact_count,termination,review_status);
CREATE TABLE IF NOT EXISTS product_specifications (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 product_id bigint NOT NULL REFERENCES products(id),
 parameter text NOT NULL, value_number numeric, value_text text, unit text,
 conditions jsonb NOT NULL DEFAULT '{}',
 evidence_id bigint NOT NULL REFERENCES evidence(id),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict')),
 CHECK(value_number IS NOT NULL OR value_text IS NOT NULL),
 UNIQUE(product_id,parameter,conditions)
);
CREATE TABLE IF NOT EXISTS product_aliases (
 product_id bigint NOT NULL REFERENCES products(id), alias text NOT NULL,
 language text NOT NULL, PRIMARY KEY(product_id,alias)
);
CREATE TABLE IF NOT EXISTS product_relations (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_product_id bigint NOT NULL REFERENCES products(id),
 target_product_id bigint NOT NULL REFERENCES products(id),
 relation text NOT NULL CHECK(relation IN ('mates_with','uses_contact','uses_housing','requires_accessory','optional_accessory','alternative')),
 conditions jsonb NOT NULL DEFAULT '{}',
 evidence_id bigint NOT NULL REFERENCES evidence(id),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict')),
 CHECK(source_product_id<>target_product_id),
 UNIQUE(source_product_id,target_product_id,relation,conditions)
);
CREATE TABLE IF NOT EXISTS assembly_templates (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 code text NOT NULL UNIQUE, description text NOT NULL,
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict'))
);
CREATE TABLE IF NOT EXISTS assembly_requirements (
 template_id bigint NOT NULL REFERENCES assembly_templates(id), role text NOT NULL,
 required boolean NOT NULL, condition jsonb NOT NULL DEFAULT '{}',
 quantity_rule text NOT NULL, PRIMARY KEY(template_id,role)
);
CREATE TABLE IF NOT EXISTS compatibility_rules (
 code text PRIMARY KEY, description text NOT NULL,
 rule jsonb NOT NULL, evidence_id bigint REFERENCES evidence(id),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict'))
);
CREATE TABLE IF NOT EXISTS review_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 entity_type text NOT NULL, entity_id bigint NOT NULL,
 action text NOT NULL, actor text NOT NULL, note text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 stage text NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, status text NOT NULL CHECK(status IN ('running','done','failed')),
 details jsonb NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS product_candidates (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 page_id bigint NOT NULL REFERENCES pages(id),
 line_hash text NOT NULL,
 model_candidate text,
 order_number_candidate text NOT NULL CHECK(order_number_candidate ~ '^[0-9]{13}$'),
 source_line text NOT NULL,
 extractor_version text NOT NULL,
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','accepted','rejected')),
 warning text NOT NULL DEFAULT 'Unverified OCR; model/order association may be incorrect',
 UNIQUE(page_id,line_hash,order_number_candidate,extractor_version)
);
ALTER TABLE review_events ADD COLUMN IF NOT EXISTS changes jsonb NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS assembly_assessments (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 check_code text NOT NULL CHECK(check_code IN ('derating','mechanical_sealing','pe_termination','pinout_mounting')),
 scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
 findings jsonb NOT NULL CHECK(jsonb_typeof(findings)='object'),
 evidence_id bigint NOT NULL REFERENCES evidence(id),
 review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','reviewed','conflict'))
);
