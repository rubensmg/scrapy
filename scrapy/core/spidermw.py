"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
from functools import wraps
from itertools import chain
from types import GeneratorType

import six
from twisted.python.failure import Failure
from scrapy.exceptions import _InvalidOutput
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list


def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')


def _evaluate_iterable(iterable):
    """Evaluate an iterator to raise an exception if needed"""
    if isinstance(iterable, GeneratorType):
        out = chain()
        for element in iterable:
            out = chain(out, (element,))
        return out
    return iterable


class SpiderMiddlewareManager(MiddlewareManager):

    component_name = 'spider middleware'

    output_chain = []  # list of dicts (process_spider_output, process_spider_exception)

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return build_component_list(settings.getwithbase('SPIDER_MIDDLEWARES'))

    def _add_middleware(self, mw):
        super(SpiderMiddlewareManager, self)._add_middleware(mw)
        if hasattr(mw, 'process_spider_input'):
            self.methods['process_spider_input'].append(mw.process_spider_input)
        if hasattr(mw, 'process_start_requests'):
            self.methods['process_start_requests'].insert(0, mw.process_start_requests)
        self.output_chain.insert(0, dict(
            process_spider_output=getattr(mw, 'process_spider_output', None),
            process_spider_exception=getattr(mw, 'process_spider_exception', None),
        ))

    def scrape_response(self, scrape_func, response, request, spider):
        fname = lambda f:'%s.%s' % (
                six.get_method_self(f).__class__.__name__,
                six.get_method_function(f).__name__)

        def process_spider_input(response):
            for method in self.methods['process_spider_input']:
                try:
                    result = method(response=response, spider=spider)
                    if result is not None:
                        raise _InvalidOutput('Middleware {} must return None or raise ' \
                            'an exception, got {}'.format(fname(method), type(result)))
                except:
                    return scrape_func(Failure(), request, spider)
            return scrape_func(response, request, spider)

        def process_spider_output(result, method):
            result = method(response=response, result=result, spider=spider)
            if _isiterable(result):
                return _evaluate_iterable(result)
            else:
                raise _InvalidOutput('Middleware {} must return an iterable, got {}' \
                                     .format(fname(method), type(result)))

        def process_spider_exception(failure, method):
            exception = failure.value
            # don't handle _InvalidOutput exception
            if isinstance(exception, _InvalidOutput):
                return failure
            result = method(response=response, exception=exception, spider=spider)
            if result is not None and not _isiterable(result):
                raise _InvalidOutput('Middleware {} must return None or an iterable, got {}' \
                                     .format(fname(method), type(result)))
            return failure if result is None else result

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.pause()
        for mw in self.output_chain:
            if all(mw.values()):
                dfd.addCallbacks(
                    callback=process_spider_output,
                    callbackArgs=(mw['process_spider_output'],),
                    errback=process_spider_exception,
                    errbackArgs=(mw['process_spider_exception'],),
                )
            elif mw['process_spider_output']:
                dfd.addCallback(process_spider_output, method=mw['process_spider_output'])
            elif mw['process_spider_exception']:
                dfd.addErrback(process_spider_exception, method=mw['process_spider_exception'])
        dfd.unpause()
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)
