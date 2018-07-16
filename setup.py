#!/usr/bin/env python

import setuptools

setuptools.setup(
    name='api',
    version='0.1.0',
    description='Business logic API',
    author='Trevor Caira',
    author_email='trevor@bitba.se',
    packages=['api'],
    install_requires=[
        'argparse==1.1',
        'jsonschema==2.0.0',
        'psycopg2==2.5.1',
        'pytz',
        'requests==1.2.3',
        'selector==0.9.4',
        'stripe==1.9.5',
        'Werkzeug==0.9.3',
    ],
)
