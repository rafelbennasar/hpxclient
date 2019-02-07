import socket
import time
import configparser
import argparse
import os
import string
import random
import re
import ssl

from hpxclient import logger
from hpxclient import consts as hpxclient_consts


def cast_value(name, value):
    """ Cast the needed values to integer.
    """
    if "_PORT" in name.upper():
        try:
            return int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("Not valid port number.")
    return value


def set_ips(settings, domain):
    ip_consts = ['LISTENER', 'FETCHER', 'MNG', 'BRIDGE']
    domain_ip = socket.gethostbyname(domain)

    for ip_const in ip_consts:
        setting_name = 'PROXY_%s_SERVER_IP' % ip_const
        setattr(settings, setting_name, domain_ip)
    setattr(settings, 'DOMAIN_IP', domain_ip)


def load_data_config_file(config_file):
    from hpxclient import settings as hpxclient_settings
    if not config_file:
        config_file = os.path.join(hpxclient_settings.HPROXY_DIR, 'hprox.cfg')

    config = configparser.ConfigParser()
    try:
        config.read_file(open(config_file))
        logger.info("Loading settings from %s", config_file)
    except FileNotFoundError:
        logger.info("No file settings found: %s", config_file)

    # This list prunes some parameters that can be in consts.py but
    # they cannot be defined via hprox.cfg
    _NOT_ALLOWED_IN_CONF = ["SECRET_KEY", ]

    # Loading settings from the config file.
    for section in config.sections():
        for name, value in config[section].items():
            logger.debug(">> Setting from config file. Key: %s, value: %s",
                         name, value)
            # We consider as a valid configuration parameter anything
            # that is listed in hpxclient.settings.
            try:
                getattr(hpxclient_settings, name.upper())
            except NameError:
                raise argparse.ArgumentTypeError(
                    "Not valid configuration parameter: %s" % name)

            if 'DOMAIN' in name.upper():
                set_ips(hpxclient_settings, value)

            if 'DEBUG' in name.upper():
                value = True if value.lower() == 'true' else False

            if name.upper() in _NOT_ALLOWED_IN_CONF:
                raise argparse.ArgumentTypeError(
                    "Not valid configuration parameter: %s" % name)
            setattr(hpxclient_settings, name.upper(),
                    cast_value(name, value))

    if hasattr(hpxclient_settings, 'SECRET_KEY_FILE') \
            and hpxclient_settings.SECRET_KEY_FILE:
        try:
            with open(hpxclient_settings.SECRET_KEY_FILE) as f:
                logger.debug(">> Setting SECRET KEY from file: %s",
                             hpxclient_settings.SECRET_KEY_FILE)
                hpxclient_settings.SECRET_KEY = f.readline().strip()
        except FileNotFoundError:
            pass


def load_config():
    """ Load configuration settings from hprox.cfg. If any
    extra parameter is supplied via command overwrites the
    configuration file.

    We consider as a valid configuration setting all items
    listed in the hpxclient.consts.
    """
    from hpxclient import settings as hpxclient_settings

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", type=int, choices=[0, 1, 2],
                        help="increase output verbosity")

    parser.add_argument("-rpc", "--rpc-local-port",
                        dest="RPC_LOCAL_PORT",
                        type=int,
                        help="Define the LOCAL PORT for the RPC protocol.")

    parser.add_argument("-p", "--port",
                        dest="PROXY_LISTENER_LOCAL_PORT",
                        type=int,
                        help="Define the LOCAL PORT for the listener service.")

    parser.add_argument("-pk", "--public-key",
                        dest="PUBLIC_KEY",
                        help="Define the network's access PUBLIC KEY.")
    parser.add_argument("-skf", "--secret-key-file",
                        dest="SECRET_KEY_FILE",
                        help="Define the file that contains the network's access SECRET KEY.")

    parser.add_argument("-c", "--config",
                        dest="config_file",
                        help="Define configuration file.")

    args = parser.parse_args()

    config_file = args.config_file

    # Loading settings from config file.
    load_data_config_file(config_file)

    # Loading settings from the command line. They overwrite config file.
    for name, value in args.__dict__.items():
        if value:
            setattr(hpxclient_settings, name,
                    cast_value(name, value))

    # Loading settings from environ. They overwrite everything.
    if "HPROX_PUBLIC_KEY" in os.environ:
        logger.info("Reading PUBLIC KEY from environment.")
        hpxclient_settings.PUBLIC_KEY = os.environ["HPROX_PUBLIC_KEY"]

    if "HPROX_SECRET_KEY" in os.environ:
        logger.info("Reading SECRET KEY from environment.")
        hpxclient_settings.SECRET_KEY = os.environ["HPROX_SECRET_KEY"]


def rndstrs(length, alphabet=string.ascii_letters + string.digits):
    return ''.join(random.choice(alphabet) for _ in range(length))


def clean_url(url):
    """ Given any url it returns its host in a standarized manner.
    """
    url_re = re.compile('(?:http.*://)?(www.)?(?P<host>[^:/ ]+).?(?P<port>[0-9]*).*')
    return url_re.search(url).group("host").lower()


def get_url_from_headers(headers):
    try:
        return headers.split()[1].decode()
    except (IndexError, UnicodeDecodeError):
        return None


def get_host_from_headers(headers):
    try:
        raw_headers = headers.split(b"\r\n")
        host = raw_headers[0].split()[1].decode()
        return clean_url(host)
    except IndexError:
        return None


def create_ssl_context_user():
    from hpxclient import settings as hpxclient_settings

    if hpxclient_settings.DEBUG:
        return None

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE  # TODO: Are we sure we want verify mode none!?
    return ssl_context


def is_captive_platform(url):
    """Returns whether the url is for Captive Platform"""
    # TODO: cache?
    if not url:
        return False
    
    for regex in hpxclient_consts.CAPTIVE_PORTALS_REGEX:
        if regex.match(url):
            return True
    return False


def get_utime_ms():
    return int(time.time()*1000.0)