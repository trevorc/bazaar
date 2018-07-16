#!/usr/bin/env python

import os; os.environ.setdefault('APP_ENV', 'development')
import sys; sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import argparse

import api.app

parser = argparse.ArgumentParser(
    description='Generate a link to a given PDF.')
parser.add_argument('pdf', type=int)

def main():
    args = parser.parse_args()
    with api.app.db.connect():
        print api.app.Pdf.find_one(args.pdf).make_link()

if __name__ == '__main__':
    main()
