import os
import six
import logging
import re
from collections import defaultdict

from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.http.cookies import CookieJar
from scrapy.utils.python import to_native_str, to_bytes

logger = logging.getLogger(__name__)


class CookiesMiddleware(object):
    """This middleware enables working with sites that need cookies"""

    def __init__(self, debug=False):
        self.jars = defaultdict(CookieJar)
        self.debug = debug

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('COOKIES_ENABLED'):
            raise NotConfigured
        return cls(crawler.settings.getbool('COOKIES_DEBUG'))

    def process_request(self, request, spider):
        if request.meta.get('dont_merge_cookies', False):
            return

        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        cookies = self._get_request_cookies(jar, request)
        for cookie in cookies:
            jar.set_cookie_if_ok(cookie, request)

        # set Cookie header
        request.headers.pop('Cookie', None)
        jar.add_cookie_header(request)
        self._debug_cookie(request, spider)

    def process_response(self, request, response, spider):
        if request.meta.get('dont_merge_cookies', False):
            return response

        # extract cookies from Set-Cookie and drop invalid/expired cookies
        cookiejarkey = request.meta.get("cookiejar")
        jar = self.jars[cookiejarkey]
        jar.extract_cookies(response, request)
        self._debug_set_cookie(response, spider)

        return response

    def _debug_cookie(self, request, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in request.headers.getlist('Cookie')]
            if cl:
                cookies = "\n".join("Cookie: {}\n".format(c) for c in cl)
                msg = "Sending cookies to: {}\n{}".format(request, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _debug_set_cookie(self, response, spider):
        if self.debug:
            cl = [to_native_str(c, errors='replace')
                  for c in response.headers.getlist('Set-Cookie')]
            if cl:
                cookies = "\n".join("Set-Cookie: {}\n".format(c) for c in cl)
                msg = "Received cookies from: {}\n{}".format(response, cookies)
                logger.debug(msg, extra={'spider': spider})

    def _format_cookie(self, cookie, request):
        # build cookie string
        decoded = {}
        for key in ('name', 'value', 'path', 'domain'):
            if not cookie.get(key):
                continue
            if isinstance(cookie[key], six.text_type):
                decoded[key] = cookie[key]
                continue
            try:
                decoded[key] = cookie[key].decode('utf8')
            except UnicodeDecodeError:
                logger.warning('Non UTF-8 encoded cookie found in request %s: %s', request, cookie)
                decoded[key] = cookie[key].decode('latin1')

        cookie_str = u'{}={}'.format(decoded.pop('name'), decoded.pop('value'))

        for key, value in decoded.items():  # path, domain
            cookie_str += u'; {}={}'.format(key.capitalize(), value)

        return cookie_str

    def _get_request_cookies(self, jar, request):
        # from 'Cookie' request header
        cookie_header = request.headers.get('Cookie') or b''
        cookie_list_bytes = re.split(b';\s*', cookie_header)
        cookie_list_unicode = []
        for cookie_bytes in cookie_list_bytes:
            try:
                cookie_unicode = cookie_bytes.decode('utf8')
            except UnicodeDecodeError:
                logger.warning('Non UTF-8 encoded cookie found in request %s: %s', request, cookie_bytes)
                cookie_unicode = cookie_bytes.decode('latin1')
            cookie_list_unicode.append(cookie_unicode)
        headers = {'Set-Cookie': cookie_list_unicode}
        response = Response(request.url, headers=headers)
        cookies_from_header = jar.make_cookies(response, request)

        # from request 'cookies' attribute
        if isinstance(request.cookies, dict):
            cookie_list = [{'name': k, 'value': v} for k, v in \
                    six.iteritems(request.cookies)]
        else:
            cookie_list = request.cookies

        cookies = [self._format_cookie(x, request) for x in cookie_list]
        headers = {'Set-Cookie': cookies}
        response = Response(request.url, headers=headers)
        cookies_from_attribute = jar.make_cookies(response, request)

        return cookies_from_header + cookies_from_attribute
