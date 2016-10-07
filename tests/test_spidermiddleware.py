
import logging

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy.spiders import Spider
from scrapy.item import Item, Field
from scrapy.utils.test import get_crawler


# ==================================================
# only catch (and log) an exception
class BaseCatchExceptionSpider(Spider):
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {'tests.test_spidermiddleware.CatchExceptionMiddleware': 540}
    }

class ReturnErrorSpider(BaseCatchExceptionSpider):
    name = 'return_error_spider'
    def parse(self, response):
        raise ZeroDivisionError

class ErrorBeforeYieldSpider(BaseCatchExceptionSpider):
    name = 'error_before_yield_spider'
    def parse(self, response):
        """ should not scrape any items """
        raise ValueError
        for i in range(3):
            yield {'value': i}

class ErrorAfterYieldSpider(BaseCatchExceptionSpider):
    name = 'error_after_yield_spider'
    def parse(self, response):
        """ should scrape 3 items """
        for i in range(3):
            yield {'value': i}
        raise AttributeError


class CatchExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        """ catch an exception and log it """
        logging.warn('{} exception caught'.format(exception.__class__.__name__))
        return None


# ==================================================
# catch an exception and do something about it
class BaseHandleExceptionSpider(Spider):
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {'tests.test_spidermiddleware.HandleExceptionMiddleware': 540}
    }

class ReturnIterableSpider(BaseHandleExceptionSpider):
    name = 'return_iterable_spider'
    def parse(self, response):
        """ should scrape 3 items """
        yield {'value': 10}
        raise UnicodeError


class HandleExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        """ handle an exception, return something useful """
        class TestItem(Item):
            name = Field()
        logging.warn('{} exception handled'.format(exception.__class__.__name__))
        return [
            TestItem(name='value'),
            {'foo': 'bar'},
        ]


# ==================================================
# catch an exception from a previous middleware's process_spider_input
class HandleExceptionFromMiddlewareOnInputSpider(Spider):
    name = 'handle_error_middleware_on_input_spider'
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            'tests.test_spidermiddleware.RaiseExceptionOnInputMiddleware': 530,
            'tests.test_spidermiddleware.HandleExceptionMiddleware': 540,
        }
    }
    def parse(self, response):
        None


class RaiseExceptionOnInputMiddleware(object):
    def process_spider_input(self, response, spider):
        raise KeyError


# ==================================================
# catch an exception from a previous middleware's process_spider_output
class HandleExceptionFromMiddlewareOnOutputSpider(Spider):
    name = 'handle_error_middleware_on_input_spider'
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            'tests.test_spidermiddleware.RaiseExceptionOnOutputMiddleware': 530,
            'tests.test_spidermiddleware.HandleExceptionMiddleware': 540,
        }
    }
    def parse(self, response):
        None


class RaiseExceptionOnOutputMiddleware(object):
    def process_spider_output(self, response, result, spider):
        yield {'value': 123}
        raise IndentationError


# ==================================================
# do not handle exceptions when returning invalid values
class ReturnInvalidValueInputSpider(Spider):
    name = 'return_invalid_value_input_spider'
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            'tests.test_spidermiddleware.ReturnInvalidValueInputMiddleware': 530,
        }
    }
    def parse(self, response):
        return None


class ReturnInvalidValueInputMiddleware(object):
    def process_spider_input(self, response, spider):
        return 1234  # not an iterable


class ReturnInvalidValueOutputSpider(Spider):
    name = 'return_invalid_value_output_spider'
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            'tests.test_spidermiddleware.ReturnInvalidValueOutputMiddleware': 530,
        }
    }
    def parse(self, response):
        return None


class ReturnInvalidValueOutputMiddleware(object):
    def process_spider_output(self, response, result, spider):
        return 1.2  # not an iterable


class TestSpiderMiddleware(TestCase):

    @defer.inlineCallbacks
    def test_process_spider_exception_return_error(self):
        crawler = get_crawler(ReturnErrorSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ZeroDivisionError exception caught", str(log))
        self.assertIn("spider_exceptions/ZeroDivisionError", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_error_before_yield(self):
        crawler = get_crawler(ErrorBeforeYieldSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ValueError exception caught", str(log))
        self.assertIn("spider_exceptions/ValueError", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_error_after_yield(self):
        crawler = get_crawler(ErrorAfterYieldSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("AttributeError exception caught", str(log))
        self.assertIn("spider_exceptions/AttributeError", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_return_iterable(self):
        crawler = get_crawler(ReturnIterableSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("UnicodeError exception handled", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_on_middleware_input(self):
        crawler = get_crawler(HandleExceptionFromMiddlewareOnInputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 2", str(log))
        self.assertIn("KeyError exception handled", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_on_middleware_output(self):
        crawler = get_crawler(HandleExceptionFromMiddlewareOnOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("IndentationError exception handled", str(log))

    @defer.inlineCallbacks
    def test_invalid_value_on_middleware_input(self):
        crawler = get_crawler(ReturnInvalidValueInputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'spider_exceptions/AssertionError': 1", str(log))

    @defer.inlineCallbacks
    def test_invalid_value_on_middleware_output(self):
        crawler = get_crawler(ReturnInvalidValueOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'spider_exceptions/AssertionError': 1", str(log))
