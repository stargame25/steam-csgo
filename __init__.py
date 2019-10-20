__version__ = "0.3.3"
__author__ = "Andriy Herasymchuk"

version_info = (0, 3, 3)

import sys

if sys.version_info[0] == 3:
    from .wrapper import *
else:
    pass
