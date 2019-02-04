import asyncio
import pproxy

from hpxclient.fetcher import transp as fetcher_transp
from hpxclient.fetcher import upstrm as fetcher_upstream
from hpxclient import settings as hpxclient_settings


FETCHER_TRANS = None

FETCHER_VERSION = 'asyncio'  # delete this once we decide to use only this


async def configure_service(user_id, session_id, public_key, ssl_context=None):
    global FETCHER_TRANS

    await asyncio.wait(
        [fetcher_upstream.configure_client(user_id, session_id,
                                           public_key, ssl_context),
         ])

    # On reconnect we don't want to set it up again
    if FETCHER_TRANS:
        return

    if FETCHER_VERSION == 'asyncio':
        server = pproxy.Server('http+socks4+socks5://:%s'
                               % hpxclient_settings.PROXY_FETCHER_LOCAL_PORT)
        settings = {'listen': pproxy.server.ProxyURI.compile_relay(
                            'http+socks4+socks5://:8080/'),
                    'rserver': [],  # TODO: fix this
                    'ulisten': [],
                    'urserver': [],
                    }

        FETCHER_TRANS = await server.start_server(settings)
    elif FETCHER_VERSION == 'thread':
        FETCHER_TRANS = await asyncio.wait([fetcher_transp.configure_server()])


