CREATE TABLE component_categories (
 code text PRIMARY KEY, label_zh text NOT NULL, description text NOT NULL
);
CREATE TABLE characteristic_definitions (
 code text PRIMARY KEY, label_zh text NOT NULL,
 storage text NOT NULL CHECK(storage IN ('identity','specification')),
 value_kind text NOT NULL CHECK(value_kind IN ('number','integer','text')),
 canonical_unit text, feature_group text NOT NULL,
 minimum numeric, minimum_exclusive boolean NOT NULL,
 paired_parameter text REFERENCES characteristic_definitions(code) DEFERRABLE INITIALLY DEFERRED,
 bound_role text CHECK(bound_role IN ('min','max'))
);
CREATE TABLE category_characteristics (
 category text NOT NULL REFERENCES component_categories(code),
 characteristic text NOT NULL REFERENCES characteristic_definitions(code),
 expected boolean NOT NULL,
 when_termination text[] NOT NULL DEFAULT '{}',
 PRIMARY KEY(category,characteristic)
);

ALTER TABLE products ADD CONSTRAINT products_category_definition_fk
 FOREIGN KEY(category) REFERENCES component_categories(code) NOT VALID;
ALTER TABLE product_specifications ADD CONSTRAINT specifications_parameter_definition_fk
 FOREIGN KEY(parameter) REFERENCES characteristic_definitions(code) NOT VALID;
ALTER TABLE product_specifications ADD COLUMN value_state text NOT NULL DEFAULT 'known';
ALTER TABLE product_specifications ADD COLUMN state_reason text;
ALTER TABLE product_specifications DROP CONSTRAINT product_specifications_check;
ALTER TABLE product_specifications ADD CONSTRAINT specifications_value_state_check CHECK (
 (value_state='known' AND ((value_number IS NOT NULL AND value_text IS NULL)
                      OR (value_number IS NULL AND length(trim(value_text))>0)))
 OR (value_state IN ('unknown','not_applicable') AND value_number IS NULL AND value_text IS NULL
     AND state_reason IS NOT NULL AND length(trim(state_reason))>0)
);

CREATE FUNCTION validate_component_specification(
 pid bigint, field_code text, n numeric, t text, u text, cond jsonb, state text, reason text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE d characteristic_definitions%ROWTYPE; cat text; term text; other numeric;
BEGIN
 SELECT * INTO d FROM characteristic_definitions WHERE code=field_code;
 IF NOT FOUND OR d.storage<>'specification' THEN
  RAISE EXCEPTION 'Unknown specification definition: %',field_code USING ERRCODE='23514';
 END IF;
 SELECT category,termination INTO cat,term FROM products WHERE id=pid FOR UPDATE;
 IF NOT EXISTS(SELECT 1 FROM category_characteristics WHERE category=cat AND characteristic=field_code
   AND (cardinality(when_termination)=0 OR term=ANY(when_termination))) THEN
  RAISE EXCEPTION 'Characteristic % is not defined for category %',field_code,cat USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(cond) IS DISTINCT FROM 'object' OR u IS DISTINCT FROM d.canonical_unit THEN
  RAISE EXCEPTION 'Invalid conditions or canonical unit for %',field_code USING ERRCODE='23514';
 END IF;
 IF state IN ('unknown','not_applicable') THEN
  IF n IS NOT NULL OR t IS NOT NULL OR reason IS NULL OR length(trim(reason))=0 THEN
   RAISE EXCEPTION 'Unknown/not-applicable values require a reason and no value' USING ERRCODE='23514';
  END IF;
  RETURN;
 END IF;
 IF state<>'known' THEN RAISE EXCEPTION 'Invalid value state' USING ERRCODE='23514'; END IF;
 IF d.value_kind='text' THEN
  IF n IS NOT NULL OR t IS NULL OR length(trim(t))=0 THEN
   RAISE EXCEPTION 'Text value required for %',field_code USING ERRCODE='23514';
  END IF;
 ELSE
  IF n IS NULL OR t IS NOT NULL OR n::text IN ('NaN','Infinity','-Infinity')
     OR (d.value_kind='integer' AND n<>trunc(n))
     OR (d.minimum IS NOT NULL AND (n<d.minimum OR (d.minimum_exclusive AND n=d.minimum))) THEN
   RAISE EXCEPTION 'Invalid numeric value for %',field_code USING ERRCODE='23514';
  END IF;
  IF d.paired_parameter IS NOT NULL THEN
   SELECT value_number INTO other FROM product_specifications
    WHERE product_id=pid AND parameter=d.paired_parameter AND conditions=cond AND value_state='known';
   IF other IS NOT NULL AND ((d.bound_role='min' AND n>other) OR (d.bound_role='max' AND n<other)) THEN
    RAISE EXCEPTION 'Reversed range for %',field_code USING ERRCODE='23514';
   END IF;
  END IF;
 END IF;
END;
$$;
CREATE FUNCTION check_component_specification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM validate_component_specification(NEW.product_id,NEW.parameter,NEW.value_number,
  NEW.value_text,NEW.unit,NEW.conditions,NEW.value_state,NEW.state_reason);
 RETURN NEW;
END;
$$;
CREATE TRIGGER specifications_feature_validation BEFORE INSERT OR UPDATE ON product_specifications
 FOR EACH ROW EXECUTE FUNCTION check_component_specification();

CREATE FUNCTION check_component_category_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.category IS DISTINCT FROM OLD.category OR NEW.termination IS DISTINCT FROM OLD.termination) AND EXISTS(
  SELECT 1 FROM product_specifications s WHERE s.product_id=OLD.id AND NOT EXISTS(
   SELECT 1 FROM category_characteristics c WHERE c.category=NEW.category AND c.characteristic=s.parameter
    AND (cardinality(c.when_termination)=0 OR NEW.termination=ANY(c.when_termination)))) THEN
  RAISE EXCEPTION 'New category is incompatible with existing product characteristics' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER products_category_validation BEFORE UPDATE OF category,termination ON products
 FOR EACH ROW EXECUTE FUNCTION check_component_category_change();
