import re

HPX_NUMBER_OF_DECIMALS = 8

COUNTRY_PROXY = "PL"

HPROX_DIR_NAME = '.hprox'
HPROX_CONFIG_NAME = 'hprox.cfg'

def compile_cp_regex():
    return [re.compile(regex) for regex in [
        r"http://go\.microsoft\.com/fwlink/\?LinkID=219472(.*)",
        r"http://www\.gstatic\.com/generate_204",
        r"http://detectportal\.firefox\.com/",
        r"http://clients\d\.google\.com/generate_204"
    ]]


CAPTIVE_PORTALS_REGEX = compile_cp_regex()
