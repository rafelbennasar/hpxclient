import asyncio

from hpxclient import logger
from hpxclient import protocols


class RegisterConnConsumer(protocols.RegisterConnConsumer):
    def process(self):
        logger.info("[Bridge] validating public/ secret key.")
        #is_auth = plib_utils.validate_pub_sec_keys(self.data[b'public_key'],
        #                                           self.data[b'secret_key'])
        #self.protocol.is_authorized = is_auth
        #self.protocol.public_key = self.data[b"public_key"]

        #if not is_auth:
        #    logger.info("Listener connection-consumer not correct. Closing transport.")
        #    self.protocol.transport.close()


class RegisterConnPIDConsumer(protocols.RegisterConnPIDConsumer):
    def process(self):
        pass


class InitConnConsumer(protocols.InitConnConsumer):
    def process(self):
        pass


class BroadcastConsumer(protocols.BroadcastConsumer):
    """
        Check topology of the connection schema in:
         http://www.brynosaurus.com/pub/net/p2pnat/

    """
    def process(self):
        p2p_addresses = self.data[b"p2p_addresses"]

        task_list = []
        for peer_local_address, peer_remote_address in p2p_addresses:
            print("My priv %s.\n Peer priv %s, peer pub %s" %(self.protocol.local_addr,
                                                              peer_local_address,
                                                              peer_remote_address))
            aux_partner_remote_address = (peer_local_address[0],
                                          self.protocol.local_addr[1])
            """
                From the same local TCP ports that A and B used to
                register with S,  A and B each asynchronously make
                outgoing connection attempts to the other's public and
                private endpoints as reported by S, while simultaneously
                listening for incoming connections on their respective
                local TCP ports.
            """
            task_list.extend([
                self.protocol.create_p2p_listener_server(port=peer_local_address[1]),
                self.protocol.create_p2p_listener_server(port=peer_remote_address[1]),
                self.protocol.create_reusable_connection(peer_local_address),
                self.protocol.create_reusable_connection(aux_partner_remote_address)
                ])
        asyncio.gather(*task_list)


class TransferDataConsumer(protocols.TransferDataConsumer):

    def process(self):
        from hpxclient.listener.consumers import BROWSER_TASKS
        conn_id, data = self.data[b'conn_id'], self.data[b'data']
        logger.info("CONSUMER transfer data: %s : %s", self.data[b"conn_id"], self.data[b"data"])
        if conn_id in BROWSER_TASKS:
            BROWSER_TASKS[conn_id].write(data)


class CloseConnConsumer(protocols.CloseConnConsumer):

    def process(self):
        pass


class PingConsumer(protocols.PingConsumer):

    def process(self):
        pass


class P2PMessageConsumer(protocols.P2PMessageConsumer):
    KIND = 'p2p_network'

    def process(self):
        logger.info("Message: %s", self.data)
