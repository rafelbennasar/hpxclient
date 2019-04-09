import logging

from hpxclient import protocols

logger = logging.getLogger(__name__)

# It's indexed by CONN_ID (not by sessions).
BROWSER_TASKS = {}


class RegisterConnConsumer(protocols.RegisterConnConsumer):

    def process(self):
        pass


class InitConnConsumer(protocols.InitConnConsumer):

    def process(self):
        pass


class TransferDataConsumer(protocols.TransferDataConsumer):

    def process(self):
        conn_id, data = self.data[b'conn_id'], self.data[b'data']
        if conn_id in BROWSER_TASKS:
            BROWSER_TASKS[conn_id].write_to_browser(data)


class CloseConnConsumer(protocols.CloseConnConsumer):

    def process(self):
        pass
