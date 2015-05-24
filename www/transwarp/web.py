#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
A simple, lightweight, WSGI-compatible web framework.
'''

__author__ = 'Jack Bai'

import types, os, re, cgi, sys, time, datetime, functools, mimetypes, threading, logging, urllib, traceback

try:
	from cStringIO import StringIO
except ImportError:
	from StringIO import StringIO

# 全局ThreadLocal对象,thread local object for storing request and response

ctx = threading.local()

# Dict object:

class Dict(dict):
	'''
	Simple dict but support access as x.y style

	>>> d1 = Dict()
	>>> d1['x'] = 100
	>>> d1.x
	100
	>>> d1.y = 200
	>>> d1['y']
	200
	>>> d2 = Dict(a=1, b=2, c='3')
	>>> d2.c
	'3'
	>>> d2['empty']
	Traceback (most recent call last):
		...
	KeyError: 'empty'
	>>> d2.empty
	Traceback (most recent call last):
		...
	AttributeError: 'Dict' object has no attribute 'empty'
	>>> d3 = Dict(('a', 'b', 'c'), (1, 2, 3))
	>>> d3.a
	1
	>>> d3.b
	2
	>>> d3.c
	3
	'''
	def __init__(self, names=(), values=(), **kw):
		super(Dict, self).__init__(**kw)
		for k, v in zip(names, values):
			self[k] = v
		
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value

_TIMEDELTA_ZERO = datetime.timedelta(0)

# timezone as UTC+8:00, UTC-10:00

_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')

class UTC(datetime.tzinfo):
	'''
	A UTC tzinfo object.

	>>> tz0 = UTC('+00:00')
	>>> tz0.tzname(None)
	'UTC+00:00'
	>>> tz8 = UTC('+8:00')
	>>> tz8.tzname(None)
	'UTC+8:00'
	>>> tz7 = UTC('+7:30')
	>>> tz7.tzname(None)
	'UTC+7:30'
	>>> tz5 = UTC('-05:30')
	>>> tz5.tzname(None)
	'UTC-05:30'
	>>> from datetime import datetime
	>>> u = datetime.utcnow().replace(tzinfo=tz0)
	>>> l1 = u.astimezone(tz8)
	>>> l2 = u.replace(tzinfo=tz8)
	>>> d1 = u - l1
	>>> d2 = u - l2
	>>> d1.seconds
	0
	>>> d2.seconds
	28800
	'''

	def __init__(self, utc):
		utc = str(utc.strip().upper())
		mt = _RE_TZ.match(utc)
		if mt:
			minus = mt.group(1)=='-'
			h = int(mt.group(2))
			m = int(mt.group(3))
			if minus:
				h, m = (-h), (-m)
			self._utcoffset = datetime.timedelta(hours=h, minutes=m)
			self._tzname = 'UTC%s' % utc
		else:
			raise ValueError('bad utc time zone.')

	def utcoffset(self, dt):
		return self._utcoffset

	def dst(self, dt):
		return _TIMEDELTA_ZERO

	def tzname(self,dt):
		return self._tzname

	def __str__(self):
		return 'UTC tzinfo object (%s)' % self._tzname

	__repr__ = __str__

# all known response statuses

_RESPONSE_STATUSES = {
	# Information
	100: 'Continue',
	101: 'Switching Protocols',
	102: 'Processing',

	# Successful
	200: 'OK',
	201: 'Created',
	202: 'Accepted',
	203: 'Non-Authoritative Information',
	204: 'No Content',
	205: 'Reset Content',
	206: 'Partial Content',
	207: 'Multi Status',
	226: 'IM Used',

	# Redirection
	300: 'Multiple Choices',
	301: 'Moved Permanently',
	302: 'Found',
	303: 'See Other',
	304: 'Not Modified',
	305: 'Use Proxy',
	307: 'Temporary Redirect',

	# Client Error
	400: 'Bad Request',
	401: 'Unauthorized',
	402: 'Payment Required',
	403: 'Forbidden',
	404: 'Not Found',
	405: 'Method Not Allowed',
	406: 'Not Acceptable',
	407: 'Proxy Authentication Required',
	408: 'Request Timeout',
	409: 'Conflict',
	410: 'Gone',
	411: 'Length Required',
	412: 'Precondition Failed',
	413: 'Request Entity Too Large',
	414: 'Request URI Too Long',
	415: 'Unsupported Media Type',
	416: 'Requested Range Not Satisfiable',
	417: 'Expectation Failed',
	418: "I'm a teapot",
	422: 'Unprocessable Entity',
	423: 'Locked',
	424: 'Failed Dependency',
	426: 'Upgrade Required',

	# Server Error
	500: 'Internal Server Error',
	501: 'Not Implemented',
	502: 'Bad Gateway',
	503: 'Service Unavailable',
	504: 'Gateway Timeout',
	505: 'HTTP Version Not Supported',
	507: 'Insufficient Storage',
	510: 'Not Extended',
}

_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')

_RESPONSE_HEADERS = (
	'Accept-Ranges',
	'Age',
	'Allow',
	'Cache-Control',
	'Connection',
	'Content-Encoding',
	'Content-Language',
	'Content-Length',
	'Content-Location',
	'Content-MD5',
	'Content-Disposition',
	'Content-Range',
	'Content-Type',
	'Date',
	'ETag',
	'Expires',
	'Last-Modified',
	'Link',
	'Location',
	'P3P',
	'Pragma',
	'Proxy-Authenticate',
	'Refresh',
	'Retry-After',
	'Server',
	'Set-Cookie',
	'Strict-Transport-Security',
	'Trailer',
	'Transfer-Encoding',
	'Vary',
	'Via',
	'Warning',
	'WWW-Authenticate',
	'X-Frame-Options',
	'X-XSS-Protection',
	'X-Content-Type-Options',
	'X-Forwarded-Proto',
	'X-Powered-By',
	'X-UA-Compatible',
)

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwarp/1.0')

class HttpError(Exception):
	'''
	HttpError that defines http error code.

	>>> e = HttpError(404)
	>>> e.status
	'404 Not Found'
	'''
	def __init__(self, code):
		'''
		Init an HttpError with response code.
		'''
		super(HttpError, self).__init__()
		self.status = '%d %s' % (code, _RESPONSE_STATUSES[code])

	def header(self, name, value):
		if not hasattr(self, '_headers'):
			self._headers = [_HEADER_X_POWERED_BY]
		self._headers.append((name, value))

	@property
	def headers(self):
		if hasattr(self, '_headers'):
			return self._headers
		return []

	def __str__(self):
		return self.status

	__repr__ = __str__

class RedirectError(HttpError):
	'''
	RedirectError that defines http redirect code.

	>>> e = RedirectError(302, 'http://www.apple.com/')
	>>> e.status
	'302 Found'
	>>> e.location
	'http://www.apple.com/'
	'''
	def __init__(self, code, location):
		'''
		Init an HttpError with response code.
		'''
		super(RedirectError, self).__init__(code)
		self.location = location

	def __str__(self):
		return '%s, %s' % (self.status, self.location)

	__repr__ = __str__

def badrequest():
	'''
	Send a badrequest response.

	>>> raise badrequest()
	Traceback (most recent call last):
		...
	HttpError: 400 Bad Requset
	'''
	return HttpError(400)

def unauthorized():
	'''
	Send an unauthorized response.

	>>> raise unauthorized()
	Traceback (most recent call last):
		...
	HttpError: 401 Unauthorized
	'''
	return HttpError(401)

def forbidden():
	'''
	Send a forbidden response.
	
	>>> raise forbidden()
	Traceback (most recent call last):
		...
	HttpError: 403 Forbidden
	'''
	return HttpError(403)

def notfound():
	'''
	Send a not found response.

	>>> raise notfound()
	Traceback (most recent call last):
		...
	HttpError: 404 Not Found
	'''
	return HttpError(404)

def conflict():
	'''
	Send a conflict response.

	>>> raise conflict()
	Traceback (most recent call last):
		...
	HttpError: 409 Conflict
	'''
	return HttpError(409)

def internalerror():
	'''
	Send an internal error response.

	>>> raise internalerror()
	Traceback (most recent call last):
		...
	HttpError: 500 Internal Server Error
	'''
	return HttpError(500)

def redirect(location):
	'''
	Do permanent redirect.

	>>> raise redirect('http://www.itranswarp.com/')
	Traceback (most recent call last):
		...
	RedirectError: 301 Moved Permanently, http://www.itranswarp.com/
	'''
	return RedirectError(301, location)

def found(location):
	'''
	Do temporary redirect.

	>>> raise found('http://www.itranswarp.com/')
	Traceback (most recent call last):
		...
	RedirectError: 302 Found, http://www.itranswarp.com/
	'''
	return RedirectError(302, location)

def seeother(location):
	'''
	Do temporary redirect.

	>>> raise seeother('http://www.itranswarp.com/')
	Traceback (most recent call last):
		...
	RedirectError: 303 See Other, http://www.itranswarp.com/
	>>> e = seeother('http://www.itranswarp.com/seeother?r=123')
	>>> e.location
	'http://www.itranswarp.com/seeother?r=123'
	'''
	return RedirectError(303, location)

def _to_str(s):
	'''
	Convert to str.

	>>> _to_str('s123') == 's123'
	True
	>>> _to_str(u'\u4e2d\u6587') == '\xe4\xb8\xad\xe6\x96\x87'
	True
	>>> _to_str(-123) == '-123'
	True
	'''
	if isinstance(s, str):
		return s
	if isinstance(s, unicode):
		return s.encode('utf-8')
	return str(s)

def _to_unicode(s, encoding='utf-8'):
	'''
	Convert to unicode.

	>>> _to_unicode('\xe4\xb8\xad\xe6\x96\x87') == u'\u4e2d\u6587'
	True
	'''
	return s.decode('utf-8')

def _quote(s, encoding='utf-8'):
	'''
	Url quote as str.

	>>> _quote('http://example/test?a=1+')
	'http%3A//example/test%3Fa%3D1%2B'
	>>> _quote(u'hello world!')
	'hello%20world%21'
	'''
	if isinstance(s, unicode):
		s = s.encode(encoding)
	return urllib.quote(s)

def _unquote(s, encoding='utf-8'):
	'''
	Url unquote as unicode.

	>>> _unquote('http%3A//example/test%3Fa%3D1+')
	u'http://example/test?a=1+'
	'''
	return urllib.unquote(s).decode(encoding)

def get(path):
	'''
	A @get decorator.

	@get('/:id')
	def index(id):
		pass

	>>> @get('/test/:id')
	... def test():
	...     return 'ok'
	...
	>>> test.__web_route__
	'/test/:id'
	>>> test.__web_method__
	'GET'
	>>> test()
	'ok'
	'''
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'GET'
		return func
	return _decorator

def post(path):
	'''
	A @post decorator.

	>>> @post('/post/:id')
	... def testpost():
	...     return '200'
	...
	>>> testpost.__web_route__
	'/post/:id'
	>>> testpost.__web_method__
	'POST'
	>>> testpost()
	'200'
	'''
	def _decorator(func):
		func.__web_route__ = path
		func.__web_method__ = 'POST'
		return func
	return _decorator

_re_route = re.compile(r'(\:[a-zA-Z_]\w*)')

def _build_regex(path):
	r'''
	Convert route path to regex.

	>>> _build_regex('/path/to/:file')
	'^\\/path\\/to\\/(?P<file>[^\\/]+)$'
	>>> _build_regex('/:user/:comments/list')
	'^\\/(?P<user>[^\\/]+)\\/(?P<comments>[^\\/]+)\\/list$'
	>>> _build_regex(':id-:pid/:w')
	'^(?P<id>[^\\/]+)\\-(?P<pid>[^\\/]+)\\/(?P<w>[^\\/]+)$'
	'''
	re_list = ['^']
	var_list = []
	is_var = False
	for v in _re_route.split(path):
		if is_var:
			var_name = v[1:]
			var_list.append(var_name)
			re_list.append(r'(?P<%s>[^\/]+)' % var_name)
		else:
			s = ''
			for ch in v:
				if ch>='0' and ch<='9':
					s = s + ch
				elif ch>='A' and ch<='Z':
					s = s + ch
				elif ch>='a' and ch<='z':
					s = s + ch
				else:
					s = s + '\\' + ch
			re_list.append(s)
		is_var = not is_var
	re_list.append('$')
	return ''.join(re_list)

class Route(object):
	'''
	A Route object is a callable object.
	'''

	def __init__(self, func):
		self.path = func.__web_route__
		self.method = func.__web_method__
		self.is_static = _re_route.search(self.path) is None
		if not self.is_static:
			self.route = re.compile(_build_regex(self.path))
		self.func = func

	def match(self, url):
		m = self.route.match(url)
		if m:
			return m.groups()
		return None

	def __call__(self, *args):
		return self.func(*args)

	def __str__(self):
		if self.is_static:
			return 'Route(static,%s,path=%s)' % (self.method, self.path)
		return 'Route(dynamic,%s,path=%s)' % (self.method, self.path)

	__repr__ = __str__

def _static_file_generator(fpath):
	BLOCK_SIZE = 8192
	with open(fpath, 'rb') as f:
		block = f.read(BLOCK_SIZE)
		while block:
			yield block
			block  = f.read(BLOCK_SIZE)

class StaticFileRoute(object):

	def __init__(self):
		self.method = 'GET'
		self.is_static = False
		self.route - re.compile('^/static/(.+)$')

	def match(self, url):
		if url.startswith('/static/'):
			return (url[1:], )
		return None

	def __call__(self, *args):
		fpath = os.path.join(ctx.application.document_root, args[0])
		if not os.path.isfile(fpath):
			raise notfound()
		fext = os.path.splitext(fpath)[1]
		ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stream')
		return _static_file_generator(fpath)

def favicon_handler():
	return static_file_handler('/favicon.ico')

class MultipartFile(object):
	'''
	Multipart file storage get from request input.

	f = ctx.request['file']
	f.filename # 'test.png'
	f.file # file-like object
	'''
	def __init__(self, storage):
		self.filename = _to_unicode(storage.filename)
		self.file = storage.file

class Request(object):
	'''
	Request object for obtaining all http request information.
	'''

	def __init__(self, environ):
		self._environ = environ

	def _parse_input(self):
		def _convert(item):
			if isinstance(item, list):
				return [_to_unicode(i.value) for i in item]
			if item.filename:
				return MultipartFile(item)
			return _to_unicode(item.value)
		fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
		inputs = dict()
		for key in fs:
			inputs[key] = _convert(fs[key])
		return inputs

	def _get_raw_input(self):
		'''
		Get raw input as dict containing values as unicode, list or MultipartFile.
		'''
		if not hasattr(self, '_raw_input'):
			self._raw_input = self._parse_input()
		return self._raw_input

	def __getitem__(self, key):
		'''
		Get input parameter value. If the specified key has multiple value, the first one is returned.
		If the specified key is not exist, then raise KeyError.

		>>> from StringIO import StringIO
		>>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
		>>> r['a']
		u'1'
		>>> r['c']
		u'ABC'
		>>> r['empty']
		Traceback (most recent call last):
			...
		KeyError: 'empty'
		>>> b = '----WebKitFormBoundaryQQ3J8kPsjFpTmqNz'
		>>> pl = ['--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Scofield', '--%s' % b, 'Content-Disposition: form-data; name=\\"name\\"\\n', 'Lincoln', '--%s' % b, 'Content-Disposition: form-data; name=\\"file\\"; filename=\\"test.txt\\"', 'Content-Type: text/plain\\n', 'just a test', '--%s' % b, 'Content-Disposition: form-data; name=\\"id\\"\\n', '4008009001', '--%s--' % b, '']
		>>> payload = '\\n'.join(pl)
		>>> r = Request({'REQUEST_METHOD':'POST', 'CONTENT_LENGTH':str(len(payload)), 'CONTENT_TYPE':'multipart/form-data; boundary=%s' % b, 'wsgi.input':StringIO(payload)})
		>>> r.get('name')
		u'Scofield'
		>>> r.gets('name')
		[u'Scofield', u'Lincoln']
		>>> f = r.get('file')
		>>> f.filename
		u'test.txt'
		>>> f.file.read()
		'just a test'
		'''
		r = self._get_raw_input()[key]
		if isinstance(r, list):
			return r[0]
		return r

	def get(self, key, default=None):
		'''
		The same as request[key], but return default value if key is not found.

		>>> from StringIO import StringIO
		>>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
		>>> r.get('a')
		u'1'
		>>> r.get('empty')
		>>> r.get('empty', 'DEFAULT')
		'DEFAULT'
		'''
		r = self._get_raw_input().get(key, default)
		if isinstance(r, list):
			return r[0]
		return r

	def gets(self, key):
		'''
		Get multiple values for specified key.

		>>> from StringIO import StringIO
		>>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
		>>> r.gets('a')
		[u'1']
		>>> r.gets('c')
		[u'ABC', u'XYZ']
		>>> r.gets('empty')
		Traceback (most recent call last):
			...
		KeyError: 'empty'
		'''
		r = self._get_raw_input()[key]
		if isinstance(r, list):
			returnr[:]
		return [r]

	def input(self, **kw):
		'''
		Get input as dict from request, fill dict using provided default value if key not exist.

		i  = ctx.request.input(role='guest')
		i.role ==> 'guest'

		>>> from StringIO import StringIO
		>>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
		>>> i = r.input(x=2008)
		>>> i.a
		u'1'
		>>> i.b
		u'M M'
		>>> i.c
		u'ABC'
		>>> i.x
		2008
		>>> i.get('d', u'100')
		u'100'
		>>> i.x
		2008
		'''
		copy = Dict(**kw)
		raw = self._get_raw_input()
		for k, v in raw.iteritems():
			copy[k] = v[0] if isinstance(v, list) else v
		return copy

	def get_body(self):
		'''
		Get raw data from HTTP POST and return as str.

		>>> from StringIO import StringIO
		>>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
		>>> r.get_body()
		'<xml><raw/>'
		'''
		fp = self._environ['wsgi.input']
		return fp.read()

	@property
	def remote_addr(self):
		'''
		Get remote addr. Return '0.0.0.0' if cannot get remote addr.

		>>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
		>>> r.remote_addr
		'192.168.0.100'
		'''
		return self._environ.get('REMOTE_ADDR', '0.0.0.0')

	@property
	def document_root(self):
		'''
		Get raw document_root as str. Return '' if no document_root.

		>>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
		>>> r.document_root
		'/srv/path/to/doc'
		'''
		return self._environ.get('DOCUMENT_ROOT', '')

	@property
	def query_string(self):
		'''
		Get raw query string as str. Return '' if no query string.

		>>> r = Request({'QUERY_STRING': 'a=1&c=2'})
		>>> r.query_string
		'a=1&c=2'
		>>> r = Request({})
		>>> r.query_string
		''
		'''
		return self._environ.get('QUERY_STRING', '')

	@property
	def environ(self):
		'''
		Get raw environ as dict, both key, value are str.

		>>> r = Request({'REQUEST_METHOD': 'GET', 'wsgi.url_scheme':'http'})
		>>> r.environ.get('REQUEST_METHOD')
		'GET'
		>>> r.environ.get('wsgi.url_scheme')
		'http'
		>>> r.environ.get('SERVER_NAME')
		>>> r.environ.get('SERVER_NAME', 'unamed')
		'unamed'
		'''
		return self._environ

	@property
	def request_method(self):
		'''
		Get request method. The valid returned values are 'GET', 'POST', 'HEAD'.

		>>> r = Request({'REQUEST_METHOD': 'GET'})
		>>> r.request_method
		'GET'
		>>> r = Request({'REQUEST_METHOD': 'POST'})
		>>> r.request_method
		'POST'
		'''
		return self._environ['REQUEST_METHOD']

	@property
	def path_info(self):
		'''
		Get request path as str.

		>>> r = Request({'PATH_INFO': '/test/a%20b.html'})
		>>> r.path_info
		'/test/a b.html'
		'''
		return urllib.unquote(self._environ.get('PATH_INFO', ''))

	@property
	def host(self):
		'''
		Get request host as str. Default to '' if cannot get host.

		>>> r = Request({'HTTP_HOST': 'localhost:8080'})
		>>> r.host
		'localhost:8080'
		'''
		return self._environ.get('HTTP_HOST', '')

	def _get_headers(self):
		if not hasattr(self, '_headers'):
			hdrs = {}
			for k ,v in self._environ.iteritems():
				if k.startswith('HTTP_'):
					# convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
					hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
			self._headers = hdrs
		return self._headers

	@property
	def headers(self):
		'''
		Get all HTTP headers with ket as str and value as unicode. The header names are 'XXX-XXX' uppercase.

		>>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
		>>> H = r.headers
		>>> H['ACCEPT']
		u'text/html'
		>>> H['USER-AGENT']
		u'Mozilla/5.0'
		>>> L = H.items()
		>>> L.sort()
		>>> L
		[('ACCEPT', u'text/html'), ('USER-AGENT', u'Mozilla/5.0')]
		'''
		return dict(**self._get_headers())

	def header(self, headerm default=None):
		'''
		Get header from request as unicode, return None if not exist, or default if specified.
		The header name is case-insensitive such as 'USER-AGENT' or u'content-Type'.

		>>> r = Request({'HTTP_USER_AGENT': 'Mozilla/5.0', 'HTTP_ACCEPT': 'text/html'})
		>>> r.header('User-Agent')
		u'Mozilla/5.0'
		>>> r.header('USER-AGENT')
		u'Mozilla/5.0'
		>>> r.header('Accept')
		u'text/html'
		>>> r.header('Test')
		>>> r.header('Test', u'DEFAULT')
		u'DEFAULT'
		'''
		return self._get_headers().get(header.upper(), default)

	def _get_cookies(self):
		if not hasattr(self, '_cookies'):
			cookies = {}
			cookie_str = self._environ.get('HTTP_COOKIE')
			if cookie_str:
				for c in cookie_str.split(';'):
					pos = c.find('=')
					if pos>0:
						cookies[c[:pos].strip()] = _unquote(c[pos+1:])
			self._cookies = cookies
		return self._cookies

	@property
	def cookies(self):
		'''
		Return all cookies as dict. The cookie name is str and value is unicode.

		>>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
		>>> r.cookies['A']
		u'123'
		>>> r.cookies['url']
		u'http://www.example.com/'
		'''
		return Dict(**self._get_cookies())

	def cookie(self, name, default=None):
		'''
		Return specified cookie value as unicode. Default to None if cookie not exist.

		>>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
		>>> r.cookie('A')
		u'123'
		>>> r.cookie('url')
		u'http://www.example.com/'
		>>> r.cookie('test')
		>>> r.cookie('test', u'DEFAULT')
		u'DEFAULT'
		'''
		return self._get_cookies().get(name, default)

UTC_0 = UTC('+00:00')	

class Response(object):

	def __init__(self):
		self._status = '200 OK'
		self._headers = {'CONTENT_TYPE', 'text/html; charset=utf-8'}

	@property
	def headers(self):
		'''
		Return response headers as [(key1, value1), (key2, value2)...] including cookies.

		>>> r = Response()
		>>> r.headers
		[('Content-Type', 'text/html; charset=utf-8'), ('X-Powered-By', 'transwarp/1.0')]
		>>> r.set_cookie('s1', 'ok', 3600)
		>>> r.headers
		[('Content-Type', 'text/html; charset=utf-8'), ('Set-Cookie', 's1=ok; Max-Age=3600; Path=/; HttpOnly'), ('X-Powered-By', 'transwarp/1.0')]
		'''
		L = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
		if hasattr(self, '_cookies'):
			for v in self._cookies.itervalues():
				L.append(('Set-Cookie', v))
		L.append(_HEADER_X_POWERED_BY)
		return L

	def header(self, name):
		'''
		Get header by name, case-insensitive.

		>>> r = Response()
		>>> r.header('content-type')
		'text/html; charset=utf-8'
		>>> r.header('CONTENT-type')
		'text/html; charset=utf-8'
		>>> r.header('X-Powered-By')
		'''
		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
			key = name
		return self._headers.get(key)

	def unset_header(self, name):
		'''
		Unset header by name and value .

		>>> r = Response()
		>>> r.header('content-type')
		'text/html; charset=utf-8'
		>>> r.unset_header('CONTENT-type')
		>>> r.header('content-type')
		'''
		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
			key = name
		if key in self._headers:
			del self._headers[key]

	def set_header(self, name, value):
		'''
		Set header by name and value.

		>>> r = Response()
		>>> r.header('content-type')
		'text/html; charset=utf-8'
		>>> r.set_header('CONTENT-type', 'image/png')
		>>> r.header('content-TYPE')
		'image/png'
		'''
		key = name.upper()
		if not key in _RESPONSE_HEADER_DICT:
		key = name
		self._headers[key] = _to_str(value)

	@property
	def content_type(self):
		'''
		Get content type from response. This is a shortcut for header('Content-Type').

		>>> r = Response()
		>>> r.content_type
		'text/html; charset=utf-8'
		>>> r.content_type = 'application/json'
		>>> r.content_type
		'application/json'
		'''
		return self.header('CONTENT-TYPE')

	@content_type.setter
	def content_type(self, value):
		'''
		Set content type for response. This is a shortcut for set_header('CONTENT-TYPE', value).
		'''
		if value:
			self.set_header('CONTENT-TYPE', value)
		else:
			self.unset_header('CONTENT-TYPE')

	@property
	def content_length(self):
		'''
		Get content length. Return None if not set.

		>>> r = Response()
		>>> r.content_length
		>>> r.content_length = 100
		>>> r.content_length
		'100'
		'''
		return self.header('CONTENT-LENGTH')

	@content_length.setter
	def content_length(self, value):
		'''
		Set content length, the value can be int or str.

		>>> r = Response()
		>>> r.content_length = '1024'
		>>> r.content_length
		'1024'
		>>> r.content_length = 1024 * 8
		>>> r.content_length
		'8192'
		'''
		self.set_header('CONTENT-LENGTH', str(value))

	def delete_cookie(self, name):
		'''
		Delete a cookie immediately.

		Args:
			name: the cookie name.
		'''
		self.set_cookie(name, '__deleted__', expires=0)

	def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
		'''
		Set a cookie.

		Args:
			name: the cookie name.
			value: the cookie value.
			max_age: optional, seconds of cookie's max age.
			expires: optional, unix timestamp, datetime or date object that indicate an absolute time of the
					expiration time of cookie. Note that if expires specified, the max_age will be ignored.
			path: the cookie path, default to '/'.
			domain: the cookie domain, default to None.
			secure: if the cookie secure, default to False.
			http_only: if the cookie is for http only, default to True for better safty
					(client-side script cannot access cookies with HttpOnly flag).

		>>> r = Response()
		>>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
		>>> r._cookies
		{'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
		>>> r.set_cookie('company', r'Example="Limited"', expires=1342274794.123, path='/sub/')
		>>> r._cookies
		{'company': 'company=Example%3D%22Limited%22; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/sub/; HttpOnly'}
		>>> dt = datetime.datetime(2012, 7, 14, 22, 6, 34, tzinfo=UTC('+8:00'))
		>>> r.set_cookie('company', 'Expires', expires=dt)
		>>> r._cookies
		{'company': 'company=Expires; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/; HttpOnly'}
		'''
		if not hasattr(self, '_cookies'):
			self._cookies = {}
		L = ['%s=%s' % (_quote(name), _quote(value))]
		if expires is not None:
			if isinstance(expires, (float, int, long)):
				L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
			if isinstance(expires, (datetime.date, datetime.datetime)):
				L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
		elif isinstance(max_age, (int, long)):
			L.append('Max-Age=%d' % max_age)
		L.append('Path=%s' % path)
		if domain:
			L.append('Domain=%s' % domain)
		if secure:
			L.append('Secure')
		if http_only:
			L.append('HttpOnly')
		self._cookies[name] = '; '.join(L)

	def unset_cookie(self, name):
		'''
		Unset a cookie.

		>>> r = Response()
		>>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
		>>> r._cookies
		{'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
		>>> r.unset_cookie('company')
		>>> r._cookies
		{}
		'''
		if hasattr(self, '_cookies'):
			if name in self._cookies:
				del self._cookies[name]

	@property
	def status_code(self):
		'''
		Get response status code as int.

		>>> r = Response()
		>>> r.status_code
		200
		>>> r.status = 404
		>>> r.status_code
		404
		>>> r.status = '500 Internal Error'
		>>> r.status_code
		500
		'''
		return int(self._status[:3])

	@property
	def status(self):
		'''
		Get response status. Default to '200 OK'.

		>>> r = Response()
		>>> r.status
		'200 OK'
		>>> r.status = 404
		>>> r.status
		'404 Not Found'
		>>> r.status = '500 Oh My God'
		>>> r.status
		'500 Oh My God'
		'''
		return self._status

	@status.setter
	def status(self, value):
		'''
		Set response status as int or str.

		>>> r = Response()
		>>> r.status = 404
		>>> r.status
		'404 Not Found'
		>>> r.status = '500 ERR'
		>>> r.status
		'500 ERR'
		>>> r.status = u'403 Denied'
		>>> r.status
		'403 Denied'
		>>> r.status = 99
		Traceback (most recent call last):
			...
		ValueError: Bad response code: 99
		>>> r.status = 'ok'
		Traceback (most recent call last):
			...
		ValueError: Bad response code: ok
		>>> r.status = [1, 2, 3]
		Traceback (most recent call last):
			...
		TypeError: Bad type of response code.
		'''
		if isinstance(value, (int, long)):
			if value>=100 and value<=999:
				st = _RESPONSE_STATUSES.get(value, '')
				if st:
					self._status = '%d %s' % (value, st)
				else:
					self._status = str(value)
			else:
				raise ValueError('Bad response code: %d' % value)
		elif isinstance(value, basestring):
			if isinstance(value, unicode):
				value = value.encode('utf-8')
			if _RE_RESPONSE_STATUS.match(value):
				self._status = value
			else:
				raise ValueError('Bad response code: %s' % value)
		else:
			raise TypeError('Bad type of response code.')






