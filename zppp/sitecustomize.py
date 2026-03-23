import os
import sys

SITE_PACKAGES = r"D:\Lib\site-packages"

if os.path.isdir(SITE_PACKAGES) and SITE_PACKAGES not in sys.path:
    sys.path.append(SITE_PACKAGES)
