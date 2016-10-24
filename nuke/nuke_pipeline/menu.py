#!/usr/bin/python

import nuke
import darktower_delivery
import ConfigParser
import sys
from darktower_utilities import *

g_ih_show_code = None
g_delivery_folder = None
try:
    g_ih_show_code = os.environ['IH_SHOW_CODE']
    config = ConfigParser.ConfigParser()
    config.read(os.environ['IH_SHOW_CFG_PATH'])
    if sys.platform == "win32":
        g_delivery_folder = config.get('darktower', 'delivery_folder_win32')
    else:
        g_delivery_folder = config.get('darktower', 'delivery_folder')
    print "INFO: Successfully loaded show-specific Python code for %s."%g_ih_show_code
except KeyError:
    pass
    

    
menubar = nuke.menu("Nuke")
m = menubar.addMenu("Dark Tower")
n = m.addMenu("&Delivery")
n.addCommand("Submit for Review", "send_for_review_darktower()")
n.addCommand("Publish Delivery","nuke.message(darktower_delivery.deliver(nuke.getFilename(\"Pick The Folder To Deliver\", default=\"%s\")))"%g_delivery_folder)


