import asyncio
import sys
import logging

from hpxclient import settings as hpxclient_settings
from hpxclient import consts as hpxclient_consts
from hpxclient import protocols
from hpxclient.mng import consts as mng_consts
from hpxclient.fetcher import consumers as fetcher_consumers
from hpxclient.mng import service as manager_service
from hpxclient import utils as hpxclient_utils

logger = logging.getLogger(__name__)

FETCHER_UPSTREAM = None


class TransTransporter(asyncio.Protocol):
    def __init__(self, conn_id, session_id, peer):
        self.peer = peer
        self.transport = None

        self.total_amount_data_downloaded = 0
        self.amount_data_downloaded = 0

        self.conn_id = conn_id
        self.session_id = session_id
        self.buff = b''

        self.utime_last_ack = None

        self.utime_started_task = None
        self.utime_last_request = 0
        self.utime_last_response = 0

        # Process task time sums the time waiting between a
        # customer's request and the response from the server.
        self.accum_process_task_time = 0

        # total_task_time counts the time since the task started.
        self.total_task_time = 1

        self.avg_kbps = 0

    def connection_made(self, transport):
        self.utime_started_task = hpxclient_utils.get_utime_ms()
        self.utime_last_ack = hpxclient_utils.get_utime_ms()

        self.transport = transport

        if self.buff:
            self.transport.write(self.buff)
            self.buff = b''

    def connection_lost(self, exc):
        now = hpxclient_utils.get_utime_ms()
        self.total_task_time = self.utime_last_response - self.utime_started_task

        p_seconds = self.accum_process_task_time / 1000.
        if p_seconds:
            self.avg_kbps = (self.total_amount_data_downloaded*8/1024) / p_seconds

        logger.info("[MINER] Sending Close-Transfer-ACK: %s bytes (%s Mb) for "
                    "conn id %s (process time: %s ms/ total: %s ms/ %s kbps)",
                    self.amount_data_downloaded,
                    round(self.amount_data_downloaded/1024/1024, 2),
                    self.conn_id,
                    self.accum_process_task_time,
                    self.total_task_time,
                    round(self.avg_kbps, 2))

        manager_service.MANAGER.send_transfer_miner_close(
            self.conn_id.decode(),
            self.amount_data_downloaded)

        self.peer.write_data(
            protocols.CloseConnProducer(conn_id=self.conn_id)
        )

    def data_received(self, data):
        now = hpxclient_utils.get_utime_ms()

        if self.transport is None:
            self.peer.close()

        self.amount_data_downloaded += len(data)
        self.total_amount_data_downloaded += len(data)

        diff = now - self.utime_last_ack

        if 0 < self.amount_data_downloaded and \
            (diff > mng_consts.TRANSFER_DATA_ACK_MAX_PERIOD or
            mng_consts.TRANSFER_DATA_ACK_BLOCK_SIZE < self.amount_data_downloaded):
            logger.info("[MINER] Sending Transfer-ACK: %s bytes for conn id %s",
                        self.amount_data_downloaded, self.conn_id)
            manager_service.MANAGER.send_transfer_miner_ack(
                self.conn_id.decode(), self.amount_data_downloaded)
            self.amount_data_downloaded = 0
            self.utime_last_ack = now

        self.peer.write_data(
            protocols.TransferDataProducer(conn_id=self.conn_id,
                                           session_id=self.session_id,
                                           data=data))
        now = hpxclient_utils.get_utime_ms()
        self.utime_last_response = now
        self.accum_process_task_time += now - self.utime_last_request
        self.utime_last_request = now

    def write_data(self, data):
        self.utime_last_request = hpxclient_utils.get_utime_ms()

        if self.transport is None:
            self.buff += data
        elif self.transport.is_closing():
            logger.warning("Transport not available. Not able to send data "
                           "to conn id %s, %s bytes", self.conn_id, len(data))
        else:
            self.transport.write(data)


class FetcherForwarderProtocol(protocols.MsgpackProtocol):
    """ Client which connect to job queue server and
        process requests from domestic ip.
    """

    REGISTERED_CONSUMERS = [
        fetcher_consumers.InitConnConsumer,
        fetcher_consumers.InitSessionConsumer,
        fetcher_consumers.TransferDataConsumer,
        fetcher_consumers.CloseConnConsumer
    ]

    def __init__(self, user_id, public_key):
        super().__init__()
        global FETCHER_UPSTREAM
        FETCHER_UPSTREAM = self
        self.user_id = user_id
        self.session_id = None
        self.public_key = public_key
        self.conn_id = None
        self.transport = None
        self.is_authorized = True
        self.is_authenticated = True
        self.amount_data_downloaded = 0

    def connection_made(self, transport):
        logger.debug("Connection made to FetcherForwarderProtocol. Conn id %s",
                     self.conn_id)
        self.transport = transport
        self.register_conn()

    def connection_lost(self, exc):
        logger.debug("Connection lost in FetcherForwarderProtocol. Conn id %s",
                     self.conn_id)

    def _update_session_id(self):
        self.session_id = manager_service.MANAGER.get_session_id()
        logger.debug("Session id %s updated in fetcher service",
                     self.session_id)

    def register_conn(self):
        self._update_session_id()
        logger.debug("Registering session id %s for user %s and public key %s",
                     self.session_id, self.user_id, self.public_key)
        self.write_data(
            protocols.RegisterConnPIDProducer(user_id=self.user_id,
                                              session_id=self.session_id,
                                              public_key=self.public_key))

    def message_received(self, message):
        protocols.process_message(self, message, self.REGISTERED_CONSUMERS)

    def write_data(self, msg_producer):
        if self.transport and not self.transport.is_closing():
            self.transport.write(
                protocols.create_msgpack_message(msg_producer.msg2str()))


async def configure_client(pid, public_key, ssl_context=None):
    dhost, dport = hpxclient_settings.PROXY_FETCHER_SERVER_IP, \
                   hpxclient_settings.PROXY_FETCHER_SERVER_PORT
    forwarder_ = FetcherForwarderProtocol(pid, public_key)
    return await protocols.ReconnectingProtocolWrapper.create_connection(
        lambda: forwarder_,
        host=dhost,
        port=dport,
        ssl=ssl_context,
    )


def main():
    loop = asyncio.get_event_loop()
    server = loop.run_until_complete(configure_client())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        sys.stderr.flush()
        print('\nStopped\n')
    finally:
        loop.close()


if __name__ == '__main__':
    main()
