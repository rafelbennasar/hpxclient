from hpxclient import protocols


class RPCAuthResponseConsumer(protocols.RPCAuthResponseConsumer):

    def process(self):
        is_auth = self.data[b"result"]
        if not is_auth:
            self.protocol.transport.close()
            print("Password not correct. Closing shell.")
            exit()


class RPCDataResponseConsumer(protocols.RPCDataResponseConsumer):

    def process(self):
        response = self.data[b"response"]
        print("> %s" % response)
