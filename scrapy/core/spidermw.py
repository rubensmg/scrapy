"""
Spider Middleware manager

See documentation in docs/topics/spider-middleware.rst
"""
from functools import wraps

import six
from twisted.python.failure import Failure
from scrapy.exceptions import _InvalidOutput
from scrapy.middleware import MiddlewareManager
from scrapy.utils.defer import mustbe_deferred
from scrapy.utils.conf import build_component_list


def _isiterable(possible_iterator):
    return hasattr(possible_iterator, '__iter__')


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

        def _wrapper_process_spider_output(method):
            @wraps(method)
            def callback(result):
                result = method(response=response, result=result, spider=spider)
                if _isiterable(result):
                    for elem in result:
                        yield elem
                else:
                    raise _InvalidOutput('Middleware {} must return an iterable, got {}' \
                                         .format(fname(method), type(result)))
            return callback

        def _wrapper_process_spider_exception(method):
            @wraps(method)
            def errback(failure):
                exception = failure.value
                # don't handle _InvalidOutput exception
                if isinstance(exception, _InvalidOutput):
                    return failure
                result = method(response=response, exception=exception, spider=spider)
                if result is not None and not _isiterable(result):
                    raise _InvalidOutput('Middleware {} must return None or an iterable, got {}' \
                                         .format(fname(method), type(result)))
                return failure if result is None else result
            return errback

        dfd = mustbe_deferred(process_spider_input, response)
        dfd.pause()
        for mw in self.output_chain:
            if all(mw.values()):
                dfd.addCallbacks(
                    callback=_wrapper_process_spider_output(mw['process_spider_output']),
                    errback=_wrapper_process_spider_exception(mw['process_spider_exception']))
            elif mw['process_spider_output']:
                dfd.addCallback(_wrapper_process_spider_output(mw['process_spider_output']))
            elif mw['process_spider_exception']:
                dfd.addErrback(_wrapper_process_spider_exception(mw['process_spider_exception']))
        dfd.unpause()
        # XXX - debug
        print('='*100)
        for _m in dfd.callbacks:
            print(_m)
        print('='*100)
        # import pdb
        # pdb.set_trace()
        # XXX - debug
        return dfd

    def process_start_requests(self, start_requests, spider):
        return self._process_chain('process_start_requests', start_requests, spider)
