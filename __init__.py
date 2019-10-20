__version__ = "1.0.1"
__author__ = "Andriy Herasymchuk"

version_info = (1,0,1)

import sys

if sys.version_info[0] == 3:
    from .wrapper import *
else:
    pass
