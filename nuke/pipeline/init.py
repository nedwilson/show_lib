#!/usr/bin/python

import nuke

# viewer process register
nuke.ViewerProcess.register("Spinel Show LUT", nuke.Node, ("Spinel_ShowLUT", ""))
