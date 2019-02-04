import os
import pathlib
import socket

DEBUG = False

USER_DIR = str(pathlib.Path.home())
HPROXY_DIR = os.path.join(USER_DIR, '.hproxy')

if not os.path.exists(HPROXY_DIR):
    os.mkdir(HPROXY_DIR)

PROXY_LISTENER_LOCAL_PORT = 8080
DOMAIN = 'hprox.com'
DOMAIN_IP = socket.gethostbyname(DOMAIN)

# The listener server which handle local connection and proxies them.
PROXY_LISTENER_SERVER_IP, PROXY_LISTENER_SERVER_PORT = DOMAIN_IP, 10014

# The port where proxy listening incoming connection for fetching
# and return to proxy engine.
PROXY_FETCHER_LOCAL_PORT = 8090

# The server with job to fetching (connected by domestic proxies).
PROXY_FETCHER_SERVER_IP, PROXY_FETCHER_SERVER_PORT = DOMAIN_IP, 10012

# The proxy engine management server.
PROXY_MNG_SERVER_IP, PROXY_MNG_SERVER_PORT = DOMAIN_IP, 10010

# Rendezvous server for p2p connections
PROXY_BRIDGE_SERVER_IP, PROXY_BRIDGE_SERVER_PORT = DOMAIN_IP, 10016
P2P_BRIDGE_SERVER_PORT = 10111

# RPC settings
RPC_USERNAME = None
RPC_PASSWORD = None
RPC_LOCAL_PORT = 10999

# These variables will be filled with env-vars values or conf files:
PUBLIC_KEY = None
SECRET_KEY = None
SECRET_KEY_FILE = None