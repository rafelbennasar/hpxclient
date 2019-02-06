import asyncio
import sys

from hpxclient import logger
from hpxclient import protocols
from hpxclient import utils as hpxclient_utils
from hpxclient.fetcher import service as fetcher_service
from hpxclient.listener import service as listener_service
from hpxclient.bridge import service as bridge_service
from hpxclient import settings as hpxclient_settings
from hpxclient.mng import consts as mng_consts

from hpxclient.mng import producers as mng_producers
from hpxclient.mng import consumers as mng_consumers


MANAGER = None
ssl_context = None


class RPCManagerServer(protocols.MsgpackProtocol):

    REGISTERED_CONSUMERS = [
        mng_consumers.RPCAuthRequestConsumer,
        mng_consumers.RPCDataRequestConsumer,
    ]

    def __init__(self):
        global RPC_MANAGER
        RPC_MANAGER = self
        super().__init__()
        self.transport = None
        self.is_authorized = False

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        logger.info("hpxclient.mng.service Connection lost.")

    def message_received(self, message):
        logger.info("MESSAGE RECEIVED in the RCP: %s", message)
        protocols.process_message(self, message, self.REGISTERED_CONSUMERS)

    def write_data(self, msg_producer):
        self.transport.write(protocols.create_msgpack_message(msg_producer.msg2str()))


class ManagerProtocol(protocols.MsgpackProtocol):

    REGISTERED_CONSUMERS = [
        mng_consumers.AuthResponseConsumer,
        mng_consumers.CloseConnConsumer,
        mng_consumers.TransferDataConsumer,
        mng_consumers.InfoBalanceConsumer,
        mng_consumers.InfoVersionConsumer
    ]

    def __init__(self, email=None, password=None, message_handler=None,
                 public_key=None, secret_key=None,
                 ssl_context=None):
        global MANAGER
        MANAGER = self
        super().__init__()

        self.transport = None
        self.is_authorized = False
        self.session_id = None
        self.user_id = None

        self.message_handler = message_handler

        self.email = email
        self.password = password
        self.public_key = public_key
        self.secret_key = secret_key
        self.ssl_context = ssl_context

        self.initial_balance_amount = None
        # confirmed are bytes that we have sent and the server
        # received from us. It DOES NOT mean that it's been
        # confirmed that the 'other' miner/ consumer also had sent
        # the same amount.
        self.miner_amount_bytes = 0
        self.miner_amount_bytes_confirmed = 0
        self.consumer_amount_bytes = 0
        self.consumer_amount_bytes_confirmed = 0

    async def start_services(self):
        ps_keys = {"session_id": self.session_id,
                   "user_id": self.user_id,
                   "public_key": self.public_key,
                   'ssl_context': self.ssl_context}

        await asyncio.wait([
            listener_service.configure_service(**ps_keys),
        ])
        await asyncio.wait([
            fetcher_service.configure_service(**ps_keys),
            # bridge_service.configure_server(**ps_keys),
        ])

    def connection_made(self, transport):
        self.transport = transport
        self.send_auth_request()

    def send_transfer_miner_ack(self, conn_id, amount_data):
        self.miner_amount_bytes += amount_data
        self.write_data(
            protocols.TransferAckProducer(conn_id,
                                          amount_data,
                                          mng_consts.MINER_TRANSFER_ACK_KIND)
        )

    def send_transfer_consumer_ack(self, conn_id, amount_data):
        self.consumer_amount_bytes += amount_data
        self.write_data(
            protocols.TransferAckProducer(conn_id,
                                          amount_data,
                                          mng_consts.CONSUMER_TRANSFER_ACK_KIND)
            )

    def send_transfer_miner_close(self, conn_id, amount_data):
        self.miner_amount_bytes += amount_data
        self.write_data(
            protocols.TransferAckProducer(conn_id,
                                          amount_data,
                                          mng_consts.MINER_END_TRANSFER_KIND)
        )

    def send_transfer_consumer_close(self, conn_id, amount_data):
        self.consumer_amount_bytes += amount_data
        self.write_data(
            protocols.TransferAckProducer(conn_id,
                                          amount_data,
                                          mng_consts.CONSUMER_END_TRANSFER_KIND)
        )

    def send_auth_request(self):
        self.write_data(
            mng_producers.AuthRequestProducer(email=self.email,
                                              password=self.password,
                                              public_key=self.public_key,
                                              secret_key=self.secret_key))

    def connection_lost(self, exc):
        logger.info("hpxclient.mng.service Connection lost.")

    def message_received(self, message):
        if self.message_handler:
            self.message_handler(message)
        protocols.process_message(self, message, self.REGISTERED_CONSUMERS)

    def write_data(self, msg_producer):
        if self.transport and not self.transport.is_closing():
            self.transport.write(protocols.create_msgpack_message(msg_producer.msg2str()))

    @property
    def is_manager_active(self):
        return MANAGER.transport is not None

    @property
    def is_listener_active(self):
        return listener_service.FETCHER.transport is not None

    @property
    def is_bridge_active(self):
        return bridge_service.BRIDGE.transport is not None


async def start_client(email=None, password=None, public_key=None,
                       secret_key=None, message_handler=None,
                       retry_initial_connection=False):
    """ Starts client services:
    """
    global ssl_context
    ssl_context = hpxclient_utils.create_ssl_context_user()

    logger.info("Connecting to manager server: %s:%s",
                hpxclient_settings.PROXY_MNG_SERVER_IP,
                hpxclient_settings.PROXY_MNG_SERVER_PORT)
    manager_ = ManagerProtocol(email=email,
                               password=password,
                               public_key=public_key,
                               secret_key=secret_key,
                               ssl_context=ssl_context,
                               message_handler=message_handler)

    await protocols.ReconnectingProtocolWrapper.create_connection(
        lambda: manager_,
        host=hpxclient_settings.PROXY_MNG_SERVER_IP,
        port=hpxclient_settings.PROXY_MNG_SERVER_PORT,
        ssl=ssl_context,
        retry_initial_connection=retry_initial_connection)

    if hpxclient_settings.RPC_USERNAME and hpxclient_settings.RPC_PASSWORD:
        loop = asyncio.get_event_loop()
        await asyncio.wait([
            loop.create_server(RPCManagerServer,
                               host="0.0.0.0",
                               port=hpxclient_settings.RPC_LOCAL_PORT)
        ])
        logger.info("RPC server started.")
    else:
        logger.warning("RPC server not started as the user/pwd is "
                       "not defined. Please, define it in the hprox.cfg")


def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_client(email='denroz@inbox.ru',
                                         password='Qwerty12'))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        sys.stderr.flush()
        print('\nStopped\n')
    finally:
        loop.close()
