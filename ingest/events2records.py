#!/usr/bin/env python

# converts event JSON, one per line, to COPY-formatted TSV for each
# constituent relation in the event JSON

import sys
import json
import argparse
import functools


quote_replacements = [
    ('\b', r'\b'),
    ('\f', r'\f'),
    ('\n', r'\n'),
    ('\r', r'\r'),
    ('\t', r'\t'),
    ('\v', r'\v'),
]

def adapt_value(value):
    if value is None:
        return r'\N'
    s = unicode(value).encode('UTF-8')
    for c1, c2 in quote_replacements:
        s = s.replace(c1, c2)
    return s

def adapt_row(converter):
    @functools.wraps(converter)
    def wrapped(*args):
        rel = converter.__name__[3:]
        row = converter(*args)
        return str.join('\t', [rel] + map(adapt_value, row))
    return wrapped

@adapt_row
def to_event(event):
    return (
        None,                   # non-composite primary key
        event['id'],
        event['title'],
        event['short_title'],
        event['url'],
        event['datetime_local'],
        event['datetime_utc'] + 'Z',
        event['datetime_tbd'],
        event['venue']['id'],
        event['type'],
        event['score'],
        event['stats'].get('listing_count'),
        event['stats'].get('average_price'),
        event['stats'].get('lowest_price'),
        event['stats'].get('highest_price'),
    )

@adapt_row
def to_performer(performer):
    return (
        None,                   # non-composite primary key
        performer['id'],
        performer['name'],
        performer['short_name'],
        performer['url'],
        performer.get('image'),
        json.dumps(performer.get('images', {})),
        performer.get('score'),
        performer['slug'],
    )

@adapt_row
def to_venue(venue):
    return (
        venue['id'],
        venue['name'],
        venue.get('address') or None,
        venue.get('extended_address') or None,
        venue['city'],
        venue['postal_code'],
        venue['state'][:2].upper(),
        venue['country'],
        (venue['location']['lon'], venue['location']['lat']),
        venue.get('score'),
    )

@adapt_row
def to_event_performer(event, performer):
    return (
        event['id'],
        performer['id'],
    )

@adapt_row
def to_taxonomy(taxonomy):
    return (
        None,                   # non-composite primary key
        taxonomy['id'],
        taxonomy['name'],
        taxonomy['parent_id'],
    )

@adapt_row
def to_event_taxonomy(event, taxonomy):
    return (
        event['id'],
        taxonomy['id'],
    )

parser = argparse.ArgumentParser()
parser.add_argument('-v', action='store_true',
                    help='emit verbose debugging output')

if __name__ == '__main__':
    args = parser.parse_args()
    for line in sys.stdin:
        event = json.loads(line)
        print to_event(event)
        for performer in event.get('performers', []):
            print to_performer(performer)
            print to_event_performer(event, performer)
        if 'venue' in event:
            print to_venue(event['venue'])
        for taxonomy in event.get('taxonomies', []):
            print to_taxonomy(taxonomy)
            print to_event_taxonomy(event, taxonomy)
