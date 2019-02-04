import logging

FORMAT = "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)s - %(funcName)10s() ] %(message)s"
logging.basicConfig(level=logging.DEBUG,
                    format=FORMAT)
logging.basicConfig(format=FORMAT)
logging.getLogger('asyncio').setLevel(logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger(__name__).setLevel(logging.INFO)
