#!/usr/bin/env python3

import argparse
import sys
import getpass
import asyncio
from asynccmd import Cmd

from hpxclient.rpc import service as rpc_service


class HProxShell(Cmd):
    def __init__(self, mode, intro, prompt):
        # We need to pass in Cmd class mode of async cmd running
        super().__init__(mode=mode)
        self.intro = intro
        self.prompt = prompt
        self.loop = None
        self.username = None
        self.password = None
        asyncio.ensure_future(self.connect_to_manager())

    async def connect_to_manager(self):
        if not self.username:
            self.username = input("Username: ")
        if not self.password:
            self.password = getpass.getpass("Password: ")
        await rpc_service.configure_service(username=self.username,
                                            password=self.password)

    def do_balance(self, args):
        rpc_service.RPC_MANAGER.send_rpc_data_request("balance")

    def do_usage(self, args):
        rpc_service.RPC_MANAGER.send_rpc_data_request("usage")

    def start(self, loop=None):
        self.loop = loop
        super().cmdloop(loop)


def _load_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--username",
                        dest="username",
                        type=str,
                        )
    parser.add_argument("-p", "--password",
                        dest="password",
                        type=str,
                        )
    return parser.parse_args()


def main():
    # For win system we have only Run mode
    # For POSIX system Reader mode is preferred
    if sys.platform == 'win32':
        loop = asyncio.ProactorEventLoop()
        mode = "Run"
    else:
        loop = asyncio.get_event_loop()
        mode = "Reader"

    RPC_SHELL = HProxShell(mode=mode,
                           intro="\n\n\nThis is the hprox shell.",
                           prompt="hprox> ")


    params = _load_config()
    for name, value in params.__dict__.items():
        if value:
            setattr(RPC_SHELL, name, value)

    RPC_SHELL.start(loop)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.stop()

if __name__ == "__main__":
    main()