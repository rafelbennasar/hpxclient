import sys
import random
import asyncio

from hpxclient import logger
from hpxclient import protocols
from hpxclient import consts as hpxclient_consts
from hpxclient.bridge import service as bridge_service
from hpxclient.listener import consumers as listener_consumers
from hpxclient.mng import service as manager_service
from hpxclient import utils as hpxclient_utils
from hpxclient.mng import consts as mng_consts
from hpxclient import settings as hpxclient_settings


FETCHER = None

BROWSER_LISTENER = None


class FetcherProtocol(protocols.MsgpackProtocol):

    REGISTERED_FETCHER_CONSUMERS = [
        listener_consumers.RegisterConnConsumer,
        listener_consumers.InitConnConsumer,
        listener_consumers.TransferDataConsumer,
        listener_consumers.CloseConnConsumer
    ]

    def __init__(self, session_id, user_id, public_key):
        super(FetcherProtocol, self).__init__()
        self.transport = None
        self.session_id = session_id
        self.user_id = user_id
        self.public_key = public_key
        self.is_authorized = True
        self.is_authenticated = True
        self.amount_data_downloaded = 0
        self._buffered_data = []
        self.utime_last_ack = None

    def connection_made(self, transport):
        logger.debug("Connection made to fetcher service")
        global FETCHER
        FETCHER = self
        self.transport = transport
        self.register_conn()

        for data in self._buffered_data:
            self.transport.write(data)
        self._buffered_data = []
        self.utime_last_ack = hpxclient_utils.get_utime_ms()

    def connection_lost(self, exc):
        logger.debug("Connection lost to fetcher: %s", exc)
        global FETCHER
        FETCHER = None

    def message_received(self, message):
        protocols.process_message(self, message,
                                  self.REGISTERED_FETCHER_CONSUMERS)

    def init_conn(self, conn_id, url):
        self.write_data(protocols.InitConnFetchUrlProducer(conn_id, url))

    def register_conn(self):
        self.write_data(
            protocols.RegisterConnPIDProducer(user_id=self.user_id,
                                              session_id=self.session_id,
                                              public_key=self.public_key))

    def init_session(self, session_id):
        self.session_id = session_id
        self.write_data(protocols.InitSessionProducer(self.session_id))

    def close_conn(self, conn_id):
        self.write_data(protocols.CloseConnProducer(conn_id=conn_id))

    def trans_conn(self, conn_id, data):
        now = hpxclient_utils.get_utime_ms()
        self.amount_data_downloaded += len(data)

        diff = now - self.utime_last_ack
        if 0 < self.amount_data_downloaded and \
            (diff > mng_consts.TRANSFER_DATA_ACK_MAX_PERIOD
                 or mng_consts.TRANSFER_DATA_ACK_BLOCK_SIZE < self.amount_data_downloaded):
            logger.info("[CONSUMER] Sending Transfer-ACK: "
                        "%s bytes for conn id %s", self.amount_data_downloaded, conn_id)
            manager_service.MANAGER.send_transfer_consumer_ack(conn_id,
                                                               self.amount_data_downloaded)
            self.amount_data_downloaded = 0
            self.utime_last_ack = now

        self.write_data(protocols.TransferDataProducer(conn_id=conn_id,
                                                       session_id=self.session_id,
                                                       data=data))

    def write_data(self, msg_producer):
        if self.transport.is_closing():
            return

        if self.transport is None:
            self._buffered_data.append(
                protocols.create_msgpack_message(msg_producer.msg2str()))
        else:
            self.transport.write(
                protocols.create_msgpack_message(msg_producer.msg2str()))


class BrowserListenerServer(asyncio.Protocol):

    def __init__(self):
        self.conn_id = hpxclient_utils.rndstrs(32).encode()
        self.amount_data_downloaded = 0
        self.transport = None
        self.processor = None
        self.url = None

        self.conn_initialized = False

    def get_processor(self):
        """ Return object that will 'process' the request:
            - Fetcher: The URL-task-request would be sent to our server-fetcher
            and it would be relayed to another client that was also connected
            to the fetcher.
            - P2P client: The URL-task-request would be sent to another
            client directly through the P2PBridge connection.
            Before starting
            """
        return FETCHER
        try:
            p2p_public_key = random.choice(list(bridge_service.P2P_CLIENTS.keys()))
            logger.info("Selected P2P processor: %s.", p2p_public_key)
            return bridge_service.P2P_CLIENTS[p2p_public_key]
        except IndexError:
            logger.info("Selected FETCHER processor.")
            return FETCHER

    def connection_made(self, transport):
        self.transport = transport
        self.processor = self.get_processor()
        logger.info("""Connection %s made to client.LocalListener Processor: %s""", self.conn_id, self.processor)

        if self.processor is None:
            self.transport.close()
            return

        listener_consumers.BROWSER_TASKS[self.conn_id] = self

    def create_http_message(self, text, status_code):
        msg = """HTTP/1.1 %s 
                Content-Type: text/html
                Connection: Closed

                <html>
                <head><meta charset="UTF-8"></head>
                <body>
                %s
                </body>
                </html>
                \r\n\r\n
                    """ % (status_code, text)
        return msg

    def data_received(self, data):
        # Connection is initialized once we already know the url
        # as we need to know it to filter what RecvNetwork is
        # able to accept the request.
        if not self.url:
            self.url = hpxclient_utils.get_host_from_headers(data)

        # full_url = hpxclient_utils.get_url_from_headers(data)
        # if data.startswith(b'GET') and not hpxclient_utils.is_captive_platform(full_url):
        #     msg = self.create_http_message("""
        #         <h1>Http protocol not supported, try using https.</h1>
        #         <script>
        #             window.location.href = window.location.href.replace("http:","https:")
        #         </script>""", 200)
        #     self.transport.write(msg.encode())
        #     self.transport.close()
        #     self.processor.close_conn(self.conn_id)
        #     return

        if not self.conn_initialized:
            self.processor.init_conn(self.conn_id, self.url)
            self.conn_initialized = True

        if FETCHER is None:
            logger.info("Listener transport closed as fetcher is none.")
            self.transport.close()
            return

        if self.conn_id not in listener_consumers.BROWSER_TASKS:
            logger.warning("BrowserListener closed %s!", self.conn_id)
            self.transport.close()
            return

        self.processor.trans_conn(self.conn_id, data)

    def connection_lost(self, exc):
        logger.info("[Consumer] Sending Close-Transfer-ACK: %s bytes for conn id %s",
                    self.amount_data_downloaded, self.conn_id)
        manager_service.MANAGER.send_transfer_consumer_close(self.conn_id,
                                                             self.amount_data_downloaded)
        self.amount_data_downloaded = 0

        if FETCHER is not None:
            FETCHER.close_conn(self.conn_id)

        if self.conn_id in listener_consumers.BROWSER_TASKS:
            logger.warning("[LocalListener] Deleting CONN ID %s from TASKS", self.conn_id)
            del listener_consumers.BROWSER_TASKS[self.conn_id]

    def write_to_browser(self, data):
        if self.transport.is_closing():
            return

        self.transport.write(data)
        self.amount_data_downloaded += len(data)

        if mng_consts.TRANSFER_DATA_ACK_BLOCK_SIZE < self.amount_data_downloaded:
            amount_left = self.amount_data_downloaded % mng_consts.TRANSFER_DATA_ACK_BLOCK_SIZE
            amount_ack = self.amount_data_downloaded - amount_left
            logger.info("[CONSUMER] Sending Transfer-ACK: %s bytes for conn id %s", amount_ack, self.conn_id)
            manager_service.MANAGER.send_transfer_consumer_ack(self.conn_id, amount_ack)
            self.amount_data_downloaded = amount_left


async def configure_service(user_id, session_id, public_key, ssl_context):
    loop = asyncio.get_event_loop()
    fetcher_ = FetcherProtocol(user_id=user_id, session_id=session_id, public_key=public_key)
    logger.info("Proxy listening at %s", hpxclient_settings.PROXY_LISTENER_LOCAL_PORT)

    global BROWSER_LISTENER
    if not BROWSER_LISTENER:
        BROWSER_LISTENER = await asyncio.wait([
            loop.create_server(
                BrowserListenerServer, '127.0.0.1', hpxclient_settings.PROXY_LISTENER_LOCAL_PORT,
            ), ])

    await asyncio.wait([
        protocols.ReconnectingProtocolWrapper.create_connection(
            lambda: fetcher_,
            host=hpxclient_settings.PROXY_LISTENER_SERVER_IP,
            port=hpxclient_settings.PROXY_LISTENER_SERVER_PORT,
            ssl=ssl_context
        ),
    ])


def main():
    loop = asyncio.get_event_loop()
    pid, conn_id, ssl = None, None, None
    loop.run_until_complete(configure_service(pid, conn_id, ssl))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        sys.stderr.flush()
        print('\nStopped\n')
    finally:
        loop.close()


if __name__ == '__main__':
    main()
