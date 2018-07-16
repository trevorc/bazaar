# errors.py - application error classes

import json

import werkzeug.exceptions


class APIError(werkzeug.exceptions.HTTPException):
    def __init__(self, context=None, params=None):
        self.context = context
        self.params  = params
        super(APIError, self).__init__()

    def get_body(self, environ):
        return json.dumps({
            'code': self.error, 'message': self.message,
            'context': self.context, 'params': self.params,
            'error': self.__class__.__name__,
        }, indent=2)

    def get_headers(self, environ):
        return [('Content-Type', 'application/json')]

class invalid_session(APIError):
    code    =  400
    error   = 1000
    message = 'invalid session key'
    headers = {'WWW-Authenticate': 'Basic realm="API"'}

class invalid_request(APIError):
    code    =  400
    error   = 1010
    message = 'invalid request body'

    def __init__(self, error):
        super(invalid_request, self).__init__(
            context=error.message,
            params={
                'validator': error.validator,
                'schema': error.schema,
                'instance': error.instance,
            })

class not_understood(APIError):
    code    =  400
    error   = 1020
    message = 'request not understood'

class forbidden(APIError):
    code    =  403
    error   = 1030

class not_found(APIError):
    code    =  404
    error   = 1040
    message = 'no such resource'

class card_missing(APIError):
    code    =  400
    error   = 1050
    message = 'no card available'

class file_missing(APIError):
    code    =  400
    error   = 1060
    message = 'expected file upload'

class bad_request(APIError):
    code    =  400
    error   = 1099
    message = 'bad request'

    def __init__(self, message, context=None):
        self.message = message
        super(bad_request, self).__init__(context=context)

class facebook_auth(APIError):
    code    =  400
    error   = 2000
    message = 'Facebook OAuth error'

class facebook_misc(APIError):
    code    =  400
    error   = 2010
    message = 'misc Facebook error'

class listing_claimed(APIError):
    code    =  403
    error   = 3000
    message = 'listing already claimed'

class unknown_error(APIError):
    code    =  500
    error   = 9000
    message = 'unknown error'

class database_error(APIError):
    code    =  500
    error   = 9010
    message = 'unknown database error'
