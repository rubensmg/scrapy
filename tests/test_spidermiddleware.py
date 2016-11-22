
import logging

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy.spiders import Spider
from scrapy.item import Item, Field
from scrapy.utils.test import get_crawler


# ================================================================================
# exceptions from a spider's parse method
class BaseExceptionFromParseMethodSpider(Spider):
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {'tests.test_spidermiddleware.CatchExceptionMiddleware': 540}
    }

class NotAGeneratorSpider(BaseExceptionFromParseMethodSpider):
    """ return value is NOT a generator """
    name = 'not_a_generator'
    def parse(self, response):
        raise ZeroDivisionError

class GeneratorErrorBeforeItemsSpider(BaseExceptionFromParseMethodSpider):
    """ return value is a generator; the exception is raised
    before the items are yielded: no items should be scraped """
    name = 'generator_error_before_items'
    def parse(self, response):
        raise ValueError
        for i in range(3):
            yield {'value': i}

class GeneratorErrorAfterItemsSpider(BaseExceptionFromParseMethodSpider):
    """ return value is a generator; the exception is raised
    after the items are yielded: 3 items should be scraped """
    name = 'generator_error_after_items'
    def parse(self, response):
        for i in range(3):
            yield {'value': i}
        raise FloatingPointError

class CatchExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        """ catch an exception and log it """
        logging.warn('{} exception caught'.format(exception.__class__.__name__))
        return None


# ================================================================================
# exception from a previous middleware's process_spider_output method (not a generator)
class NotAGeneratorFromPreviousMiddlewareOutputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'not_a_generator_from_previous_middleware_output'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.RaiseExceptionOnOutputNotAGeneratorMiddleware': 545,
            # spider side
        }
    }
    def parse(self, response):
        return [{'value': i} for i in range(3)]

class RaiseExceptionOnOutputNotAGeneratorMiddleware(object):
    def process_spider_output(self, response, result, spider):
        raise UnicodeError


# ================================================================================
# exception from a previous middleware's process_spider_output method (generator)
class GeneratorFromPreviousMiddlewareOutputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'generator_from_previous_middleware_output'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.RaiseExceptionOnOutputGeneratorMiddleware': 545,
            # spider side
        }
    }
    def parse(self, response):
        return [{'value': i} for i in range(10, 13)]

class RaiseExceptionOnOutputGeneratorMiddleware(object):
    def process_spider_output(self, response, result, spider):
        for r in result:
            yield r
        raise NameError


class TestSpiderMiddleware(TestCase):

    @defer.inlineCallbacks
    def test_process_spider_exception_from_parse_method(self):
        # non-generator return value
        crawler = get_crawler(NotAGeneratorSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ZeroDivisionError exception caught", str(log))
        self.assertIn("spider_exceptions/ZeroDivisionError", str(log))
        # generator return value, no items before the error
        crawler = get_crawler(GeneratorErrorBeforeItemsSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ValueError exception caught", str(log))
        self.assertIn("spider_exceptions/ValueError", str(log))
        # generator return value, 3 items before the error
        crawler = get_crawler(GeneratorErrorAfterItemsSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("FloatingPointError exception caught", str(log))
        self.assertIn("spider_exceptions/FloatingPointError", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_from_previous_middleware_output(self):
        # non-generator output value
        crawler = get_crawler(NotAGeneratorFromPreviousMiddlewareOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertNotIn("UnicodeError exception caught", str(log))
        # generator output value
        crawler = get_crawler(GeneratorFromPreviousMiddlewareOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("NameError exception caught", str(log))
