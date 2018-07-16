#!/usr/bin/env python

import os
import sys
import pytz
import random
import string
import StringIO
import datetime
import operator
import itertools

import psycopg2

os.environ.setdefault('PGDATABASE', 'bazaar')
db = psycopg2.connect('')
cursor = db.cursor()

tlds = '''agrigento.it aid.pl ako.hyogo.jp asker.no asso.bj bv.nl c.bg
carrara-massa.it de.us edu.km eid.no environment.museum firenze.it
garden.museum gifu.gifu.jp go.kr go.pw gov.pl gov.st
gyokuto.kumamoto.jp hara.nagano.jp hayashima.okayama.jp
hiratsuka.kanagawa.jp hoyanger.no is-a-bookkeeper.com is-very-bad.org
katsushika.tokyo.jp koebenhavn.museum lc.it lier.no lindas.no mil.rw
moss.no nakamichi.yamanashi.jp naval.museum net.ag net.pr net.tj nf.ca
notteroy.no ol.no onagawa.miyagi.jp photography.museum radom.pl
raisa.no riik.ee s3-us-gov-west-1.amazonaws.com selfip.com
shioya.tochigi.jp snaase.no toyako.hokkaido.jp trust.museum tw.cn
uchinomi.kagawa.jp vaapste.no vestnes.no wassamu.hokkaido.jp'''.split()

def fetchall():
    while True:
        row = cursor.fetchone()
        if row is None:
            break
        yield row

r = random.Random()
with file('/usr/share/dict/words') as f:
    words = [w.strip() for w in f]

try:
    with file('/usr/share/dict/propernames') as f:
        names = [w.strip() for w in f]
except IOError:
    names = words

def randrange(upper=100, lower=None):
    if lower is None:
        lower = 8
    return xrange(1, r.randint(lower, upper))

chars = list(set(string.letters) - set(string.whitespace))

def randstr(maxlen=100, minlen=None):
    return str.join('', [r.choice(chars)
                         for _ in randrange(maxlen, minlen)])

def randword():
    return r.choice(words)

def random_email():
    return '{0}@{1}.{2}'.format(randword(), randword(), random.choice(tlds))

def random_url():
    return 'http://{0}.{1}/{2}'.format(
        randword(), random.choice(tlds), randstr(16))


def fetch_events():
    cursor.execute('TABLE seatgeek_event')
    for row in fetchall():
        yield row[0], row[1:]

def generate_accounts():
    for pk in randrange(256):
        yield pk+2, (
            r.randint(100, 1000000), # facebook_id
            random_email(),          # email
            '{0} {1}'.format(r.choice(names), randword().title()), # full_name
            randstr(64),      # access_token
            r.choice(pytz.all_timezones),
            random_url(),       # profile
        )

def generate_listings(accounts, events):
    pk = itertools.count()
    num_sellers = r.randint(4, max(len(accounts)/2, 8))
    for seller in r.sample(accounts.keys(), num_sellers):
        for event in [r.choice(events.keys()) for _ in randrange(16, 0)]:
            yield next(pk), (
                event,
                seller,
                50 * r.randint(0, 300), # price
                r.choice([
                    None,
                    ' '.join(randword() for _ in randrange(20)),
                ]),         # message
            )

def generate_customers(accounts):
    num_accounts = r.randint(4, len(accounts))
    for account in r.sample(accounts.keys(), num_accounts):
        customer = 'cus_{}'.format(randstr(24))
        yield customer, (account,)

def generate_cards(accounts, customers):
    num_customers = r.randint(3*len(customers)/4, len(customers))
    now = datetime.datetime.now(pytz.utc).date()
    for customer in r.sample(customers.keys(), num_customers):
        expiration = now + datetime.timedelta(r.randint(0, 3650))
        card = 'card_{}'.format(randstr(24))
        yield card, (
            customer,
            randstr(17, 17),      # fingerprint
            accounts[customers[customer][0]][2], # full_name
            str(expiration.replace(day=1)),
            r.randint(1001, 9999), # card_last4
            r.choice([
                'Visa',
                'American Express',
                'Mastercard',
                'Discover',
                'JCB',
                'Diners Club',
                None,
            ]),                 # card_type
        )

def generate_claims(cards, listings):
    pk = itertools.count()
    min_len = min(len(cards), len(listings))
    num_listings = r.randint(min(min_len, 4), 3*min_len/4)
    for listing in r.sample(listings.keys(), num_listings):
        card = r.choice(list(cards.viewkeys() - {listings[listing][1]}))
        yield next(pk), (listing, card)

def generate_tickets(claims):
    pk = itertools.count()
    num_claims = r.randint(2, len(claims))
    for claim in r.sample(claims.keys(), num_claims):
        yield next(pk), (claim,)

def generate_pdfs(tickets):
    num_tickets = r.randint(2, len(tickets))
    for ticket in r.sample(tickets.keys(), num_tickets):
        yield ticket, (randstr(24),)

def as_file(d):
    s = StringIO.StringIO()
    for k, r in d.iteritems():
        s.write('{0}\t{1}\n'.format(str(k), '\t'.join([
            r'\N' if val is None else str(val)
            for val in r])))
    s.seek(0)
    return s

def main():
    events = dict(fetch_events())
    accounts = dict(generate_accounts())
    listings = dict(generate_listings(accounts, events))
    customers = dict(generate_customers(accounts))
    cards = dict(generate_cards(accounts, customers))
    claims = dict(generate_claims(cards, listings))
    tickets = dict(generate_tickets(claims))
    pdfs = dict(generate_pdfs(tickets))

    cursor.execute('TRUNCATE stripe_customer CASCADE')
    cursor.execute('TRUNCATE listing CASCADE')
    cursor.execute('DELETE FROM account WHERE id > %s', (2,))

    cursor.copy_from(
        as_file(accounts), 'account',
        columns=('id', 'facebook_id', 'email', 'full_name',
                 'access_token', 'tz', 'profile'))
    cursor.copy_from(
        as_file(listings), 'listing',
        columns=('id', 'event', 'seller', 'price', 'message'))
    cursor.copy_from(
        as_file(customers), 'stripe_customer',
        columns=('id', 'account'))
    cursor.copy_from(
        as_file(cards), 'stripe_card',
        columns=('id', 'customer', 'fingerprint', 'full_name',
                 'expiration', 'last4', 'brand'))
    cursor.copy_from(as_file(claims), 'claim',
                     columns=('id', 'listing', 'stripe_card'))
    cursor.copy_from(as_file(tickets), 'ticket',
                     columns=('id', 'claim'))
    cursor.copy_from(as_file(pdfs), 'pdf',
                     columns=('ticket', 'filename'))

    for table in ['account', 'listing', 'claim', 'ticket']:
        cursor.execute("SELECT setval('{0}_id_seq', "
                       "(SELECT MAX(id) FROM {0}))".format(table))
    cursor.execute('COMMIT')

if __name__ == '__main__':
    main()
