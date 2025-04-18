-- +goose Up
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;




CREATE TABLE resident (
   id uuid PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   name text NOT NULL,
   last_name text,
   email text
);

CREATE TRIGGER set_timestamp_update
  BEFORE UPDATE ON resident
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_set_timestamp();



CREATE TABLE country (
   id uuid PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   name text NOT NULL,
   code text,
   population int
);
CREATE TRIGGER set_timestamp_update
  BEFORE UPDATE ON country
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_set_timestamp();
CREATE UNIQUE INDEX on country (name);
CREATE UNIQUE INDEX on country (code);
-- Openai_File: Table to store the file information of the file created by OpenAI
CREATE TABLE city (
   id uuid PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
   name text NOT NULL,
   country_id uuid REFERENCES country (id),
   population int
);
CREATE TRIGGER set_timestamp_update
  BEFORE UPDATE ON city
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_set_timestamp();

CREATE UNIQUE INDEX on city (name, country_id);

-- -- -- Openai_Vector_File: Table to store the mapping between the vector and the file. many-many relationship
CREATE TABLE resident_city (
  id uuid PRIMARY KEY NOT NULL DEFAULT gen_random_uuid(),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
  city_id uuid REFERENCES city (id),
  resident_id uuid REFERENCES resident (id),
  main_residence boolean NOT NULL DEFAULT true

);

CREATE UNIQUE INDEX on resident_city (resident_id, city_id);

CREATE TRIGGER set_timestamp_update
  BEFORE UPDATE ON resident_city
  FOR EACH ROW
  EXECUTE PROCEDURE trigger_set_timestamp();


-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin

DROP TABLE resident CASCADE;
DROP TABLE city CASCADE;
DROP TABLE country CASCADE;
DROP TABLE resident_city CASCADE;
DROP FUNCTION trigger_set_timestamp;

-- DROP TABLE map_vector CASCADE;

-- +goose StatementEnd
