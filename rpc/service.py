import asyncio

from hpxclient import protocols
from hpxclient import settings as hpxclient_settings
from hpxclient.rpc import consumers as rpc_consumers

RPC_MANAGER = None


class RPCManagerProtocol(protocols.MsgpackProtocol):

    REGISTERED_CONSUMERS = [
        rpc_consumers.RPCAuthResponseConsumer,
        rpc_consumers.RPCDataResponseConsumer,
    ]

    def __init__(self, username, password):
        global RPC_MANAGER
        RPC_MANAGER = self
        super().__init__()
        self.username = username
        self.password = password
        self.transport = None
        self.is_authorized = False

    def connection_made(self, transport):
        self.transport = transport
        self.send_auth_request(self.username, self.password)

    def send_auth_request(self, username, password):
        self.write_data(protocols.RPCAuthRequestProducer(username=username,
                                                         password=password))

    def connection_lost(self, exc):
        pass

    def send_rpc_data_request(self, command):
        self.write_data(protocols.RPCDataRequestProducer(command=command))

    def message_received(self, message):
        protocols.process_message(self, message, self.REGISTERED_CONSUMERS)

    def write_data(self, msg_producer):
        self.transport.write(protocols.create_msgpack_message(msg_producer.msg2str()))


async def configure_service(username, password):
    rpc_manager = RPCManagerProtocol(username=username,
                                     password=password)
    await asyncio.wait([
        protocols.ReconnectingProtocolWrapper.create_connection(
            lambda: rpc_manager,
            host="0.0.0.0",
            port=hpxclient_settings.RPC_LOCAL_PORT,
        ),
    ])
