
# Interval to send a ping to the rendezvous server
BRIDGE_PING_INTERVAL = 10

# Interval to refresh p2p broadcast connections. After this
# time, we will try to fetch more p2p connections if
# we don't have BROADCAST_POOL_SIZE p2p connections.
BRIDGE_FILL_RATE_INTERVAL = 10

# Interval to send ping to peer to keep the connection alive.
PEER_PING_INTERVAL = 120

# Timeout for not responding peers.
# Closes connection with any peer with ping bigger than PING_TIMEOUT
PEER_PING_TIMEOUT = 140
