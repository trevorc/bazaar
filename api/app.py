# app.py - application logic for the rest api

import os
import re
import sys
import json
import shlex
import locale
import urllib
import decimal
import datetime
import operator
import functools
import itertools
import traceback
import subprocess
import email.utils
import pkg_resources
import email.mime.text

import pytz
import stripe
import psycopg2
import selector
import requests
import werkzeug
import jsonschema
import werkzeug.http
import werkzeug.wsgi
import werkzeug.utils
import psycopg2.errorcodes
import werkzeug.exceptions
import werkzeug.contrib.wrappers
import werkzeug.contrib.securecookie

from . import db, errors


#################
# Configuration #
#################

COOKIE_DOMAIN = None
SENDMAIL = '/usr/sbin/sendmail -t -oi'

# Required - defaults unused
API_HOST = None
SECRET_KEY = None
STRIPE_SECRET_KEY = None
WWW_HOST = None

_configuration_schema = {
    'type': 'object',
    'properties': {
        'API_HOST': {'type': 'string', 'pattern': 'https?://.*[^/]'},
        'SECRET_KEY': {'type': 'string'},
        'SENDMAIL': {'type': 'string'},
        'SMTP_HOST': {'type': 'string'},
        'STRIPE_SECRET_KEY': {'type': 'string', 'pattern': 'sk_.+'},
        'WWW_HOST': {'type': 'string', 'pattern': 'https?://.*[^/]'},
    },
    'required': ['SECRET_KEY', 'STRIPE_SECRET_KEY', 'WWW_HOST'],
    'additionalProperties': False,
}

def _load_configuration(requirement, env):
    configuration = json.load(pkg_resources.resource_stream(
        requirement, os.path.join('conf', '{}.json'.format(env))))
    jsonschema.validate(configuration, _configuration_schema)
    globals().update(configuration)

if 'APP_ENV' not in os.environ:
    sys.stderr.write('warning: defaulting to development (APP_ENV unset)\n')
    os.environ['APP_ENV'] = 'development'

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
_load_configuration(__name__, os.environ['APP_ENV'])

stripe.api_key = STRIPE_SECRET_KEY

# Additional constants
CITIES = {
    1: 'new-york',
    2: 'austin',
}
FROM_ADDR = 'Bazaar <noreply@bazaar.bbsvc.net>'
SETUP_PAYMENT_URL = WWW_HOST + '/#account'
UPLOAD_PDF_URL = WWW_HOST + '/#listings/{0}/{1}/fulfill'
UPLOAD_DIR = pkg_resources.resource_filename(__name__, 'uploads')

if not os.path.exists(UPLOAD_DIR):
    sys.stderr.write("creating UPLOAD_DIR `{}'".format(UPLOAD_DIR))
    os.mkdir(UPLOAD_DIR, 0700)

#############
# Utilities #
#############

DB_ERRORS = {
    'listing_already_claimed': 'ZX001',
}

def compose(f, g):
    def _compose(x):
        return f(g(x))
    return _compose

def fail_with(exc_class):
    def fail_handler(request, e):
        raise exc_class()
    return fail_handler

def NoContent():
    response = werkzeug.Response(status=204)
    del response.headers['Content-Type']
    return response

def by_constraint(**constraints):
    def handle_error_by_constraint(request, e):
        err = constraints.get(e.diag.constraint_name)
        if err is None:
            raise errors.database_error()
        raise err()
    return handle_error_by_constraint

##############
# Middleware #
##############

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, '__json__'):
            return dict(o.__json__())
        elif isinstance(o, datetime.datetime):
            o = o.replace(microsecond=0)
            return (o if o.tzinfo is None
                    else o.astimezone(pytz.utc)).isoformat()
        return super(JSONEncoder, self).default(o)

class JSONResponse(werkzeug.Response):
    def __init__(self, response, status=None, headers=None):
        super(JSONResponse, self).__init__(
            json.dumps(response, cls=JSONEncoder, indent=2)+'\n',
            status=status, headers=headers,
            mimetype='application/json')

def request_middleware(middleware):
    @functools.wraps(middleware)
    def decorator(func):
        @functools.wraps(func)
        def _request_middleware(request):
            middleware(request)
            return func(request)
        return _request_middleware
    return decorator

def response_middleware(middleware):
    @functools.wraps(middleware)
    def decorator(func):
        @functools.wraps(func)
        def _response_middleware(request):
            response = func(request)
            middleware(response)
            return response
        return _response_middleware
    return decorator

def wrap_errors(func):
    @functools.wraps(func)
    def _wrap_errors(request):
        try:
            return func(request)
        except errors.APIError, error:
            traceback.print_exc(file=request.errors)
            return error
        except werkzeug.exceptions.BadRequest, e:
            traceback.print_exc(file=request.errors)
            return errors.not_understood(e.description)
        except:
            traceback.print_exc(file=request.errors)
            try:
                body = json.dumps(request.json)
            except werkzeug.exceptions.BadRequest:
                body = '<unknown>'
            request.errors.write(
                'request json: {0}\n'
                'request url: {1}\n'
                'request user agent: {2}\n'.format(
                    body, request.url,
                    request.headers.get('User-Agent', '-')))
            return errors.unknown_error()
    return _wrap_errors

@response_middleware
def wrap_no_cache(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Expires']       = 'Thu, 01 Jan 1970 00:00:00 GMT'
    response.headers['Pragma']        = 'no-cache'

@request_middleware
def wrap_format_request(func):
    pass

def wrap_format_response(func):
    @functools.wraps(func)
    def _wrap_format_response(request):
        result = func(request)
        if isinstance(result, werkzeug.BaseResponse):
            return result
        return JSONResponse(result)
    return _wrap_format_response

class SecureCookie(werkzeug.contrib.securecookie.SecureCookie):
    serialization_method = json

@request_middleware
def wrap_session_auth(request):
    session = SecureCookie.load_cookie(request, secret_key=SECRET_KEY)
    request.account = Account(id=session['account']) \
                      if session is not None and 'account' in session \
                      else None

def wrap_sql_errors(**kwargs):
    error_handlers = {
        (DB_ERRORS[name]
         if name in DB_ERRORS
         else getattr(psycopg2.errorcodes, name.upper())): handler
        for name, handler in kwargs.iteritems()}
    def middleware(func):
        @functools.wraps(func)
        def _wrap_sql_errors(request):
            try:
                return func(request)
            except psycopg2.Error, e:
                traceback.print_exc(file=request.errors)
                handler = error_handlers.get(e.pgcode)
                if handler is None:
                    raise errors.database_error()
                return handler(request, e)
        return _wrap_sql_errors
    return middleware

def with_db(func):
    @functools.wraps(func)
    def _with_db(request):
        with db.connect():
            return func(request)
    return _with_db

core_meta_schema = json.load(pkg_resources.resource_stream(
    jsonschema.__name__, 'schemas/draft4.json'))

def format_schema(schema):
    return '\n\nParameters:\n    {}\n'.format(
        json.dumps(schema, indent=4).replace('\n', '\n    ').rstrip())

def validate(schema):
    jsonschema.validate(schema, core_meta_schema)
    @request_middleware
    def _validate(request):
        try:
            jsonschema.validate(
                request.args
                if request.method == 'GET'
                else request.form
                if request.content_type == 'multipart/form-data'
                else request.json,
                schema)
        except jsonschema.ValidationError, e:
            raise errors.invalid_request(e)
    return _validate

def account_required(fetch=False):
    @request_middleware
    def _account_required(request):
        if not request.account:
            raise errors.invalid_session()
        request.account = Account.find_one(request.account.id) \
            if fetch \
            else Account(id=request.account.id)
    return _account_required

@request_middleware
def listing_required(request):
    request.listing = Listing.find_one(
        int(request.routing_vars['id']),
        where='seller__id=%s',
        params=[request.account.id])


############
# Facebook #
############

def facebook_fetch(access_token, resource=None, **params):
    params['access_token'] = access_token
    response = requests.get(
        str.join('/', ['https://graph.facebook.com/me'] +
                 ([] if resource is None else [resource])),
        params=params)
    if response.status_code == 200:
        return response.json()
    if 400 <= response.status_code < 500:
        raise errors.facebook_auth(response.json()['error']['message'])
    raise errors.facebook_misc(response.json())

def get_facebook_picture(access_token, size):
    picture = facebook_fetch(access_token, 'picture',
                             type='square', redirect='false')
    if not picture['data']['is_silhouette']:
        return picture['data']['url']


##########
# Models #
##########

class ModelMeta(type):
    def __new__(cls, name, bases, cls_attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, cls_attrs)
        attrs = {
            'pk_field': 'id',
            'db_schema': 'public',
            'db_table': name.lower(),
            'rel_fields': {},
        }
        attrs.update(cls_attrs)
        if 'db_fields' not in attrs:
            with db.connect():
                cols = db.column_names('%(db_schema)s.%(db_table)s' % attrs)
            rel_columns = {'{0}__{1}'.format(field, rel.pk_field)
                           for field, rel in attrs['rel_fields'].iteritems()}
            attrs['db_fields'] = tuple(
                column.split('__', 1)[0]
                if column in rel_columns
                else column
                for column in cols)
        if 'save_fields' not in attrs:
            attrs['save_fields'] = tuple(
                column
                for column in attrs['db_fields']
                if column != attrs['pk_field'])
        return type.__new__(cls, name, bases, attrs)

class Model(object):
    __metaclass__ = ModelMeta

    def __init__(self, **kwargs):
        for field in self.db_fields:
            setattr(self, field, kwargs.get(field))

    def adapt(self, row):
        rel_rows = {}
        for k, v in row.iteritems():
            rel = k.split('__', 1)
            if len(rel) == 2:
                rel_rows.setdefault(rel[0], {})[rel[1]] = v

        row = dict(row)
        for rel, model in self.rel_fields.iteritems():
            row[rel] = model().adapt(rel_rows.get(rel, {}))
        for field, value in row.iteritems():
            setattr(self, field, value)
        return self

    @classmethod
    def find_one(cls, pk=None, db_table=None, where=None, params=None,
                 order_by=None):
        try:
            return next(cls.find(pk, db_table, where, params, order_by, 1))
        except StopIteration:
            raise errors.not_found(cls.db_table, {'pk': pk})

    @classmethod
    def find(cls, pk=None, db_table=None, where=None, params=None,
             order_by=None, limit=None):
        if where is None != params is None:
            raise ValueError('must supply both where and params')
        params = [] if params is None else list(params)
        if pk is not None:
            where = '{}=%s'.format(cls.pk_field) \
                if where is None \
                else '{0} AND {1}=%s'.format(where, cls.pk_field)
            params.append(pk)
        if db_table is None:
            db_table = cls.db_table
        order_by = '' if order_by is None \
                   else ' ORDER BY ' + order_by
        limit = '' if limit is None \
                else ' LIMIT ' + str(int(limit))
        query = 'SELECT * FROM {0} WHERE {1}{2}{3}'.format(
            db_table, where, order_by, limit)
        for row in db.execute(query, params):
            yield cls().adapt(row)

    def _get_pk(self):
        return getattr(self, self.__class__.pk_field)

    def _set_pk(self, val):
        setattr(self, self.__class__.pk_field, val)

    pk = property(_get_pk, _set_pk)

    @classmethod
    def db_field_name(cls, field):
        return '{0}__{1}'.format(field, cls.rel_fields[field].pk_field) \
            if field in cls.rel_fields \
            else field

    def db_field_value(self, field):
        return getattr(self, field).pk \
            if field in self.rel_fields \
            else getattr(self, field)

    def save(self, force_insert=False):
        cls = self.__class__
        fields = [(cls.db_field_name(field), self.db_field_value(field))
                  for field in cls.save_fields]
        if force_insert or self.pk is None:
            query = 'INSERT INTO {0} ({1}) VALUES ({2}) RETURNING *'.format(
                cls.db_table,
                str.join(',', map(operator.itemgetter(0), fields)),
                str.join(',', itertools.repeat('%s', len(fields))))
            params = map(operator.itemgetter(1), fields)
        else:
            updates = ['{}=%s'.format(field) for field, _ in fields]
            query = 'UPDATE {0} SET {1} WHERE {2}=%s RETURNING *'.format(
                cls.db_table, str.join(', ', updates), cls.pk_field)
            params = map(operator.itemgetter(1), fields) + [self.pk]
        row = db.execute_one(query, params)
        return self.adapt(row)


def zip_fields(*fields):
    def __json__(self):
        return zip(fields, operator.attrgetter(*fields)(self))
    return __json__

class Venue(Model):
    db_table = 'seatgeek_venue'
    __json__ = zip_fields('id', 'name', 'address', 'postal_code',
                          'city', 'state')

word_boundary = re.compile(r'\W+', re.UNICODE)

def parse_query(query):
    words = filter(None, word_boundary.split(query))
    return unicode.join(u' & ', words) + u':*'

class Event(Model):
    db_table = 'full_event_search'
    rel_fields = {'venue': Venue}

    __json__ = zip_fields('id', 'title', 'performer_names', 'performer_image',
                          'venue', 'datetime_utc', 'datetime_local')

    @property
    def timestamp(self):
        return str.join(
            ' ', self.datetime_local.strftime('%a %b %e %l:%M %p').split())

    @classmethod
    def search(cls, city, query, limit=None):
        where = "city__id=%s AND to_tsquery('english', %s) @@ search__terms"
        return cls.find(where=where, params=(city, parse_query(query)),
                        limit=limit or 20)

class Account(Model):
    db_table = 'full_accounts'
    save_fields = ('facebook_id', 'email', 'full_name', 'access_token',
                   'tz', 'profile', 'stripe_customer')

    def __json__(self, full=False):
        yield 'id', self.id
        yield 'created_at', self.created_at
        yield 'full_name', self.full_name
        yield 'tz', self.tz
        yield 'profile', self.profile
        if full:
            yield 'email', self.email
            yield 'facebook_id', self.facebook_id
            yield 'has_card', True

    @classmethod
    def login(self, facebook_id, email, name, access_token, tz, picture):
        pk = db.callproc_one(
            'replace_account',
            facebook_id, email, name, access_token, tz, picture)[0]
        return Account.find_one(pk)

class Listing(Model):
    db_table = 'full_listings'
    rel_fields = {'event': Event, 'seller': Account}
    save_fields = ('event', 'seller', 'price', 'message')

    __json__ = zip_fields('id', 'created_at', 'event', 'seller',
                          'price', 'message')

    def __json__(self, viewer=None):
        yield 'id', self.id
        yield 'created_at', self.created_at
        yield 'event', self.event
        yield 'seller', self.seller
        yield 'price', self.price
        yield 'message', self.message
        if viewer is not None:
            yield 'is_own', viewer.id == self.seller.id
        if hasattr(self, 'first_degree') and hasattr(self, 'second_degree'):
            yield 'connection', 1 \
                if self.first_degree \
                else 2 if self.second_degree \
                else None

    @property
    def display_price(self):
        return locale.currency(decimal.Decimal(self.price)/100)

    @classmethod
    def search(cls, city, facebook_id):
        sql = '''
        SELECT *
          FROM available_listings
         WHERE city__id = %s
           AND buyer = %s
         LIMIT 20
        '''
        rows = db.execute(sql, params=(city, facebook_id))
        return [cls().adapt(row) for row in rows]

    @classmethod
    def own(cls, city, account):
        return cls.find(where='city__id=%s AND seller__id=%s',
                        params=(city, account))

class Card(Model):
    db_table = 'stripe_card'
    save_fields = ('id', 'customer', 'fingerprint', 'full_name',
                   'expiration', 'last4', 'brand')

    def __json__(self):
        yield 'full_name', self.full_name
        yield 'expiration', self.expiration.strftime('%Y-%m')
        yield 'last4', '%04d' % self.last4
        yield 'brand', self.brand

class Checkout(Model):
    # rel_fields = {'buyer': Account, 'listing': Listing}
    save_fields = ('customer', 'listing', 'stripe_card')
    __json__ = zip_fields('id', 'listing')

class Pdf(Model):
    pk_field = 'ticket'

    def make_link(self):
        expires = datetime.datetime.utcnow() + datetime.timedelta(14)
        token = SecureCookie(secret_key=SECRET_KEY)
        token['pdf'] = self.pk
        return u'{0}/pdfs?token={1}'.format(
            API_HOST, urllib.quote(token.serialize(expires=expires)))

##########
# Emails #
##########

def send_email(recipient, subject, body):
    message = email.mime.text.MIMEText(body)
    message['From'] = FROM_ADDR
    message['To'] = email.utils.formataddr(recipient)
    message['Subject'] = subject
    sendmail = subprocess.Popen(
        shlex.split(SENDMAIL),
        stdin=subprocess.PIPE)

    try:
        sendmail.communicate(message.as_string())
        sendmail.stdin.close()
    finally:
        sendmail.wait()

def Email(subject, template):
    body = pkg_resources.resource_string(
        __name__, 'emails/{}.txt'.format(template))
    def _send(*recipients, **kwargs):
        assert None not in kwargs.viewvalues()
        for recipient in recipients:
            message = body.format(recipient=recipient, **kwargs)
            send_email((recipient.full_name, recipient.email),
                       subject.format(**kwargs), message)
    return _send

send_claim_submitted_email = Email(
    subject='Ticket request submitted -- {event.title}',
    template='claim_submitted')
send_claim_received_email = Email(
    subject='Someone wants your ticket to {event.title}!',
    template='claim_received')
send_ticket_email = Email(
    subject='Purchase confirmed -- {event.title}',
    template='ticket')
send_ticket_unavailable_email = Email(
    subject='Ticket unavailable -- {event.title}',
    template='ticket_unavailable')


############
# Handlers #
############

class Request(werkzeug.Request,
              werkzeug.contrib.wrappers.RoutingArgsRequestMixin,
              werkzeug.contrib.wrappers.JSONRequestMixin):
    errors = werkzeug.utils.environ_property('wsgi.errors')

def ping(request):
    return werkzeug.Response('ok\n')

@validate({
    'type': 'object',
    'properties': {
        'city': {'type': 'string', 'pattern': '[1-9][0-9]*'},
        'limit': {'type': 'string', 'pattern':'[1-9][0-9]*'},
        'q': {'type': 'string', 'minLength': 2},
    },
    'required': ['city', 'q'],
    'additionalProperties': False})
@with_db
def search_events(request):
    '''Autocompleting search for events in the database.'''

    request.errors.write('searching events city={0} q={1}\n'.format(
        request.args['city'], request.args['q']))
    limit = request.args.get('limit') and min(int(request.args['limit']), 20)
    return list(Event.search(int(request.args['city']),
                             request.args['q'], limit=limit))

@with_db
@account_required(True)
def view_account(request):
    return request.account.__json__(full=True)

@with_db
@account_required(True)
def view_card(request):
    request.errors.write('fetching card for account={0} customer={1}\n'.format(
        request.account.id, request.account.stripe_customer))
    return Card.find_one(
        where='customer=%s',
        params=(request.account.stripe_customer,),
        order_by='created_at DESC')

@validate({
    'type': 'object',
    'properties': {
        'access_token': {'type': 'string'},
        'tz': {'type': 'string'},
    },
    'required': ['access_token', 'tz'],
    'additionalProperties': False})
@with_db
def login(request):
    '''Login with facebook. Creates a session cookie.'''

    fb = facebook_fetch(request.json['access_token'])
    picture = get_facebook_picture(request.json['access_token'], 'square')
    account = Account.login(fb['id'], fb['email'], fb['name'],
                            request.json['access_token'],
                            request.json['tz'], picture)
    response = JSONResponse(account)
    expires = datetime.datetime.utcnow() + datetime.timedelta(30)
    SecureCookie({'account': account.id}, secret_key=SECRET_KEY).save_cookie(
        response, httponly=True, expires=expires, force=True,
        domain=COOKIE_DOMAIN)
    return response

@validate({
    'type': 'object',
    'properties': {
        'city': {'type': 'string', 'pattern': '[1-9][0-9]*'},
    },
    'required': ['city'],
    'additionalProperties': False})
@with_db
@account_required(True)
def search_listings(request):
    return [dict(listing.__json__(request.account))
            for listing in Listing.search(int(request.args['city']),
                                          request.account.facebook_id)]

@with_db
@validate({
    'type': 'object',
    'properties': {
        'city': {'type': 'string', 'pattern': '[1-9][0-9]*'},
    },
    'required': ['city'],
    'additionalProperties': False})
@account_required()
def view_my_listings(request):
    return [dict(listing.__json__(request.account))
            for listing in Listing.own(int(request.args['city']),
                                       request.account.id)]

@validate({
    'type': 'object',
    'properties': {
        'event': {'type': 'integer', 'minimum': 1},
        'price': {'type': 'integer', 'minimum': 0}, # in cents
        'message': {'type': ['null', 'string'], 'minLength': 1},
    },
    'required': ['event', 'price'],
    'additionalProperties': False})
@account_required()
@with_db
@wrap_sql_errors(foreign_key_violation=by_constraint(
    listing_event_fkey=functools.partial(errors.not_found, 'event')))
def create_listing(request):
    '''Offer a new ticket for an existing event.'''

    request.errors.write('creating listing seller={0} event={1} price={2}\n'.format(
        request.account.id, request.json['event'], request.json['price']))
    return Listing(event=Event(id=request.json['event']),
                   seller=request.account,
                   price=request.json['price'],
                   message=request.json.get('message')).save()

@with_db
@account_required()
def view_listing(request):
    '''View an available listing for buyers and sellers.'''

    listing = Listing.find_one(int(request.routing_vars['id']))
    return dict(listing.__json__(request.account))

@validate({
    'type': 'object',
    'properties': {
        'price': {'type': 'integer', 'minimum': 0}, # in cents
        'message': {'type': ['null', 'string'], 'minLength': 1},
    },
    'additionalProperties': False})
@with_db
@account_required()
@listing_required
def update_listing(request):
    '''Modify the price or message associated with your listing.'''

    request.errors.write('updating listing id={0} seller={1} update={2}\n'.format(
        request.listing.id, request.listing.seller.id, json.dumps(request.json)))
    if 'price' in request.json:
        request.listing.price = request.json['price']
    if 'message' in request.json:
        request.listing.message = request.json['message']

    # cannot use ``request.listing.save()`` -- INSTEAD OF UPDATE
    # triggers are currently not permitted on views that depend on
    # materialized views
    sql = '''
    UPDATE listing
       SET price=%s, message=%s
     WHERE id=%s AND seller=%s AND deleted_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM claim c WHERE c.listing=%s)
    RETURNING *
    '''
    params = (request.listing.price, request.listing.message,
              request.listing.id, request.account.id, request.listing.id)
    return request.listing.adapt(db.execute_one(sql, params))

@with_db
@listing_required
@wrap_sql_errors(listing_already_claimed=fail_with(errors.listing_claimed))
def remove_listing(request):
    '''Remove a listing. Listing must not have been claimed.'''

    # cannot use ``request.listing.save()`` -- see above.
    sql = '''
    UPDATE listing
       SET deleted_at = current_timestamp
     WHERE id=%s AND seller=%s AND deleted_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM claim c WHERE c.listing=%s)
    '''
    params = (request.listing.id, request.account.id, request.listing.id)
    db.execute(sql, params)
    return NoContent()


@validate({
    'type': 'object',
    'properties': {
        'listing': {'type': 'number'},
        'card_token': {'type': 'string', 'pattern': 'tok_.+'},
    },
    'required': ['listing'],
    'additionalProperties': False})
@with_db
@account_required(True)
@wrap_sql_errors(unique_violation=by_constraint(
    claim_listing_key=errors.listing_claimed))
def create_checkout(request):
    '''Update the credit card information for a customer through Stripe.'''

    request.errors.write('creating checkout account={0} listing={1} '
                         'customer={2}\n'.format(
                             request.account.id, request.json['listing'],
                             request.account.stripe_customer))

    if request.account.stripe_customer is None and \
       request.json.get('card_token') is None:
        raise errors.card_missing()

    customer = None             # stripe customer
    stripe_card = None          # claim with default card
    listing = Listing.find_one(request.json['listing'])

    # Create or update stripe customer
    if request.account.stripe_customer is None:
        customer = stripe.Customer.create(
            description='account={0} email={1}'.format(
                request.account.id, request.account.email),
            card=request.json['card_token'])
        request.account.stripe_customer = customer.id
        request.errors.write('adding customer={0} to account={0}\n'.format(
            request.account.stripe_customer, request.account.id))
        request.account.save()
    elif request.json.get('card_token') is not None:
        customer = stripe.Customer.retrieve(request.account.stripe_customer)
        customer.card = request.json['card_token']
        customer.save()

    if customer is not None:           # card updated; save it
        assert request.json.get('card_token') is not None
        stripe_card = customer.default_card # claim with this card
        card = customer.cards.data[0]
        assert stripe_card == card.id
        request.errors.write('creating card {}\n'.format(
            json.dumps(card.to_dict(), sort_keys=True,
                       cls=stripe.StripeObjectEncoder)))
        expiration = datetime.date(card.exp_year, card.exp_month, 1)
        Card(id=card.id, customer=customer.id, fingerprint=card.fingerprint,
             full_name=card.name, expiration=expiration, last4=card.last4,
             brand=card.type).save(force_insert=True)

    checkout = Checkout(customer=request.account.stripe_customer,
                        stripe_card=stripe_card, listing=listing.id).save()
    request.errors.write(
        'sending claim received email to {}\n'.format(
            email.utils.formataddr((listing.seller.full_name,
                                    listing.seller.email))))
    city_slug = CITIES[listing.city__id]
    send_claim_received_email(
        recipient=listing.seller, buyer=request.account,
        event=listing.event,
        upload_pdf_url=UPLOAD_PDF_URL.format(city_slug, listing.id),
        setup_payment_url=SETUP_PAYMENT_URL)

    return checkout

@with_db
def view_checkout(request):
    pass

@validate({
    'type': 'object',
    'properties': {
        'fulfill': {
            'type': ['boolean', 'string'],
            'enum': ['true', False]
        },
        'checkout': {
            'type': 'string',
            'pattern': '[0-9]+',
        },
    },
    'required': ['fulfill'],
    'additionalProperties': False})
@with_db
def create_ticket(request):
    sys.stderr.write('form: %s\n' % request.form)
    sys.stderr.write('files: %s\n' % request.files)
    if request.content_type == 'multipart/form-data':
        if 'ticket' not in request.files:
            raise errors.file_missing('ticket')
        filename = werkzeug.secure_filename(request.files['ticket'])
        path = os.path.join(UPLOAD_DIR, filename)
        request.files['ticket'].save(path)
    else:
        pass

@with_db
def view_ticket(request):
    pass

class FileResponse(werkzeug.BaseResponse):
    def __init__(self, path):
        werkzeug.BaseResponse.__init__(self, mimetype='application/pdf')
        self.path = path
        st = os.stat(path)
        self.headers['Content-Length'] = str(st.st_size)
        self.headers['Last-Modified'] = werkzeug.http.http_date(st.st_mtime)

    def __call__(self, environ, start_response):
        start_response('200 OK', self.headers.to_wsgi_list())
        return werkzeug.wsgi.wrap_file(environ, file(self.path))

@validate({
    'type': 'object',
    'properties': {
        'token': {'type': 'string'},
    },
    'required': ['token'],
    'additionalProperties': False})
@with_db
def view_pdf(request):
    token = SecureCookie.unserialize(request.args['token'], SECRET_KEY)
    if 'pdf' not in token:
        raise errors.bad_request('invalid token')
    pdf = Pdf.find_one(token['pdf'])
    return FileResponse(os.path.join(UPLOAD_DIR, pdf.filename))

router = selector.Selector(wrap=reduce(compose, [
    Request.application,
    wrap_errors,
    wrap_no_cache,
    wrap_format_request,
    wrap_format_response,
    wrap_session_auth,
]))
router.add('/ping', GET=ping)
router.add('/account', GET=view_account, PUT=login)
router.add('/account/listings', GET=view_my_listings)
router.add('/card', GET=view_card)
router.add('/events', GET=search_events)
router.add('/listings', GET=search_listings, POST=create_listing)
router.add('/listings/{id:digits}', GET=view_listing, PUT=update_listing, DELETE=remove_listing)
router.add('/checkouts', POST=create_checkout)
router.add('/checkouts/{id:digits}', GET=view_checkout)
router.add('/tickets', POST=create_ticket)
router.add('/tickets/{id:digits}', GET=view_ticket)
router.add('/pdfs', GET=view_pdf)
