#!/usr/bin/env python

import re
import sys
import json

decoder = json.JSONDecoder()
ws = re.compile(r'^\s*')

def explode(line):
    i = 0
    while i < len(line):
        obj, n = decoder.raw_decode(line[i:])
        for event in obj['events']:
            yield event
        i += n
        i += len(ws.match(line[i:]).group(0))

if __name__ == '__main__':
    for line in sys.stdin:
        for event in explode(line):
            print json.dumps(event)
