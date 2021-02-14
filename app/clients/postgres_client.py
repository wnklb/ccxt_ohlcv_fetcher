import logging

import psycopg2
import psycopg2.extras
from config import PSQL_DSN, SCHEMA_CCXT_OHLCV, SCHEMA_METHENA
from sql.ddl import create_table_ccxt_ohlcv_status, create_schema_ccxt_ohlcv, create_schema_methena
from utils.postgres import convert_datetime_to_timestamp
from utils.singleton import Singleton

log = logging.getLogger('methena')


class PostgresClient(Singleton):
    conn = None
    cur = None
    setup_done = False
    log.debug('Created PostgresClient')

    def __init__(self):
        if self.conn is None:
            self.__start()
        if not self.setup_done:
            self.__setup()
        log.debug('Initialized PostgresClient')

    def stop(self):
        self.conn.close()
        log.info('PostgresClient closed connection to {}'.format(PSQL_DSN.split('@')[1]))

    def __start(self):
        self.conn = psycopg2.connect(dsn=PSQL_DSN)
        self.cur = self.conn.cursor()
        log.info('PostgresClient connected to {}'.format(PSQL_DSN.split('@')[1]))
        return self

    def __setup(self):
        self.execute(create_schema_ccxt_ohlcv)
        self.execute(create_schema_methena)
        self.create_table_ccxt_ohlcv_fetcher_config_if_not_exists()
        self.create_table_ccxt_ohlcv_status()
        self.setup_done = True
        log.info('PostgresClient setup done - initial schemas and tables created.')

    def __execute(self, query, values=None):
        self.cur.execute(query, values)

    def __commit(self):
        self.conn.commit()

    def __execute_and_commit(self, query, values=None):
        self.__execute(query, values)
        self.__commit()

    def insert(self, query, values):
        self.__execute_and_commit(query, values)

    def insert_many(self, query, values, page_size=1000):
        psycopg2.extras.execute_values(self.cur, query, values, page_size=page_size)
        self.__commit()

    def execute(self, query, values=None):
        self.__execute_and_commit(query, values)

    def fetch_one(self, query):
        self.__execute(query)
        return self.cur.fetchone()

    def fetch_many(self, query):
        self.__execute(query)
        return self.cur.fetchall()

    # ===================== [ Custom Calls ] =====================

    def create_table_ccxt_ohlcv_fetcher_config_if_not_exists(self):
        # TODO: get state and log dependingly
        query = """
        create table if not exists ccxt_ohlcv_fetcher_state
        (
            config jsonb not null,
            timestamp timestamp with time zone default CURRENT_TIMESTAMP not null,
            id integer not null
                constraint ccxt_ohlcv_fetcher_state_pk
                    primary key
        );

        alter table ccxt_ohlcv_fetcher_state owner to methena;
        """
        self.__execute_and_commit(query)

    def create_table_ccxt_ohlcv_status(self):
        self.__execute_and_commit(create_table_ccxt_ohlcv_status)

    def create_exchange_ohlcv_table_if_not_exists(self, table):
        query = """
        CREATE TABLE IF NOT EXISTS {schema}.{table} (
            symbol varchar(16),
            timeframe varchar(2),
            timestamp timestamp,
            open float,
            high float,
            low float,
            close float,
            volume float
        );""".format(schema=SCHEMA_CCXT_OHLCV, table=table)
        self.__execute_and_commit(query)

    def insert_ohlcv_entries(self, values, table, schema=SCHEMA_CCXT_OHLCV, page_size=1000):
        query = "INSERT INTO {schema}.{table} VALUES %s;".format(schema=schema, table=table)
        psycopg2.extras.execute_values(self.cur, query, values, page_size=page_size)
        self.__commit()

    def fetch_latest_timestamp(self, exchange, symbol, timeframe):
        query = """
        SELECT timestamp from {schema}.{exchange}
        WHERE symbol='{symbol}'
        AND timeframe='{timeframe}'
        ORDER BY timestamp DESC
        LIMIT 1;
        """.format(
            schema=SCHEMA_CCXT_OHLCV,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe
        )
        datetime_ = self.fetch_one(query)
        if datetime_ is None:
            return
        timestamp = convert_datetime_to_timestamp(datetime_[0])
        return timestamp

    def set_ccxt_ohlcv_fetcher_config(self, state):
        query = """
        insert into methena.ccxt_ohlcv_fetcher_state (id, config, timestamp)
        values (1, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (id)
        DO UPDATE
        SET
            config = EXCLUDED.config,
            timestamp = EXCLUDED.timestamp
        ;
        """
        self.insert(query, (state,))
