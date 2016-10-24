#!/usr/bin/python

import nuke

# viewer process register
nuke.ViewerProcess.register("Dark Tower Show LUT", nuke.Node, ("DarkTower_ShowLUT", ""))
