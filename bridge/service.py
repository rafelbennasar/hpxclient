import asyncio
import socket
import time

from hpxclient import logger
#from hpxclient import consts as hpxclient_consts
from hpxclient import settings as hpxclient_settings
from hpxclient.bridge import consumers as bridge_consumers
from hpxclient.bridge import producers as bridge_producers
from hpxclient.bridge import consts as bridge_consts
from hpxclient import protocols

BROADCAST_POOL_SIZE = 10

BRIDGE = None

# conn_id -> Protocol
P2P_CLIENTS = {}

"""
four scenarios:
    public ip   AND     home => ok
    mobile      AND     home => ok
    home + vpn  AND     home + vpn => ok
    mobile      AND     home + vpn => fail

"""


class P2PBridge(protocols.MsgpackProtocol):
    """ P2PBridge protocol connects to other clients Bridges. """

    # Interval to send ping to peer to keep the connection alive.
    #  PEER_PING_INTERVAL = 10

    # Timeout for not responding peers.
    # Closes connection with any peer with ping bigger than PING_TIMEOUT
    #  PEER_PING_TIMEOUT = 20

    REGISTERED_P2P_BRIDGE_CONSUMERS = [
        bridge_consumers.PingConsumer,
        bridge_consumers.InitConnConsumer,
        bridge_consumers.RegisterConnPIDConsumer,
        bridge_consumers.BroadcastConsumer,
        bridge_consumers.TransferDataConsumer,
        bridge_consumers.P2PMessageConsumer,
        bridge_consumers.CloseConnConsumer
    ]

    def __init__(self, pid, conn_id):
        super().__init__()
        self.conn_id = conn_id
        self.pid = pid

    def connection_made(self, transport):
        self.transport = transport
        self.last_ping_response = None

        P2P_CLIENTS[self.pid] = self
        print("connection made!", self.pid, id(self))
        self.write_data(
            bridge_producers.P2PMessageProducer("P2PListen message with id %s. %s to %s" %
                                                (id(self),
                                                 self.transport._extra["sockname"],
                                                 self.transport._extra["peername"]))
        )

        asyncio.ensure_future(self.ping_service())

    async def ping_service(self):
        """ Ping the other peer and we check when was the last
        time that he pinged us. If it's longer than PING_TIMEOUT
        we break the connection.
        """
        while True:
            self.ping_peer()
            now = int(time.time())
            if self.last_ping_response is not None \
                    and bridge_consts.PEER_PING_TIMEOUT < now - self.last_ping_response:
                logger.info("Closed connection due to PING TIMEOUT")
                self.transport.close()
            await asyncio.sleep(bridge_consts.PEER_PING_INTERVAL)

    def ping_peer(self):
        """ Pings peer to keep the connection open and to notify
        to our peer that we are still connected.
        """
        self.write_data(protocols.PingProducer())

    def init_conn(self, conn_id):
        """ The URL task connection started. """
        self.write_data(protocols.InitConnProducer(conn_id))

    def register_conn(self):
        logger.info("Registering connection from bridge to p2p server.")
        self.write_data(protocols.RegisterConnProducer(self.pid,
                                                            self.conn_id))

    def close_conn(self, conn_id):
        """ The URL task connection was closed. """
        self.write_data(protocols.CloseConnProducer(conn_id))

    def connection_lost(self, exc):
        """ The connection with the P2P peer was closed.
        It must be taken out from the P2P clients pool.
        """
        if self.pid in P2P_CLIENTS:
            del P2P_CLIENTS[self.pid]
            logger.info("Connection with %s was closed. Error: %s", self.pid, exc)
        else:
            logger.error("Public key %s was not in P2P clients! Error: %s", self.pid, exc)

    def trans_conn(self, conn_id, data):
        self.write_data(protocols.TransferDataProducer(conn_id, data))

    def message_received(self, message):
        protocols.process_message(self, message,
                                       self.REGISTERED_P2P_BRIDGE_CONSUMERS)

    def write_data(self, msg_producer):
        self.transport.write(
            protocols.create_msgpack_message(msg_producer.msg2str())
        )


class Bridge(protocols.MsgpackProtocol):
    """ Bridge protocol connects to the server rendezvous-p2p-server and
    allows to connect p2p clients in between them.

    {protocol, public address, public port, remote address, remote port}

    """
    """

    Suppose that client A wishes to set up a TCP connection
    with client B. We assume as usual that both A and B
    already have active TCP connections with a well-known
    rendezvous server S.

    The server records each registered client's public and
    private endpoints.

    At the protocol level, TCP hole punching works in this way:

        Client A uses its active TCP session with S to ask S
        for help connecting to B.

        S replies to A with B's public and private TCP
        endpoints, and at the same time sends A's public and
        private endpoints to B.

        From the same local TCP ports that A and B used to
        register with S,  A and B each asynchronously make
        outgoing connection attempts to the other's public and
        private endpoints as reported by S, while simultaneously
        listening for incoming connections on their respective
        local TCP ports.

        A and B wait for outgoing connection attempts to succeed,
        and/or for incoming connections to appear. If one of the
        outgoing connection attempts fails due to a network error
        such as “connection reset” or “host unreachable,” the host
        simply re-tries that connection attempt after a short delay
        (e.g., one second), up to an application-defind maximum
        timeout period.

        When a TCP connection is made, the hosts authenticate each
        other to verify that they connected to the intended host.
        If authentication fails, the clients close that connection
        and continue waiting for others to succeed. The clients use
        the first successfully authenticated TCP stream resulting
        from this process.

        Unlike with UDP, where each client only needs one socket to
        communicate with both S and any number of peers simultaneously,
        with TCP each client application must manage several sockets
        bound to a single local TCP port on that client node, as
        shown in Figure 7.

        Each client needs a stream socket representing its connection
        to S, a listen socket on which to accept incoming connections
        from peers, and at least two additional stream sockets with
        which to initiate outgoing connections to the other peer's
        public and private TCP endpoints.


    """

    REGISTERED_BRIDGE_CONSUMERS = [
        bridge_consumers.InitConnConsumer,
        bridge_consumers.RegisterConnPIDConsumer,
        bridge_consumers.BroadcastConsumer,
        bridge_consumers.CloseConnConsumer,
        bridge_consumers.PingConsumer
    ]

    def __init__(self, pid, session_id, public_key):
        super().__init__()
        self.pid = pid
        self.session_id = session_id
        self.public_key = public_key

        self.is_authorized = False

        self.transport = None
        # self.conn_id = plib_utils.rndstrs(32).encode()

        self.local_addr = None
        self.remote_addr = None
        #self.channel_ui = hpxclient_utils.get_current_ui_channel(name='bridge', protocol=self)

    def connection_made(self, transport):
        global BRIDGE
        BRIDGE = self

        self.transport = transport
        self.init_conn(self.conn_id)
        self.register_conn()
        self.init_session(self.pid)
        asyncio.ensure_future(self.ping_service())
        asyncio.ensure_future(self.p2p_fill_rate_service())
        asyncio.ensure_future(self.create_p2p_listener_server(hpxclient_settings.P2P_BRIDGE_SERVER_PORT))

    async def ping_service(self):
        """ Ping from Rendezvous server to p2hpxclient connected.
        """
        while self.transport: # meanwhile connection is active.
            self.ping_peer()
            await asyncio.sleep(bridge_consts.BRIDGE_PING_INTERVAL)

    async def p2p_fill_rate_service(self):
        """ Controls that at least
        Ping the other peer and we check when was the last
        time that he pinged us. If it's longer than PING_TIMEOUT
        we break the connection.
        """
        while True:
            n_elements = len(P2P_CLIENTS)
            if n_elements < BROADCAST_POOL_SIZE:
                n_new_elements = BROADCAST_POOL_SIZE - len(P2P_CLIENTS)
                self.write_data(protocols.RefreshP2PBroadcastProducer(n_new_elements))
            await asyncio.sleep(bridge_consts.BRIDGE_FILL_RATE_INTERVAL)

    def ping_peer(self):
        self.write_data(protocols.PingProducer())

    def init_conn(self, conn_id):
        """ Initializes connection after a browser request.
        """
        self.write_data(protocols.InitConnProducer(conn_id))

    def init_session(self, pid):
        """ After receiving the session id from the fetcher
        we are able to register broadcast with the rendevouz server
        and this will provoke that the rendevouz server puts our
        ip address in the redis.
        """
        # TODO: What does need use? pid or conn_id instead session_id ?
        self.session_id = pid # was session
        self.register_broadcast()

    def register_conn(self):
        logger.info("Registering connection from bridge to p2p server.")
        self.write_data(protocols.RegisterConnPIDProducer(user_id=self.user_id,
                                                               session_id=self.session_id,
                                                               public_key=self.public_key))

    def register_broadcast(self):
        """ Sends broadcast data to the p2p rendezvous server.
        """
        self.local_addr = self.transport.get_extra_info("sockname")
        logger.info("My transport sockname (local address) is: {}".format(self.local_addr))
        self.write_data(bridge_producers.RegisterBroadcastProducer(self.local_addr,
                                                                   self.session_id)) # was session

    def close_conn(self, conn_id):
        self.write_data(protocols.CloseConnProducer(conn_id))

    async def create_p2p_listener_server(self, port):
        #ssl_context = plib.utils.create_ssl_context_server(self.local_addr)
        loop = asyncio.get_event_loop()
        bridge_ = P2PBridge(self.pid, self.conn_id)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        ssl_sock = None #ssl_context.wrap_socket(sock)
        # ssl_sock.connect(('0.0.0.0', port))
        print("Local server P2P listener on %s" % port)
        return await loop.create_server(lambda: bridge_,
                                        sock=ssl_sock)

    async def create_reusable_connection(self, address):
        while True:
            try:
                loop = asyncio.get_event_loop()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                sock.connect(tuple(address))
                bridge_ = P2PBridge(self.pid,
                                    self.conn_id)
                transport, protocol = await loop.create_connection(lambda: bridge_,
                                                                   sock=sock,
                                                                   local_addr=self.local_addr)
            except Exception as e:
                print(e, address)
            else:
                print("ok! connection done!")
                protocol.register_conn()
                break
            await asyncio.sleep(1)

    def message_received(self, message):
        protocols.process_message(self, message, self.REGISTERED_BRIDGE_CONSUMERS)

    def write_data(self, msg_producer):
        self.transport.write(
            protocols.create_msgpack_message(msg_producer.msg2str())
        )


async def configure_server(pid, session_id, public_key, ssl_context):
    bridge_ = Bridge(pid=pid,
                     session_id=session_id,
                     public_key=public_key)
    loop = asyncio.get_event_loop()

    s = socket.socket(socket.AF_INET,
                      socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    ssl_socket = ssl_context.wrap_socket(s)
    try:
        ssl_socket.connect((hpxclient_settings.PROXY_BRIDGE_SERVER_IP,
                   int(hpxclient_settings.PROXY_BRIDGE_SERVER_PORT)))
    except:
        logger.error("Connection to bridge failed: ",
                     (hpxclient_settings.PROXY_BRIDGE_SERVER_IP,
                      int(hpxclient_settings.PROXY_BRIDGE_SERVER_PORT)))
    return await protocols.ReconnectingProtocolWrapper.create_connection(
        lambda: bridge_,
        sock=ssl_socket,
    )
