#!/usr/bin/env python

import os
import json
import jsonpath
import argparse

import sys; sys.path.append('.')
import explodejson

parser = argparse.ArgumentParser()
parser.add_argument('docpath')
parser.add_argument('query')

if __name__ == '__main__':
    args = parser.parse_args()
    docs = os.listdir(args.docpath)
    for doc in docs:
        path = os.path.join(args.docpath, doc)
        with file(path) as p:
            for line in p:
                for obj in explodejson.explode(line):
                    for result in jsonpath.jsonpath(obj, args.query) or []:
                        print json.dumps(result)
