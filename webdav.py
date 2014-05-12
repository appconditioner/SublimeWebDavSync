# WebDAV client library with automatic Basic or Digest Authorization
#
# Copyright (C) 2014-2014 Rene Kretzschmar. All Rights Reserved.
# 
# The DAV part of this library is copied from davlib.py 
# (Copyright (C) 1998-2000 Guido van Rossum. All Rights Reserved. Written by Greg Stein. 
#	Given to Guido. Licensed using the Python license.)
# 
# The digest header build code is copied from auth.py - see https://github.com/kennethreitz/requests
#

import sys

if sys.version_info[0] > 2:
	from queue import Queue
	from http.client import HTTPSConnection
	from http.client import HTTPConnection
	from urllib.parse import urlparse
else:
	from httplib import HTTPSConnection
	from httplib import HTTPConnection
	from urlparse import urlparse
	from Queue import Queue

import urllib
import string
import types
import mimetypes

import hashlib
import base64
import re
import time
import os


BASIC_AUTH = "basic"
DIGEST_AUTH = "digest"

INFINITY = 'infinity'
XML_DOC_HEADER = '<?xml version="1.0" encoding="utf-8"?>'
XML_CONTENT_TYPE = 'text/xml; charset="utf-8"'

# block size for copying files up to the server
BLOCKSIZE = 16384


class WebDAV(HTTPSConnection, object):
	def __init__(self, protocol=None, host=None, username=None, password=None):

		self.protocol = protocol
		if self.protocol == "https":
			self.default_port = 443
		else:
			self.default_port = 80

		self.username = username
		self.password = password
		self.auth = None
		self.basic_auth_header = None
		self.nc = 0
		self.qop = None
		self.nonce = None
		self.opaque = None		
		self.algorithm = None
		self.last_nonce = None
		super(WebDAV, self).__init__(host=host)

	def connect(self):
		if self.protocol == "https":
			HTTPSConnection.connect(self)
		else:
			HTTPConnection.connect(self)

	def get(self, url, extra_hdrs={ }):
		return self._request('GET', url, extra_hdrs=extra_hdrs)

	def head(self, url, extra_hdrs={ }):
		return self._request('HEAD', url, extra_hdrs=extra_hdrs)

	def post(self, url, data={ }, body=None, extra_hdrs={ }):
		headers = extra_hdrs.copy()

		assert body or data, "body or data must be supplied"
		assert not (body and data), "cannot supply both body and data"
		if data:
			body = ''
			for key, value in data.items():
				if isinstance(value, types.ListType):
					for item in value:
						body = body + '&' + key + '=' + urllib.quote(str(item))
				else:
					body = body + '&' + key + '=' + urllib.quote(str(value))
			body = body[1:]
			headers['Content-Type'] = 'application/x-www-form-urlencoded'

		return self._request('POST', url, body, headers)

	def options(self, url='*', extra_hdrs={ }):
		return self._request('OPTIONS', url, extra_hdrs=extra_hdrs)

	def trace(self, url, extra_hdrs={ }):
		return self._request('TRACE', url, extra_hdrs=extra_hdrs)

	def put(self, url, contents,
			content_type=None, content_enc=None, extra_hdrs={ }):

		if not content_type:
			content_type, content_enc = mimetypes.guess_type(url)

		headers = extra_hdrs.copy()
		if content_type:
			headers['Content-Type'] = content_type
		if content_enc:
			headers['Content-Encoding'] = content_enc
		return self._request('PUT', url, contents, headers)

	def delete(self, url, extra_hdrs={ }):
		return self._request('DELETE', url, extra_hdrs=extra_hdrs)

	def propfind(self, url, body=None, depth=None, extra_hdrs={ }):
		headers = extra_hdrs.copy()
		headers['Content-Type'] = XML_CONTENT_TYPE
		if depth is not None:
			headers['Depth'] = str(depth)
		return self._request('PROPFIND', url, body, headers)

	def proppatch(self, url, body, extra_hdrs={ }):
		headers = extra_hdrs.copy()
		headers['Content-Type'] = XML_CONTENT_TYPE
		return self._request('PROPPATCH', url, body, headers)

	def mkcol(self, url, extra_hdrs={ }):
		return self._request('MKCOL', url, extra_hdrs=extra_hdrs)

	def move(self, src, dst, extra_hdrs={ }):
		headers = extra_hdrs.copy()
		headers['Destination'] = dst
		return self._request('MOVE', src, extra_hdrs=headers)

	def copy(self, src, dst, depth=None, extra_hdrs={ }):
		headers = extra_hdrs.copy()
		headers['Destination'] = dst
		if depth is not None:
			headers['Depth'] = str(depth)
		return self._request('COPY', src, extra_hdrs=headers)

	def lock(self, url, owner='', timeout=None, depth=None,
			scope='exclusive', type='write', extra_hdrs={ }):
		headers = extra_hdrs.copy()
		headers['Content-Type'] = XML_CONTENT_TYPE
		if depth is not None:
			headers['Depth'] = str(depth)
		if timeout is not None:
			headers['Timeout'] = timeout
		body = XML_DOC_HEADER + \
				'<DAV:lockinfo xmlns:DAV="DAV:">' + \
				'<DAV:lockscope><DAV:%s/></DAV:lockscope>' % scope + \
				'<DAV:locktype><DAV:%s/></DAV:locktype>' % type + \
				'<DAV:owner>' + owner + '</DAV:owner>' + \
				'</DAV:lockinfo>'
		return self._request('LOCK', url, body, extra_hdrs=headers)

	def unlock(self, url, locktoken, extra_hdrs={ }):
		headers = extra_hdrs.copy()
		if locktoken[0] != '<':
			locktoken = '<' + locktoken + '>'
		headers['Lock-Token'] = locktoken
		return self._request('UNLOCK', url, extra_hdrs=headers)


	def _update_authorization_info(self,resp):
		if(resp.status == 401):
			# get the headers
			headers = resp.getheaders()
			# and finish this request
			resp.read()

			# obtain the auth info
			authInfo = None
			for header in headers:
				if header[0] == "www-authenticate":
					authInfo = header[1]

			if authInfo:
				if DIGEST_AUTH in authInfo.lower():
					# configure digest auth
					self.auth = DIGEST_AUTH
					# mandatory infos
					nonce = re.search('nonce="([^"]+)"', authInfo)
					realm = re.search('realm="([^"]+)"', authInfo)

					if realm and nonce:
						self.realm = realm.group(1)

						nonce_val = nonce.group(1)

						if self.nonce == None or self.nonce != nonce_val:
							self.nc = 0
							self.nonce = nonce_val
							qop = re.search('qop="([^"]+)"', authInfo)
							self.qop = qop.group(1) if qop != None else None
							opaque = re.search('opaque="([^"]+)"', authInfo)
							self.opaque = opaque.group(1) if opaque != None else None
							algorithm = re.search('algorithm="([^"]+)"', authInfo)
							self.algorithm = algorithm.group(1) if algorithm != None else None
							return None

				elif BASIC_AUTH in authInfo.lower():
					# Basic auth
					self.auth = BASIC_AUTH
					auth_token = base64.encodestring("%s:%s" %(self.username, self.password)).strip()
					self.basic_auth_header = "Basic %s" %auth_token
					return None

		# in all other cases return the response as is						
		return resp

	def _authorization_header(self, method, url):
		if self.auth == BASIC_AUTH:
			return self.basic_auth_header
		elif self.auth == DIGEST_AUTH:
			return self._build_digest_header(method, url)

	def _build_digest_header(self, method, url):

		realm = self.realm
		nonce = self.nonce
		qop = self.qop
		algorithm = self.algorithm
		opaque = self.opaque

		if algorithm is None:
			_algorithm = 'MD5'
		else:
			_algorithm = algorithm.upper()

		if _algorithm == 'MD5' or _algorithm == 'MD5-SESS':
			def md5_utf8(x):
				if isinstance(x, str):
					x = x.encode('utf-8')
				return hashlib.md5(x).hexdigest()
			hash_utf8 = md5_utf8
		elif _algorithm == 'SHA':
			def sha_utf8(x):
				if isinstance(x, str):
					x = x.encode('utf-8')
				return hashlib.sha1(x).hexdigest()
			hash_utf8 = sha_utf8

		KD = lambda s, d: hash_utf8("%s:%s" % (s, d))

		if hash_utf8 is None:
			return None

		entdig = None
		p_parsed = urlparse(url)
		path = p_parsed.path
		if p_parsed.query:
			path += '?' + p_parsed.query

		A1 = '%s:%s:%s' % (self.username, realm, self.password)
		A2 = '%s:%s' % (method, path)

		HA1 = hash_utf8(A1)
		HA2 = hash_utf8(A2)

		if nonce == self.last_nonce:
			self.nonce_count += 1
		else:
			self.nonce_count = 1

		ncvalue = '%08x' % self.nonce_count
		s = str(self.nonce_count).encode('utf-8')
		s += nonce.encode('utf-8')
		s += time.ctime().encode('utf-8')
		s += os.urandom(8)

		cnonce = (hashlib.sha1(s).hexdigest()[:16])
		noncebit = "%s:%s:%s:%s:%s" % (nonce, ncvalue, cnonce, qop, HA2)
		if _algorithm == 'MD5-SESS':
			HA1 = hash_utf8('%s:%s:%s' % (HA1, nonce, cnonce))

		if qop is None:
			respdig = KD(HA1, "%s:%s" % (nonce, HA2))
		elif qop == 'auth' or 'auth' in qop.split(','):
			respdig = KD(HA1, noncebit)
		else:
			return None

		self.last_nonce = nonce

		base = 'username="%s", realm="%s", nonce="%s", uri="%s", ' \
				'response="%s"' % (self.username, realm, nonce, path, respdig)
		if opaque:
			base += ', opaque="%s"' % opaque
		if algorithm:
			base += ', algorithm="%s"' % algorithm
		if entdig:
			base += ', digest="%s"' % entdig
		if qop:
			base += ', qop="auth", nc=%s, cnonce="%s"' % (ncvalue, cnonce)

		return 'Digest %s' % (base)

	def _request(self, method, url, body=None, extra_hdrs={}):

		# TODO: this is a bit dirty
		retryHeaderName = "AuthDAV-Retry"
		retryHeader = retryHeaderName in extra_hdrs

		if retryHeader:
			del extra_hdrs[retryHeaderName]

		if self.auth:
			extra_hdrs['Authorization'] = self._authorization_header(method, url)

		self.request(method, url, body, extra_hdrs)
		resp = self._update_authorization_info(self.getresponse())

		if resp:
			return resp

		if retryHeader == False:
			extra_hdrs[retryHeaderName] = "true"
			return self._request(method, url, body, extra_hdrs)

		# auth info is up to date
		return resp
