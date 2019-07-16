# show_lib

Important items to edit:

./morbius.cfg

Here is where you would specify things like an in-house email account and password, the show LUT file (goes in SHOW/SHARED/lut), the email address lists for deliveries, and the path to the delivery template Nuke script.

./nuke/gizmos/Morbius_ShowLUT.gizmo
./nuke/gizmos/Morbius_ShowLUT.nk

These files will apply the viewer LUT as part of Nuke's ViewerProcess. They convert the input from LogC to Linear, apply a shot-specific CC file (located in SEQUENCE/SHOT/data/color/SHOT.cc), and apply the show LUT, which usually outputs Rec.709.

./nuke/delivery/morbius_slate_template_v001.nk

This is where you specify how the slates are made, how the EXR frames are built, and how the shot Quicktimes are built.
