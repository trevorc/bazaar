BEGIN;

------------------
-- Search Procs --
------------------

CREATE OR REPLACE FUNCTION replace_account
( p_facebook_id    bigint
, p_email          text
, p_full_name      text
, p_access_token   text
, p_tz             text
, p_profile        text
, OUT account_id integer
)
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO account
           ( facebook_id
           , email
           , full_name
           , access_token
           , tz
           , profile
           )
    VALUES ( p_facebook_id
           , p_email
           , p_full_name
           , p_access_token
           , p_tz
           , p_profile
           )
 RETURNING id
      INTO account_id;
EXCEPTION WHEN unique_violation THEN
    UPDATE account
       SET email        = p_email
         , full_name    = p_full_name
         , access_token = p_access_token
         , tz           = p_tz
         , profile      = p_profile
     WHERE facebook_id  = p_facebook_id
       AND banned_at IS NULL
 RETURNING id
      INTO account_id;
END $$;

CREATE OR REPLACE FUNCTION listing_modification_allowed_trigger()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (SELECT 1
                 FROM checkout c
                WHERE c.listing = NEW.id)
    THEN RAISE SQLSTATE 'ZX001';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER check_listing_modification_allowed
    AFTER UPDATE ON listing
    FOR EACH ROW
    EXECUTE PROCEDURE listing_modification_allowed_trigger();

COMMIT;
