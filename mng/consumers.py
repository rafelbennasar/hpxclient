import logging
import asyncio


from decimal import Decimal
from hpxclient import protocols
from hpxclient import consts as hpxclient_consts
from hpxclient import settings as hpxclient_settings
from hpxclient.mng import service as manager_service

logger = logging.getLogger(__name__)


class AuthResponseConsumer(protocols.AuthResponseConsumer):

    def process(self):
        error = self.data[b'error']
        if not error:
            self.protocol.session_id = self.data[b'session_id']
            self.protocol.user_id = self.data[b'user_id']
            self.protocol.public_key = self.data[b'public_key']
            self.protocol.is_authenticated = True

            logger.info("Connection authorized. Starting all services "
                        "with session %s.", self.protocol.session_id)
            asyncio.ensure_future(self.protocol.start_services(
                session_id=self.protocol.session_id.decode()))

        else:
            logger.error("Unexpected error: %s", error.decode())
            self.protocol.error = error.decode()


class RPCAuthRequestConsumer(protocols.RPCAuthRequestConsumer):

    def process(self):
        username = self.data[b'username'].decode()
        password = self.data[b'password'].decode()
        auth_result = username == hpxclient_settings.RPC_USERNAME \
                      and password == hpxclient_settings.RPC_PASSWORD
        self.protocol.write_data(
            protocols.RPCAuthResponseProducer(result=auth_result)
        )


class RPCDataRequestConsumer(protocols.RPCDataRequestConsumer):

    def process(self):
        command = self.data[b'command']
        _manager = manager_service.MANAGER

        if command == b"balance":
            response = str(Decimal(_manager.balance_amount)
                           .quantize(Decimal('1.0000000')))

        elif command == b"usage":
            balance = str(Decimal(_manager.balance_amount)
                          .quantize(Decimal('1.0000000')))
            diff_balance = str(Decimal(_manager.initial_balance_amount - _manager.balance_amount)
                               .quantize(Decimal('1.0000000')))
            response = {
                "diff_balance_session": diff_balance,
                "balance": balance,
                "bytes_consumer": _manager.consumer_amount_bytes,
                "bytes_miner": _manager.miner_amount_bytes,
                "gb_consumer": _manager.consumer_amount_bytes/1024/1024/1024,
                "gb_miner": _manager.miner_amount_bytes/1024/1024/1024,
                #"bytes_consumer_confirmed": _manager.consumer_amount_bytes_confirmed,
                #"bytes_miner_confirmed": _manager.miner_amount_bytes_confirmed
                }
        else:
            response = "unknown"

        self.protocol.write_data(
            protocols.RPCDataResponseProducer(command=command, response=response))


class InfoBalanceConsumer(protocols.InfoBalanceConsumer):

    def process(self):
        _decimals_factor = 10 ** hpxclient_consts.HPX_NUMBER_OF_DECIMALS
        self.protocol.balance_amount = Decimal(int(self.data[b'balance_amount'])
                                               / _decimals_factor)
        if not self.protocol.initial_balance_amount:
            self.protocol.initial_balance_amount = self.protocol.balance_amount
        self.protocol.miner_amount_bytes_confirmed += self.data[b"bytes_miner"]
        self.protocol.consumer_amount_bytes_confirmed += self.data[b"bytes_consumer"]


class InfoVersionConsumer(protocols.InfoVersionConsumer):

    def process(self):
        self.protocol.version = self.data[b'version']


class TransferDataConsumer(protocols.TransferDataConsumer):
    def process(self):
        pass


class CloseConnConsumer(protocols.CloseConnConsumer):
    def process(self):
        logger.info('Session %s was closed from server',
                    self.data[b'session_id'])
        self.protocol.transport.close()
