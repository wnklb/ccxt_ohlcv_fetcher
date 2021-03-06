import asyncio
import datetime
import functools
from collections import OrderedDict

from handlers import BaseHandler
from sql.insert import UPSERT_CCXT_OHLCV_STATUS
from sql.select import (SELECT_CCXT_OHLCV_EXCHANGE_TABLES, SELECT_LATEST_CCXT_OHLCV_ENTRY,
                        SELECT_OHLCV_STATUS, SELECT_OHLCV_FETCHER_STATE)


class MethenaExchangesHandler(BaseHandler):
    async def get(self):
        records = self.application.pg.fetch_many(SELECT_CCXT_OHLCV_EXCHANGE_TABLES)
        result = [record[0] for record in records]
        self.write_json(result)


class MethenaOHLCVStatusHandler(BaseHandler):
    async def get(self):
        style = self.get_query_argument('style', default='flat')
        results = self.application.pg.fetch_many(SELECT_OHLCV_STATUS)

        now = datetime.datetime.now(datetime.timezone.utc)
        now_minus_1d = now - datetime.timedelta(days=1)
        now_minus_1h = now - datetime.timedelta(hours=1)
        now_minus_1m = now - datetime.timedelta(minutes=1)

        data = [] if style == 'flat' else OrderedDict()
        for result in results:
            exchange, symbol, timeframe, latest_timestamp, average_duration, \
            estimated_remaining_time, remaining_fetches = result

            status = None
            if timeframe == "1d":
                status = latest_timestamp > now_minus_1d
            elif timeframe == "1h":
                status = latest_timestamp > now_minus_1h
            elif timeframe == "1m":
                status = latest_timestamp > now_minus_1m

            if style == 'flat':
                data.append({
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': latest_timestamp,
                    'isLatest': status,
                    'averageDuration': average_duration,
                    'remainingFetches': remaining_fetches,
                    'estimatedRemainingTime': estimated_remaining_time,
                })
            elif style == 'nested':
                if exchange not in data:
                    data[exchange] = {}
                if symbol not in data[exchange]:
                    data[exchange][symbol] = {}
                data[exchange][symbol][timeframe] = {
                    "timestamp": latest_timestamp,
                    "isLatest": status,
                    'averageDuration': average_duration,
                    'remainingFetches': remaining_fetches,
                    'estimatedRemainingTime': estimated_remaining_time,
                }

        self.write_json(data)

    async def post(self):
        # TODO: should be removed since this happens on insertion
        """Updates the status of the latest OHLCV fetch."""
        exchange_tables = self.application.pg.fetch_many(SELECT_CCXT_OHLCV_EXCHANGE_TABLES)
        exchanges = [record[0] for record in exchange_tables]

        data = []
        for exchange in exchanges:

            # This query returns the latest reported timestamp for the given descriptor.
            query = SELECT_LATEST_CCXT_OHLCV_ENTRY.format(exchange=exchange)
            latest_ohlcv_entries = self.application.pg.fetch_many(query)

            if not latest_ohlcv_entries:
                continue
            for entry in latest_ohlcv_entries:
                data.append((exchange, entry[0], entry[1], entry[2]))

        self.application.pg.insert_many(UPSERT_CCXT_OHLCV_STATUS, data)
        self.set_status(204)


class MethenaOHLCVFetcherStateHandler(BaseHandler):
    async def get(self):
        data = self.application.pg.fetch_one(SELECT_OHLCV_FETCHER_STATE)
        self.write_json(data)

    async def post(self):
        raw_descriptor = self._get_descriptor()
        # Note: This is the same behavior as is implemented in mqtt_client
        task = asyncio.ensure_future(self.application.ccxt.init_exchange_markets(raw_descriptor[0]))
        task.add_done_callback(functools.partial(self._callback_add_descriptor, raw_descriptor))
        self.set_status(204)

    async def delete(self):
        raw_descriptor = self._get_descriptor()
        # Note: This is the same behavior as is implemented in mqtt_client
        descriptor = self.application.ccxt.build_descriptor(raw_descriptor)
        self.application.state.remove_descriptor(descriptor)
        self.set_status(204)

    def _get_descriptor(self):
        exchanges = self.json_args.get('exchanges', '').split(',')
        symbols = self.json_args.get('symbols', '').split(',')
        timeframes = self.json_args.get('timeframes', '').split(',')
        return exchanges, symbols, timeframes

    def _callback_add_descriptor(self, raw_descriptor, result):
        descriptor = self.application.ccxt.build_descriptor(raw_descriptor)
        self.application.state.add_descriptor(descriptor)
