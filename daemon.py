import logging
import asyncio
import sys

from hpxclient.mng import service as mng_service
from hpxclient import utils as hpxclient_utils
from hpxclient import settings as hpxclient_settings

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)-15s %(filename)s %(lineno)d %(funcName)s %(message)s')


def main():

    hpxclient_utils.load_config()
    loop = asyncio.get_event_loop()
    #loop.set_debug(True)

    loop.run_until_complete(
        mng_service.start_client(public_key=hpxclient_settings.PUBLIC_KEY,
                                 secret_key=hpxclient_settings.SECRET_KEY))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        sys.stderr.flush()
        print('\nClient stopped\n')

    finally:
        pending = asyncio.Task.all_tasks()
        for p in pending:
            p.cancel()
        loop.run_until_complete(loop.shutdown_asyncgens())


if __name__ == "__main__":
    main()
