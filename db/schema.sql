BEGIN;

-------------------------
-- Aggregate Functions --
-------------------------

CREATE OR REPLACE FUNCTION first_agg(anyelement, anyelement)
    RETURNS anyelement
    LANGUAGE SQL
    IMMUTABLE STRICT
AS $$
    SELECT $1;
$$;

CREATE AGGREGATE first (
    sfunc    = first_agg,
    basetype = anyelement,
    stype    = anyelement
);


--------------------------
-- Geographic Relations --
--------------------------

CREATE UNIQUE INDEX ON tl_2013_us_state(stusps);

-- Search category cities
CREATE TABLE city
( id       serial PRIMARY KEY
, name     text   NOT NULL
, location geography(point, 4326) NOT NULL
, CHECK (length(name) <= 85)
);

----------------------------
-- Seatgeek API Relations --
----------------------------

CREATE TABLE seatgeek_performer
( id         integer PRIMARY KEY
, name       text    NOT NULL
, short_name text    NOT NULL
, url        text    NOT NULL
, image      text
, images     json    NOT NULL
, score      real
, slug       text    NOT NULL
);

CREATE TABLE seatgeek_venue
( id          integer   PRIMARY KEY
, name        text      NOT NULL
, address     text
, extended_address text
, city        text      NOT NULL
, postal_code text      NOT NULL
, state       text      NOT NULL REFERENCES tl_2013_us_state(stusps)
, country     text      NOT NULL
, location    geography(point, 4326) NOT NULL
, score       real

, CHECK (length(address)   BETWEEN 1 AND 96)
, CHECK (length(city)      BETWEEN 1 AND 85)
);

CREATE INDEX ON seatgeek_venue USING gist (location);

CREATE TABLE seatgeek_event
( id             integer     PRIMARY KEY
, title          text        NOT NULL
, short_title    text        NOT NULL
, url            text        NOT NULL
, datetime_local timestamp   NOT NULL
, datetime_utc   timestamptz NOT NULL
, datetime_tbd   boolean     NOT NULL
, venue          integer     NOT NULL REFERENCES seatgeek_venue
, type           text        NOT NULL
, score          real
, listing_count  integer
, average_price  numeric(16, 2)
, lowest_price   numeric(16, 2)
, highest_price  numeric(16, 2)
);

CREATE INDEX ON seatgeek_event (datetime_utc);

CREATE TABLE seatgeek_taxonomy
( id        integer PRIMARY KEY
, name      text    NOT NULL
, parent_id integer REFERENCES seatgeek_taxonomy
);

CREATE TABLE seatgeek_event_performers
( event     integer NOT NULL REFERENCES seatgeek_event
, performer integer NOT NULL REFERENCES seatgeek_performer
, PRIMARY KEY (event, performer)
);

CREATE TABLE seatgeek_event_taxonomies
( event    integer NOT NULL REFERENCES seatgeek_event
, taxonomy integer NOT NULL REFERENCES seatgeek_taxonomy
, PRIMARY KEY (event, taxonomy)
);

----------------------
-- Bazaar Relations --
----------------------

CREATE TABLE time_zones AS
SELECT name FROM pg_timezone_names();
ALTER TABLE time_zones ADD PRIMARY KEY (name);

CREATE TABLE account
( id              serial      PRIMARY KEY
, created_at      timestamptz NOT NULL DEFAULT current_timestamp
, is_staff        boolean     NOT NULL DEFAULT false
, facebook_id     bigint      NOT NULL UNIQUE
, email           text        NOT NULL UNIQUE
, full_name       text        NOT NULL
, access_token    text        NOT NULL
, tz              text        NOT NULL REFERENCES time_zones
, banned_at       timestamptz
, profile         text

, CHECK (length(access_token) BETWEEN 1 AND 1024)
, CHECK (length(email)        BETWEEN 5 AND 72)
, CHECK (length(full_name)    BETWEEN 1 AND 96)
, CHECK (length(profile)      BETWEEN 5 AND 2053)
, CHECK (created_at           < banned_at)
, CHECK (email                SIMILAR TO '%_@_%')
, CHECK (profile              SIMILAR TO 'https?://%')
, CHECK (facebook_id          > 0)
);

CREATE INDEX ON account (facebook_id) WHERE banned_at IS NULL;

CREATE TABLE stripe_customer
( id         text        PRIMARY KEY
, account    integer     NOT NULL UNIQUE REFERENCES account
, created_at timestamptz NOT NULL DEFAULT current_timestamp

, CHECK (id         LIKE 'cus_%')
, CHECK (length(id) BETWEEN 5 AND 128)
);

CREATE TABLE stripe_card
( id          text        PRIMARY KEY
, customer    text        NOT NULL REFERENCES stripe_customer
, created_at  timestamptz NOT NULL DEFAULT current_timestamp
, fingerprint text        NOT NULL
, full_name   text        NOT NULL
, expiration  date        NOT NULL
, last4       integer     NOT NULL
, brand       text

, CHECK (id                     LIKE 'card_%')
, CHECK (length(id)             BETWEEN 6 AND 128)
, CHECK (length(fingerprint)    = 16)
, CHECK (extract(day from expiration) = 1)
, CHECK (length(full_name)      BETWEEN 1 AND 96)
, CHECK (last4                  BETWEEN 0 AND 9999)
);

CREATE TABLE friendship
( facebook_id bigint NOT NULL REFERENCES account(facebook_id)
, friend      bigint NOT NULL

, PRIMARY KEY (facebook_id, friend)
, CHECK (facebook_id > 0)
, CHECK (friend      > 0)
);

CREATE INDEX ON friendship (facebook_id);

CREATE TABLE listing
( id          serial         PRIMARY KEY
, created_at  timestamptz    NOT NULL DEFAULT current_timestamp
, deleted_at  timestamptz
, event       integer        NOT NULL REFERENCES seatgeek_event
, seller      integer        NOT NULL REFERENCES account
, price       integer        NOT NULL --in cents
, message     text

, CHECK (length(message)    BETWEEN 1 AND 2048)
, CHECK (created_at         < deleted_at)
, CHECK (price              >= 0)
);

CREATE TABLE claim
( id               serial      PRIMARY KEY
, created_at       timestamptz NOT NULL DEFAULT current_timestamp
, listing          integer     NOT NULL UNIQUE REFERENCES listing
, stripe_card      text        NOT NULL REFERENCES stripe_card
);

CREATE TABLE ticket
( id         serial      PRIMARY KEY
, created_at timestamptz NOT NULL DEFAULT current_timestamp
, claim      integer     NOT NULL UNIQUE REFERENCES claim
);

CREATE TABLE pdf
( ticket     integer     PRIMARY KEY REFERENCES ticket
, created_at timestamptz NOT NULL DEFAULT current_timestamp
, filename   text        NOT NULL UNIQUE

, CHECK (length(filename) BETWEEN 1 AND 255)
);

----------------------
-- Search Relations --
----------------------

CREATE MATERIALIZED VIEW venue_city AS
SELECT v.id          AS venue
     , y.id          AS city
  FROM seatgeek_venue v
  JOIN city y
    ON ST_DWithin(v.location, y.location, 40000) -- 40 km
   AND ST_Distance(v.location, y.location) =
       (SELECT MIN(ST_Distance(v2.location, y2.location))
          FROM seatgeek_venue v2
          JOIN city y2
            ON ST_DWithin(v2.location, y2.location, 50000)
         WHERE v.id = v2.id);

CREATE UNIQUE INDEX ON venue_city (venue) WITH (fillfactor=100);

CREATE MATERIALIZED VIEW performer_summary AS
SELECT ep.event AS event
     , string_agg(p.name, ', ' ORDER BY p.score DESC)
       AS performer_names
     , first(p.image ORDER BY p.score DESC)
       AS performer_image
  FROM seatgeek_event_performers ep
  JOIN seatgeek_performer p
    ON ep.performer = p.id
 GROUP BY ep.event;

CREATE UNIQUE INDEX ON performer_summary (event) WITH (fillfactor=100);


CREATE MATERIALIZED VIEW event_search AS
SELECT e.id AS id
     , setweight(to_tsvector('english', e.title), 'A')
    || setweight(to_tsvector('english', coalesce(string_agg(p.name, ', '), '')), 'B')
    || setweight(to_tsvector('english', v.name), 'C')
    AS terms
  FROM seatgeek_event e
  JOIN seatgeek_venue v
    ON e.venue = v.id
  LEFT JOIN seatgeek_event_performers ep
    ON e.id = ep.event
  LEFT JOIN seatgeek_performer p
    ON ep.performer = p.id
 WHERE e.type IN ('concert', 'music_festival')
 GROUP BY e.id, v.id;

CREATE UNIQUE INDEX ON event_search (id) WITH (fillfactor=100);
CREATE INDEX ON event_search USING gin (terms) WITH (fastupdate=off);

-- Force the query planner to use a nestloop plan for this query.
-- Ensure that when refreshing this view, the planner is correctly
-- hinted as well.
SET enable_hashjoin = false;
SET enable_mergejoin = false;

-- Second degree friendships such that all second degree friends have
-- accounts. Note that this view is not suitable as the basis for a
-- third-degree friendship query, since third-degree friends may be
-- connected through friends without accounts.
CREATE MATERIALIZED VIEW second_degree_friendship AS
SELECT f1.facebook_id AS facebook_id
     , f2.facebook_id AS friend
  FROM friendship f1
  JOIN friendship f2
    ON f1.friend = f2.facebook_id
   AND f1.facebook_id <> f2.facebook_id
  JOIN friendship f3
    ON f2.friend = f3.facebook_id
 GROUP BY f1.facebook_id, f2.facebook_id;

SET enable_hashjoin = default;
SET enable_mergejoin = default;

CREATE INDEX ON second_degree_friendship (facebook_id, friend);


COMMIT;
