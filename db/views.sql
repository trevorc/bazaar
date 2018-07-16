BEGIN;

-----------------
-- Event Views --
-----------------

CREATE OR REPLACE VIEW full_event_search AS
SELECT e.id             AS id
     , e.title          AS title
     , e.datetime_local AS datetime_local
     , e.datetime_utc   AS datetime_utc
     , coalesce(p.performer_names, '')
                        AS performer_names
     , p.performer_image AS performer_image
     , y.city           AS city__id
     , v.id             AS venue__id
     , v.name           AS venue__name
     , v.address        AS venue__address
     , v.postal_code    AS venue__postal_code
     , v.city           AS venue__city
     , v.state          AS venue__state
     , s.terms          AS search__terms
  FROM seatgeek_event e
  JOIN event_search s
    ON e.id = s.id
  JOIN venue_city y
    ON e.venue = y.venue
  JOIN seatgeek_venue v
    ON e.venue = v.id
  LEFT JOIN performer_summary p
    ON e.id = p.event
 WHERE e.datetime_utc > (current_timestamp - interval '5 minutes')
 ORDER BY e.datetime_utc ASC;

-------------------
-- Account Views --
-------------------

CREATE OR REPLACE VIEW full_accounts AS
SELECT a.*
     , u.id AS stripe_customer
  FROM account a
  LEFT JOIN stripe_customer u
    ON a.id = u.account;

CREATE OR REPLACE FUNCTION modify_account_row()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    CASE TG_OP
    WHEN 'INSERT' THEN
        INSERT INTO account
               ( facebook_id, email, full_name
               , access_token, tz, profile )
        VALUES ( NEW.facebook_id, NEW.email, NEW.full_name
               , NEW.access_token, NEW.tz, NEW.profile );
    WHEN 'UPDATE' THEN
        UPDATE account a
           SET facebook_id  = NEW.facebook_id
             , email        = NEW.email
             , full_name    = NEW.full_name
             , access_token = NEW.access_token
             , tz           = NEW.tz
             , profile      = NEW.profile
         WHERE a.id = NEW.id
           AND a.banned_at IS NULL;
    END CASE;

    IF NEW.stripe_customer IS NOT NULL THEN
        INSERT INTO stripe_customer (id, account)
             VALUES (NEW.stripe_customer, NEW.id)
          RETURNING id INTO NEW.stripe_customer;
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER modify_account
    INSTEAD OF UPDATE ON full_accounts
    FOR EACH ROW
    EXECUTE PROCEDURE modify_account_row();

CREATE OR REPLACE VIEW default_card AS
SELECT c.*
  FROM stripe_card c
 WHERE c.created_at
       = (SELECT MAX(c2.created_at)
            FROM stripe_card c2
           WHERE c.customer = c2.customer);

------------------
-- Ticket Views --
------------------

CREATE OR REPLACE VIEW connectedness AS
SELECT a1.facebook_id AS facebook_id
     , a2.facebook_id AS friend
     , f1.facebook_id AS first_degree
     , f2.facebook_id AS second_degree
  FROM account a1
  JOIN account a2
    ON a1.id <> a2.id
  LEFT JOIN friendship f1
    ON a1.facebook_id = f1.facebook_id
   AND a2.facebook_id = f1.friend
  LEFT JOIN second_degree_friendship f2
    ON a1.facebook_id = f2.facebook_id
   AND a2.facebook_id = f2.friend;

CREATE OR REPLACE VIEW full_listings AS
SELECT l.id             AS id
     , l.created_at     AS created_at
     , l.price          AS price
     , l.message        AS message
     , y.city           AS city__id
     , s.id             AS seller__id
     , s.created_at     AS seller__created_at
     , s.facebook_id    AS seller__facebook_id
     , s.full_name      AS seller__full_name
     , s.profile        AS seller__profile
     , s.email          AS seller__email
     , s.tz             AS seller__tz
     , e.id             AS event__id
     , e.title          AS event__title
     , p.performer_names AS event__performer_names
     , p.performer_image AS event__performer_image
     , e.datetime_local AS event__datetime_local
     , e.datetime_utc   AS event__datetime_utc
     , e.venue          AS event__venue__id
     , v.name           AS event__venue__name
     , v.address        AS event__venue__address
     , v.city           AS event__venue__city
     , v.state          AS event__venue__state
     , v.postal_code    AS event__venue__postal_code
  FROM listing l
  JOIN account s
    ON l.seller = s.id
  JOIN seatgeek_event e
    ON l.event = e.id
  JOIN venue_city y
    ON e.venue = y.venue
  JOIN seatgeek_venue v
    ON e.venue = v.id
  LEFT JOIN performer_summary p
    ON e.id = p.event
  LEFT JOIN claim m
    ON l.id = m.listing
 WHERE l.deleted_at IS NULL
   AND m.id IS NULL
   AND e.datetime_utc > (current_timestamp - interval '5 minutes');

-- To find the connectedness for a particular buyer, filter on
-- the facebook_id of the buyer's account.
CREATE OR REPLACE VIEW available_listings AS
SELECT l.*
     , c.facebook_id    AS buyer
     , c.first_degree   AS first_degree
     , c.second_degree  AS second_degree
  FROM full_listings l
  JOIN connectedness c
    ON l.seller__facebook_id = c.friend
 ORDER BY c.first_degree ASC
        , c.second_degree ASC
        , l.event__datetime_utc ASC;

CREATE OR REPLACE FUNCTION modify_listing_row()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    CASE TG_OP
    WHEN 'INSERT' THEN
        INSERT INTO listing ( event, seller, price, message )
             VALUES ( NEW.event__id, NEW.seller__id, NEW.price, NEW.message )
          RETURNING id, created_at
        INTO STRICT NEW.id;
    WHEN 'UPDATE' THEN
        UPDATE listing l
           SET event = NEW.event__id
             , price = NEW.price
             , message = NEW.message
         WHERE l.id = OLD.id;
    WHEN 'DELETE' THEN
        UPDATE listing l
           SET deleted_at = current_timestamp
         WHERE l.id = OLD.id;
    END CASE;
    SELECT * FROM full_listings l WHERE l.id = NEW.id
      INTO STRICT NEW;
    RETURN NEW;
END $$;

CREATE TRIGGER modify_full_listings
    INSTEAD OF INSERT OR UPDATE OR DELETE ON full_listings
    FOR EACH ROW
    EXECUTE PROCEDURE modify_listing_row();

CREATE OR REPLACE VIEW checkout AS
SELECT c.*
     , r.customer
  FROM claim c
  JOIN stripe_card r
    ON c.stripe_card = r.id
  JOIN stripe_customer u
    ON r.customer = u.id
  JOIN listing l
    ON c.listing = l.id
  LEFT JOIN ticket t
    ON c.id = t.claim
 WHERE t.id IS NULL
   AND u.account <> l.seller;

CREATE OR REPLACE FUNCTION modify_checkout_row()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO claim (listing, stripe_card)
         VALUES ( NEW.listing
                , COALESCE(
                  NEW.stripe_card,
                  (SELECT r.id
                     FROM default_card r
                    WHERE r.customer = NEW.customer))
                )
      RETURNING id INTO NEW.id;
    RETURN NEW;
END $$;

CREATE TRIGGER modify_checkout
    INSTEAD OF INSERT ON checkout
    FOR EACH ROW
    EXECUTE PROCEDURE modify_checkout_row();

COMMIT;
