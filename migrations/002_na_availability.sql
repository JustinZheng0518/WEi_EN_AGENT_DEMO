-- NA means data not available, distinct from confirmed not_applicable.
-- Migration 001 and its dictionary remain immutable.
ALTER TABLE product_specifications DROP CONSTRAINT specifications_value_state_check;
CREATE OR REPLACE FUNCTION validate_component_specification(
 pid bigint, field_code text, n numeric, t text, u text, cond jsonb, state text, reason text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE d characteristic_definitions%ROWTYPE; cat text; term text; other numeric;
BEGIN
 SELECT * INTO d FROM characteristic_definitions WHERE code=field_code;
 IF NOT FOUND OR d.storage<>'specification' THEN
  RAISE EXCEPTION 'Unregistered specification definition: %',field_code USING ERRCODE='23514';
 END IF;
 SELECT category,termination INTO cat,term FROM products WHERE id=pid FOR UPDATE;
 IF NOT EXISTS(SELECT 1 FROM category_characteristics WHERE category=cat AND characteristic=field_code
   AND (cardinality(when_termination)=0 OR term=ANY(when_termination))) THEN
  RAISE EXCEPTION 'Characteristic % is not defined for category %',field_code,cat USING ERRCODE='23514';
 END IF;
 IF jsonb_typeof(cond) IS DISTINCT FROM 'object' OR u IS DISTINCT FROM d.canonical_unit THEN
  RAISE EXCEPTION 'Invalid conditions or canonical unit for %',field_code USING ERRCODE='23514';
 END IF;
 IF state IN ('NA','not_applicable') THEN
  IF n IS NOT NULL OR t IS NOT NULL OR reason IS NULL OR length(trim(reason))=0 THEN
   RAISE EXCEPTION 'NA/not-applicable values require a reason and no value' USING ERRCODE='23514';
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

DO $$
DECLARE old product_specifications%ROWTYPE; updated product_specifications%ROWTYPE;
BEGIN
 FOR old IN SELECT * FROM product_specifications WHERE value_state='unknown' ORDER BY id FOR UPDATE LOOP
  UPDATE product_specifications SET value_state='NA',state_reason=replace(state_reason,'未知','NA')
   WHERE id=old.id RETURNING * INTO updated;
  INSERT INTO review_events(entity_type,entity_id,action,actor,note,changes)
   VALUES('specification',old.id,'normalize_na','system:na-policy',
    'User policy: unavailable data is NA; preserve value, source and review decision.',
    jsonb_build_object('before',to_jsonb(old),'after',to_jsonb(updated)));
 END LOOP;
END;
$$;
ALTER TABLE product_specifications ADD CONSTRAINT specifications_value_state_check CHECK (
 value_state IN ('known','NA','not_applicable') AND (
  (value_state='known' AND ((value_number IS NOT NULL AND value_text IS NULL)
   OR (value_number IS NULL AND value_text IS NOT NULL AND length(trim(value_text))>0)))
  OR (value_state IN ('NA','not_applicable') AND value_number IS NULL AND value_text IS NULL
   AND state_reason IS NOT NULL AND length(trim(state_reason))>0)
 )
);
