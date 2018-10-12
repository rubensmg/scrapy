# -*- coding: utf-8 -*-

from __future__ import print_function
from scrapy import Spider, Request
from scrapy.downloadermiddlewares.cookies import CookiesMiddleware


spider = Spider('foo')
cookies = {
    'latin1-bytes': 'á'.encode('latin1'),
    'utf8-bytes': 'á'.encode('utf8'),
    'unicode': 'á',
}
cookie_header = b'; '.join([
    b'header-latin1-bytes=' + 'á'.encode('latin1'),
    b'header-utf8-bytes=' + 'á'.encode('utf8'),
])

request = Request('https://example.org', cookies=cookies, headers={'Cookie': cookie_header})
mw = CookiesMiddleware()
mw.process_request(request, spider)


print('\nCookie header after processing:')
print(request.headers.get('Cookie'))
print()

for c in request.headers.get('Cookie').split(b'; '):
    print('-'*20)
    print('Original: ', c)
    print('UTF-8 decoded: ', c.decode('utf8'))
