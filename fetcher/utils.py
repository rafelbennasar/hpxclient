import string

from hpxclient.plib import utils as hpxclient_utils


def generate_dummyheaders(amount=32):
    return ['X-%s: %s\r\n' % (hpxclient_utils.rndstrs(16, string.ascii_uppercase),
                              hpxclient_utils.rndstrs(128)) for _ in range(amount)]



