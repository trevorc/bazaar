#!/usr/bin/env python

import sys
import json
import urllib
import os.path
import urllib2
import argparse
import operator
import itertools

API_ENDPOINT = 'http://api.seatgeek.com/2/events'

parser = argparse.ArgumentParser()
parser.add_argument('-a', dest='archive',
                    help='archive downloads to directory')
parser.add_argument('latitude', type=float)
parser.add_argument('longitude', type=float)

def make_request(verbose, archive, endpoint, **params):
    query = urllib.urlencode(
        sorted(params.iteritems(), key=operator.itemgetter(0)))
    url = '{0}?{1}'.format(endpoint, query)
    if verbose:
        sys.stderr.write('GET {}\n'.format(url))
    fp = urllib2.urlopen(url)
    obj = json.load(fp)
    if args.archive:
        with file(os.path.join(args.archive, query), 'w') as f:
            json.dump(obj, f)
    return obj

if __name__ == '__main__':
    args = parser.parse_args()
    verbose = bool(os.environ.get('DEBUG'))
    for page in itertools.count(1):
        obj = make_request(verbose, args.archive, API_ENDPOINT,
                           lat=args.latitude, lon=args.longitude,
                           page=page, per_page=10000, range='50mi')
        if not obj['events']:
            break
        json.dump(obj, sys.stdout)
        print
