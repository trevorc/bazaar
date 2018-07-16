# db.py - manage connecting to the database

import os
import operator
import threading
import contextlib

import psycopg2.pool
import psycopg2.extras
import psycopg2.extensions


os.environ.setdefault('PGDATABASE', 'bazaar')
_pool = psycopg2.pool.ThreadedConnectionPool(
    1, 16, '', cursor_factory=psycopg2.extras.DictCursor)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

_tls = threading.local()

@contextlib.contextmanager
def connect():
    _tls.conn = _pool.getconn()
    try:
        yield
        _tls.conn.cursor().execute('COMMIT')
    finally:
        _pool.putconn(_tls.conn)
        del _tls.conn

def get_connection():
    try:
        return _tls.conn
    except AttributeError:
        raise RuntimeError("connection not initialized "
                           "(use `with {}.connect()')".format(__name__))

def column_names(relid):
    rows = execute(
    '''SELECT attname
         FROM pg_attribute
        WHERE attrelid = %s::regclass
          AND attnum > 0
          AND NOT attisdropped
        ORDER BY attnum
    ''', params=(relid,))
    return map(operator.itemgetter('attname'), rows)

def enumerate_rows(cursor):
    while True:
        row = cursor.fetchone()
        if row is None:
            raise StopIteration
        yield row

def execute(query, params):
    cursor = get_connection().cursor()
    cursor.execute(query, params)
    return enumerate_rows(cursor)

def execute_one(query, params):
    return next(execute(query, params))

def callproc(procname, *args):
    cursor = get_connection().cursor()
    cursor.callproc(procname, args)
    return enumerate_rows(cursor)

def callproc_one(procname, *args):
    return next(callproc(procname, *args))
