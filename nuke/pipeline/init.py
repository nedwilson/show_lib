#!/usr/bin/python

import nuke

# viewer process register
nuke.ViewerProcess.register("Skyscraper Show LUT", nuke.Node, ("Skyscraper_ShowLUT", ""))
