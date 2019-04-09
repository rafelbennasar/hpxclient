import asyncio
import logging

from hpxclient.fetcher import upstrm as fetcher_upstream
from hpxclient import protocols
from hpxclient import settings as hpxclient_settings

logger = logging.getLogger(__name__)


TASKS = {}


class InitConnConsumer(protocols.InitConnConsumer):


    def process(self):
        conn_id = self.data[b'conn_id']
        TASKS[conn_id] = fetcher_upstream.TransTransporter(
            conn_id,
            self.protocol.session_id,
            self.protocol)
        loop = asyncio.get_event_loop()
        dhost, dport = "127.0.0.1", hpxclient_settings.PROXY_FETCHER_LOCAL_PORT

        asyncio.ensure_future(
            loop.create_connection(lambda: TASKS[conn_id], dhost, dport))


class InitSessionConsumer(protocols.InitSessionConsumer):

    def process(self):
        self.protocol.session_id = self.data[b"session_id"]


class TransferDataConsumer(protocols.TransferDataConsumer):

    def process(self):
        conn_id, data = self.data[b'conn_id'], self.data[b'data']
        if conn_id in TASKS:
            TASKS[conn_id].write_data(data)


class CloseConnConsumer(protocols.CloseConnConsumer):

    def process(self):
        conn_id = self.data[b'conn_id']

        if conn_id in TASKS:
            protocol = TASKS[conn_id]
            msg = protocols.CloseConnProducer(conn_id=conn_id)
            if protocol.transport and not protocol.transport.is_closing():
                protocol.transport.write(protocols.create_msgpack_message(msg.msg2str()))
                protocol.transport.close()
            del TASKS[conn_id]
