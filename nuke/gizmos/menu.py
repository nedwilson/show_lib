import nuke

def echo_camera_format_node():
    noop_node = nuke.createNode("NoOp", "name EchoCameraFormat")
    noop_node.knob('label').setValue(
        'Camera Format\n[if {([value input.width] == 4971) && ([value input.height] == 2349)} {return "Alexa 65"} else {[if {([value input.width] == 4334) && ([value input.height] == 3016)} {return "Alexa LF"} else {[if {([value input.width] == 4172) && ([value input.height] == 1740)} {return "Alexa LF 2.39"} else {[if {([value input.width] == 3424) && ([value input.height] == 2202)} {return "Alexa Mini"} else {[if {([value input.width] == 3840) && ([value input.height] == 2160)} {return "Blackmagic"} else {return "Unknown"}]}]}]}]}]')
    noop_node.knob('tile_color').setValue(int(0xffce77ff))
    noop_node.knob('note_font_size').setValue(20)
    noop_node.knob('note_font').setValue('Verdana Bold Bold Bold Bold Bold')

menubar = nuke.menu("Nuke")
m = menubar.addMenu("Romeo")
m.addCommand("Echo Camera Format", 'echo_camera_format_node()')
m.addCommand("Romeo Reformat", r'nuke.createNode("Romeo_Reformat")')
