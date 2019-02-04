from hpxclient import protocols


class RegisterConnProducer(protocols.RegisterConnProducer):
    pass


class RegisterBroadcastProducer(protocols.RegisterBroadcastProducer):
    pass


class InitConnProducer(protocols.InitConnProducer):
    pass


class TransferDataProducer(protocols.TransferDataProducer):
    pass


class CloseConnProducer(protocols.CloseConnProducer):
    pass


class PingProducer(protocols.PingProducer):
    pass

class P2PMessageProducer(protocols.P2PMessageProducer):
    pass