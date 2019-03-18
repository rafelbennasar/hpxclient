import asyncio
import time
import struct
import msgpack

from hpxclient import logger


DEFAULT_DELAY_TIMEOUT = 2
LENGTH_SIZE = struct.calcsize("<L")


class ReconnectingProtocolWrapper(asyncio.Protocol):
    def __init__(self, protocol_factory, host, port):
        self._protocol_factory = protocol_factory
        self._wrapped_protocol = None

        self._host = host
        self._port = port

    def connection_made(self, transport):
        self._wrapped_protocol = self._protocol_factory()
        self._wrapped_protocol.connection_made(transport)

    def connection_lost(self, exc):
        self._wrapped_protocol.connection_lost(exc)

        try:
            self._wrapped_protocol = None
            asyncio.ensure_future(
                self.create_connection(self._protocol_factory, self._host, self._port)
            )
        except AttributeError as e:
            pass
        except Exception as e:
            logger.error(e)

    def pause_writing(self):
        return self._wrapped_protocol.pause_writing()

    def resume_writing(self):
        return self._wrapped_protocol.resume_writing()

    def data_received(self, data):
        return self._wrapped_protocol.data_received(data)

    def eof_received(self):
        return self._wrapped_protocol.eof_received()

    @classmethod
    async def create_connection(cls, protocol_factory, host=None, port=None, sock=None, ssl=None,
                                retry_initial_connection=True):
        assert (host and port) or sock, "Provide sock or address:port data."
        from hpxclient.mng import service as manager_service

        loop = asyncio.get_event_loop()
        wrapper = cls(protocol_factory, host, port)
        delayed_timeout = DEFAULT_DELAY_TIMEOUT

        while True:
            try:
                if sock:
                    await loop.create_connection(lambda: wrapper, sock=sock)
                else:
                    logger.debug("Create connection for %s, %s, %s, %s",
                                 wrapper, host, port, ssl)
                    await loop.create_connection(lambda: wrapper,
                                                 host=host,
                                                 port=port,
                                                 ssl=manager_service.ssl_context)
                return
            except OSError as e:
                if not retry_initial_connection:
                    logger.info("Not retrying closed connection: %s",
                                protocol_factory)
                    break
                    #raise
                print(e)
                print("Disconnected. Trying to connect in {} seconds".format(delayed_timeout))
                delayed_timeout *= 2
                await asyncio.sleep(delayed_timeout)


class MsgpackProtocol(asyncio.Protocol):
    def __init__(self):
        self._buff = b''
        self._content_size = None

    def process_data(self):
        if self._content_size is None:
            if len(self._buff) >= LENGTH_SIZE:
                self._content_size = struct.unpack("<L",  self._buff[:LENGTH_SIZE])[0]
                self._buff = self._buff[LENGTH_SIZE:]
                return self.process_data()

        if self._content_size is None:
            return
        
        if len(self._buff) >= self._content_size:
            message = self._buff[:self._content_size]
            self.message_received(msgpack.loads(message))

            self._buff = self._buff[self._content_size:]
            self._content_size = None
            return self.process_data()

    def data_received(self, data):
        self._buff += data
        self.process_data()

    def message_received(self, message):
        raise NotImplementedError()


def create_msgpack_message(message_producer):
    data = msgpack.dumps(message_producer) # message_producer.msg2str())
    return struct.pack("<L", len(data)) + data


class MessageProducer(object):
    KIND = None

    def get_data(self):
        raise NotImplementedError()

    def msg2str(self):
        return {
            'kind': self.KIND,
            'data': self.get_data()
        }


class RegisterConnPIDProducer(MessageProducer):
    KIND = "register_pid_conn"

    def __init__(self, user_id, session_id, public_key):
        self.user_id = user_id
        self.session_id = session_id
        self.public_key = public_key

    def get_data(self):
        return {
            'user_id': self.user_id,
            'session_id': self.session_id,
            'public_key': self.public_key
        }


class RegisterConnProducer(MessageProducer):
    KIND = "register_conn"

    def __init__(self, public_key, secret_key):
        self.public_key = public_key
        self.secret_key = secret_key

    def get_data(self):
        return {
            'public_key': self.public_key,
            'secret_key': self.secret_key
        }


class RegisterBroadcastProducer(MessageProducer):
    KIND = "register_broadcast"

    def __init__(self, local_address, session_id):
        self.local_address = local_address
        self.session_id = session_id

    def get_data(self):
        return {
            "session_id": self.session_id,
            "local_address": self.local_address,
        }


class RefreshP2PBroadcastProducer(MessageProducer):
    KIND = "refresh_p2p_broadcast"

    def __init__(self, n_elements):
        self.n_elements = n_elements

    def get_data(self):
        return {
            "n_elements": self.n_elements,
        }


class BroadcastProducer(MessageProducer):
    KIND = "broadcast"

    def __init__(self, p2p_address_list):
        self.p2p_address_list = p2p_address_list

    def get_data(self):
        return {
            "p2p_addresses": self.p2p_address_list
        }


class InitConnProducer(MessageProducer):
    KIND = "init_conn"

    def __init__(self, conn_id):
        self.conn_id = conn_id

    def get_data(self):
        return {
            'conn_id': self.conn_id,
        }


class AuthRequestProducer(MessageProducer):
    KIND = "auth_req"

    def __init__(self, email, password, public_key, secret_key):
        self.email = email
        self.password = password
        self.public_key = public_key
        self.secret_key = secret_key

    def get_data(self):
        return {
            'email': self.email,
            'password': self.password,
            'public_key': self.public_key,
            'secret_key': self.secret_key
        }


class RPCAuthRequestProducer(MessageProducer):
    KIND = "rpc_auth_req"

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def get_data(self):
        return {
            'username': self.username,
            'password': self.password,
        }


class RPCAuthResponseProducer(MessageProducer):
    KIND = "rpc_auth_resp"

    def __init__(self, result):
        self.result = result

    def get_data(self):
        return {
            'result': self.result,
        }


class RPCDataRequestProducer(MessageProducer):
    KIND = "rpc_data_req"

    def __init__(self, command):
        self.command = command

    def get_data(self):
        return {
            'command': self.command,
        }


class RPCDataResponseProducer(MessageProducer):
    KIND = "rpc_data_resp"

    def __init__(self, command, response):
        self.command = command
        self.response = response

    def get_data(self):
        return {
            'command': self.command,
            'response': self.response,
        }


class AuthResponseProducer(MessageProducer):
    KIND = "auth_resp"

    def __init__(self, session_id, user_id, public_key, error=None):
        self.session_id = session_id
        self.user_id = user_id
        self.error = error
        self.public_key = public_key

    def get_data(self):
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'public_key': self.public_key,
            'error': self.error
        }


class InitConnFetchUrlProducer(MessageProducer):
    KIND = "init_conn"

    def __init__(self, conn_id, url):
        self.conn_id = conn_id
        self.url = url

    def get_data(self):
        return {
            'conn_id': self.conn_id,
            'url': self.url,
        }


class InitSessionProducer(MessageProducer):
    KIND = "init_session"

    def __init__(self, session_id):
        self.session_id = session_id

    def get_data(self):
        return {
            'session_id': self.session_id,
        }


class TransferAckProducer(MessageProducer):
    KIND = "trans_conf"

    def __init__(self, conn_id, amount_data, kind):
        self.conn_id = conn_id
        self.amount_data = amount_data
        self.kind = kind

    def get_data(self):
        return {
            'conn_id': self.conn_id,
            'amount': self.amount_data,
            'kind': self.kind
        }


class TransferDataProducer(MessageProducer):
    KIND = "trans_data"

    def __init__(self, conn_id, data, session_id=None):
        self.conn_id = conn_id
        self.data = data

    def get_data(self):
        return {
            'conn_id': self.conn_id,
            'data': self.data,
        }


class InfoBalanceProducer(MessageProducer):
    KIND = "info_balance"

    def __init__(self, amount):
        self.amount = amount

    def get_data(self):
        return {
            'amount': self.amount,
        }


class InfoVersionProducer(MessageProducer):
    KIND = "info_version"

    def __init__(self, version, url):
        self.version = version
        self.url = url

    def get_data(self):
        return {
            'url': self.url,
            'version': self.version,
        }


class CloseConnProducer(MessageProducer):
    KIND = 'close_conn'

    def __init__(self, conn_id):
        self.conn_id = conn_id

    def get_data(self):
        return {
            'conn_id': self.conn_id,
        }


class PingProducer(MessageProducer):
    KIND = 'ping'

    def __init__(self, conn_id=None):
        # DELETE ME:
        self.conn_id = conn_id
        pass

    def get_data(self):
        return {"ping:": int(time.time()),
                }


class P2PMessageProducer(MessageProducer):
    KIND = 'p2p_network'

    def __init__(self, message):
        self.message = message

    def get_data(self):
        return {
            'message': self.message
        }


class MessageConsumer(object):
    def __init__(self, protocol, data):
        self.data = data
        self.protocol = protocol

    def process(self):
        raise NotImplementedError()


class RegisterConnConsumer(MessageConsumer):
    KIND = RegisterConnProducer.KIND

class RPCAuthRequestConsumer(MessageConsumer):
    KIND = RPCAuthRequestProducer.KIND

class RPCAuthResponseConsumer(MessageConsumer):
    KIND = RPCAuthResponseProducer.KIND


class RPCDataRequestConsumer(MessageConsumer):
    KIND = RPCDataRequestProducer.KIND

class RPCDataResponseConsumer(MessageConsumer):
    KIND = RPCDataResponseProducer.KIND


class AuthRequestConsumer(MessageConsumer):
    KIND = AuthRequestProducer.KIND

class AuthResponseConsumer(MessageConsumer):
    KIND = AuthResponseProducer.KIND


class RegisterConnPIDConsumer(MessageConsumer):
    KIND = RegisterConnPIDProducer.KIND


class RegisterBroadcastConnConsumer(MessageConsumer):
    KIND = RegisterBroadcastProducer.KIND


class RefreshP2PBroadcastConsumer(MessageConsumer):
    KIND = RefreshP2PBroadcastProducer.KIND


class BroadcastConsumer(MessageConsumer):
    KIND = BroadcastProducer.KIND


class InitConnConsumer(MessageConsumer):
    KIND = InitConnProducer.KIND

#class InitConnFetchUrlConsumer(MessageConsumer):
#    KIND = InitConnProducer.KIND


class InitSessionConsumer(MessageConsumer):
    KIND = InitSessionProducer.KIND


class TransferAckConsumer(MessageConsumer):
    KIND = TransferAckProducer.KIND


class TransferDataConsumer(MessageConsumer):
    KIND = TransferDataProducer.KIND


class CloseConnConsumer(MessageConsumer):
    KIND = CloseConnProducer.KIND


class PingConsumer(MessageConsumer):
    KIND = PingProducer.KIND


class P2PMessageConsumer(MessageConsumer):
    KIND = P2PMessageProducer.KIND


class InfoBalanceConsumer(MessageConsumer):
    KIND = InfoBalanceProducer.KIND


class InfoVersionConsumer(MessageConsumer):
    KIND = InfoVersionProducer.KIND


def process_message(protocol, data, consumer_list):
    consumer_kind = data[b'kind'].decode()

    consumer_cls = None
    for _consumer_cls in consumer_list:
        if consumer_kind == _consumer_cls.KIND:
            consumer_cls = _consumer_cls
            break

    if consumer_cls is None:
        raise Exception('Kind not recognized %s, available: %s' % (consumer_cls.KIND, consumer_list))
    return consumer_cls(protocol, data[b'data']).process()



