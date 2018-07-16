-- tsv2db.sql - load tsvs from current directory

BEGIN;
CREATE TEMPORARY TABLE seatgeek_performer_temp
( ignored bit
, LIKE seatgeek_performer
);
\copy seatgeek_performer_temp from 'performer.tsv'

LOCK seatgeek_performer;
UPDATE seatgeek_performer r
   SET (name,   short_name,   url,   image,   images,   score,   slug) =
       (t.name, t.short_name, t.url, t.image, t.images, t.score, t.slug)
  FROM seatgeek_performer_temp t
 WHERE r.id = t.id
   AND (r.name, r.short_name, r.url, r.image, r.images::text, r.score, r.slug) IS DISTINCT FROM
       (t.name, t.short_name, t.url, t.image, t.images::text, t.score, t.slug);
INSERT INTO seatgeek_performer
     SELECT id, name, short_name, url, image, images, score, slug
       FROM seatgeek_performer_temp t
      WHERE NOT EXISTS (SELECT 1 FROM seatgeek_performer r WHERE r.id = t.id);
DROP TABLE seatgeek_performer_temp;
COMMIT;

BEGIN;
CREATE TEMPORARY TABLE seatgeek_venue_temp
( id          integer   NOT NULL
, name        text      NOT NULL
, address     text
, extended_address text
, city        text      NOT NULL
, postal_code text      NOT NULL
, state       text      NOT NULL
, country     text      NOT NULL
, location    point     NOT NULL
, score       real
);
\copy seatgeek_venue_temp from 'venue.tsv'

LOCK seatgeek_venue;
UPDATE seatgeek_venue r
   SET (name, address, extended_address, city, postal_code, state, country,
        location, score) =
       (t.name, t.address, t.extended_address, t.city, t.postal_code, t.state, t.country,
        ST_MakePoint(t.location[0], t.location[1]), t.score)
  FROM seatgeek_venue_temp t
 WHERE r.id = t.id;
INSERT INTO seatgeek_venue
     SELECT id, name, address, extended_address, city, postal_code, state, country,
            ST_MakePoint(location[0], location[1]), score
       FROM seatgeek_venue_temp t
      WHERE NOT EXISTS (SELECT 1 FROM seatgeek_venue r WHERE r.id = t.id);
DROP TABLE seatgeek_venue_temp;
COMMIT;

BEGIN;
CREATE TEMPORARY TABLE seatgeek_taxonomy_temp
( ignored bit
, LIKE seatgeek_taxonomy
);
\copy seatgeek_taxonomy_temp from 'taxonomy.tsv'

LOCK seatgeek_taxonomy;
UPDATE seatgeek_taxonomy r
   SET (name, parent_id) = (t.name, t.parent_id)
  FROM seatgeek_taxonomy_temp t
 WHERE r.id = t.id;
INSERT INTO seatgeek_taxonomy
     SELECT id, name, parent_id
       FROM seatgeek_taxonomy_temp t
      WHERE NOT EXISTS (SELECT 1 FROM seatgeek_taxonomy r WHERE r.id = t.id);
DROP TABLE seatgeek_taxonomy_temp;
COMMIT;

BEGIN;
CREATE TEMPORARY TABLE seatgeek_event_temp
( ignored bit
, LIKE seatgeek_event
);
\copy seatgeek_event_temp from 'event.tsv'
LOCK seatgeek_event;
UPDATE seatgeek_event r
   SET (title, short_title, url, datetime_local, datetime_utc, datetime_tbd, venue, type,
        score, listing_count, average_price, lowest_price, highest_price) =
       (t.title, t.short_title, t.url, t.datetime_local, t.datetime_utc, t.datetime_tbd, t.venue, t.type,
        t.score, t.listing_count, t.average_price, t.lowest_price, t.highest_price)
  FROM seatgeek_event_temp t
 WHERE r.id = t.id;
INSERT INTO seatgeek_event
     SELECT id, title, short_title, url, datetime_local, datetime_utc, datetime_tbd, venue, type,
            score, listing_count, average_price, lowest_price, highest_price
       FROM seatgeek_event_temp t
      WHERE NOT EXISTS (SELECT 1 FROM seatgeek_event r WHERE r.id = t.id);
DROP TABLE seatgeek_event_temp;
COMMIT;

BEGIN;
LOCK seatgeek_event_performers;
TRUNCATE seatgeek_event_performers;
\copy seatgeek_event_performers from 'event_performer.tsv'
COMMIT;

BEGIN;
LOCK seatgeek_event_taxonomies;
TRUNCATE seatgeek_event_taxonomies;
\copy seatgeek_event_taxonomies from 'event_taxonomy.tsv'
COMMIT;

BEGIN;
REFRESH MATERIALIZED VIEW venue_city;
REFRESH MATERIALIZED VIEW event_search;
REFRESH MATERIALIZED VIEW performer_summary;
COMMIT;

ANALYZE;
