#!/usr/bin/python
import datetime
start_time = datetime.datetime.now()

import nuke
import skyscraper_delivery
import ConfigParser
import sys
from skyscraper_utilities import *

g_ih_show_code = None
g_delivery_folder = None
try:
    g_ih_show_code = os.environ['IH_SHOW_CODE']
    config = ConfigParser.ConfigParser()
    config.read(os.environ['IH_SHOW_CFG_PATH'])
    if sys.platform == "win32":
        g_delivery_folder = config.get('skyscraper', 'delivery_folder_win32')
    else:
        g_delivery_folder = config.get('skyscraper', 'delivery_folder')
    print "INFO: Successfully loaded show-specific Python code for %s."%g_ih_show_code
except KeyError:
    pass
    

    
menubar = nuke.menu("Nuke")
m = menubar.addMenu("Skyscraper")
m.addCommand("SKY Reformat", "nuke.createNode(\"Sky_Reformat\")")
m.addCommand("New Shot", "new_shot()")
n = m.addMenu("&Delivery")
n.addCommand("Submit for Review", "send_for_review_skyscraper()")
n.addCommand("Publish Delivery","nuke.message(skyscraper_delivery.deliver(nuke.getFilename(\"Pick The Folder To Deliver\", default=\"%s\")))"%g_delivery_folder)
n = m.addMenu("Color")
n.addCommand("Create Viewer Process", "create_viewer_input()", "alt+shift+v")

print "INFO: skyscraper menu.py execution time: %s"%(datetime.datetime.now() - start_time)

