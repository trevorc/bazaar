#!/usr/bin/env python

import os; os.environ.setdefault('APP_ENV', 'development')
import sys; sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import argparse
import werkzeug.wsgi
import werkzeug.serving

import api.app


###########
# Startup #
###########

parser = argparse.ArgumentParser(description='Start the Bazaar backend API.')
parser.add_argument('-a', '--addr', metavar='HOST', default='0.0.0.0',
                    help='Bind to this address.')
parser.add_argument('-p', '--port', metavar='PORT', type=int, default=8080,
                    help='Listen on this TCP port.')
parser.add_argument('-r', '--use-reloader', action='store_true',
                    help='Use code reloader.')
parser.add_argument('-s', '--static', metavar='DIR',
                    help='Serve static files from DIR')

def main():
    args = parser.parse_args()
    application = api.app.router
    if args.static:
        application = werkzeug.wsgi.SharedDataMiddleware(
            application, {'/': args.static})
    werkzeug.serving.run_simple(args.addr, args.port, application,
                                use_reloader=args.use_reloader)

if __name__ == '__main__':
    main()
