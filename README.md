# show_lib

Important items to edit:

./darktower.cfg

Here is where you would specify things like an in-house email account and password, the show LUT file (goes in SHOW/SHARED/lut), the email address lists for deliveries, and the path to the delivery template Nuke script.

./nuke/gizmos/DarkTower_ShowLUT.gizmo
./nuke/gizmos/DarkTower_ShowLUT.nk

These files will apply the viewer LUT as part of Nuke'S ViewerProcess. They convert the input from LogC to Linear, apply a shot-specific CDL file (located in SEQUENCE/SHOT/data/cdl/SHOT.cdl), and apply the show LUT, which usually outputs Rec.709.

./nuke/delivery/darktower_slate_template_v0001.nk

This is where you specify how the slates are made, how the DPX frames are built, and how the shot Quicktimes are built.
