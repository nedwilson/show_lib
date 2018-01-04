#!/usr/bin/python

import nuke
import nukescripts
import os
import sys
import traceback
from utilities import *
import pwd
import ConfigParser
import tempfile
import threading
import glob
import shutil
import re
import cdl_convert

class SkyscraperNotesPanel(nukescripts.PythonPanel):
    def __init__(self):
        nukescripts.PythonPanel.__init__(self, 'Skyscraper Review Submission')
        self.cvn_knob = nuke.Multiline_Eval_String_Knob('cvn_', 'current version notes', 'For review')
        self.addKnob(self.cvn_knob)
        self.cc_knob = nuke.Boolean_Knob('cc_', 'CC', True)
        self.cc_knob.setFlag(nuke.STARTLINE)
        self.addKnob(self.cc_knob)
        self.avidqt_knob = nuke.Boolean_Knob('avidqt_', 'Avid QT', True)
        self.addKnob(self.avidqt_knob)
        self.vfxqt_knob = nuke.Boolean_Knob('vfxqt_', 'VFX QT', True)
        self.addKnob(self.vfxqt_knob)
        self.exr_knob = nuke.Boolean_Knob('exr_', 'EXR', False)
        self.addKnob(self.exr_knob)
        self.matte_knob = nuke.Boolean_Knob('matte_', 'Matte', False)
        self.addKnob(self.matte_knob)

def get_delivery_directory_skyscraper(str_path, b_istemp=False):
    delivery_folder = str_path
    s_folder_contents = "EXR"
    if b_istemp:
        s_folder_contents = "MOV"
    tday = datetime.date.today().strftime('%Y%m%d')
    matching_folders = glob.glob(os.path.join(delivery_folder, "INH_%s_*"%tday))
    noxl = ""
    max_dir = 0
    if len(matching_folders) == 0:
        calc_folder = os.path.join(delivery_folder, "INH_%s_01"%tday)
    else:
        for suspect_folder in matching_folders:
            csv_spreadsheet = glob.glob(os.path.join(suspect_folder, "*.csv"))
            excel_spreadsheet = glob.glob(os.path.join(suspect_folder, "*.xls*"))
            if len(excel_spreadsheet) == 0 and len(csv_spreadsheet) == 0 and os.path.exists(os.path.join(suspect_folder, ".delivery")):
                noxl = suspect_folder
            else:
                dir_number = int(os.path.basename(suspect_folder).split('_')[-1])
                if dir_number > max_dir:
                    max_dir = dir_number
        if noxl != "":
            calc_folder = noxl
        else:
            calc_folder = os.path.join(delivery_folder, "INH_%s_%02d" % (tday, max_dir + 1))
    print "INFO: Returning delivery folder: %s"%calc_folder
    return calc_folder

def render_delivery_threaded(ms_python_script, start_frame, end_frame, md_filelist):
    progress_bar = nuke.ProgressTask("Building Delivery")
    progress_bar.setMessage("Initializing...")
    progress_bar.setProgress(0)

    s_nuke_exe_path = nuke.env['ExecutablePath']  # "/Applications/Nuke9.0v4/Nuke9.0v4.app/Contents/MacOS/Nuke9.0v4"
    s_pyscript = ms_python_script

    s_cmd = "%s -i -V 2 -c 2G -t %s" % (s_nuke_exe_path, s_pyscript)
    s_err_ar = []
    f_progress = 0.0
    frame_match_txt = r'^Rendered frame (?P<frameno>[0-9]{1,}) of (?P<filebase>[a-zA-Z0-9-_]+)\.mov\.$'
    frame_match_re = re.compile(frame_match_txt)
    print "INFO: Beginning: %s" % s_cmd
    proc = subprocess.Popen(s_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    progress_bar.setMessage("Beginning Render.")
    while proc.poll() is None:
        try:
            s_out = proc.stdout.readline()
            s_err_ar.append(s_out.rstrip())
            matchobject = frame_match_re.search(s_out)
            if matchobject:
                s_exr_frame = matchobject.groupdict()['frameno']
                s_file_name = matchobject.groupdict()['filebase']
                i_exr_frame = int(s_exr_frame)
                f_duration = float(end_frame - start_frame + 1)
                f_progress = (float(i_exr_frame) - float(start_frame) + 1.0)/f_duration
                progress_bar.setMessage("Rendering frame %d of %s..."%(i_exr_frame,s_file_name))
                progress_bar.setProgress(int(f_progress * 50))
        except IOError:
            print "ERROR: IOError Caught!"
            var = traceback.format_exc()
            print var
    if proc.returncode != 0:
        s_errmsg = ""
        s_err = '\n'.join(s_err_ar)
        l_err_verbose = []
        for err_line in s_err_ar:
            if err_line.find("ERROR") != -1:
                l_err_verbose.append(err_line)
        if s_err.find("FOUNDRY LICENSE ERROR REPORT") != -1:
            s_errmsg = "Unable to obtain a license for Nuke! Package execution fails, will not proceed!"
        else:
            s_errmsg = "Error(s) have occurred. Details:\n%s"%'\n'.join(l_err_verbose)
        nuke.critical(s_errmsg)
    else:
        print "INFO: Successfully completed delivery render."
        
    # copy the files
    d_expanded_list = {}
    for s_src in md_filelist:
        if s_src.find('*') != -1:
            l_imgseq = glob.glob(s_src)
            for s_img in l_imgseq:
                d_expanded_list[s_img] = os.path.join(md_filelist[s_src], os.path.basename(s_img))
        else:
            d_expanded_list[s_src] = md_filelist[s_src]
            
    i_len = len(d_expanded_list.keys())
    # copy all of the files to the destination volume.
    # alert the user if anything goes wrong.
    try:
        for i_count, source_file in enumerate(d_expanded_list.keys(), start=1):
            progress_bar.setMessage("Copying: %s"%os.path.basename(source_file))
            if not os.path.exists(os.path.dirname(d_expanded_list[source_file])):
                os.makedirs(os.path.dirname(d_expanded_list[source_file]))
            shutil.copy(source_file, d_expanded_list[source_file])
            f_progress = float(i_count)/float(i_len)
            progress_bar.setProgress(50 + int(f_progress * 50))
    except:
#         e_type = sys.exc_info()[0]
#         e_msg = sys.exc_info()[1]
#         e_traceback = sys.exc_info()[2]
        nuke.critical(traceback.format_exc())
    else:
        progress_bar.setProgress(100)
        progress_bar.setMessage("Done!")

    del progress_bar

def get_cc_file_for_shot(m_shot):
    cc_file = None
    g_ih_show_code = os.environ['IH_SHOW_CODE']
    g_ih_show_root = os.environ['IH_SHOW_ROOT']
    g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
    config = ConfigParser.ConfigParser()
    config.read(g_ih_show_cfg_path)
    g_main_plate = config.get(g_ih_show_code, 'main_plate')
    g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp')
    g_seq_regexp = config.get(g_ih_show_code, 'sequence_regexp')
    g_shot_dir = config.get(g_ih_show_code, 'shot_dir')
    g_plates_dir = config.get(g_ih_show_code, "plates_dir")
    matchobject = re.search(g_shot_regexp, m_shot)
    # make sure this file matches the shot pattern
    if not matchobject:
        return cc_file
    else:
        shot = matchobject.group(0)
        seq = re.search(g_seq_regexp, shot).group(0)

    subbed_shot_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)
    shot_dir = subbed_shot_dir
    plates_dir = os.path.join(shot_dir, g_plates_dir)
    mp_dir = None
    for t_plate in glob.glob("%s%s%s*"%(plates_dir, os.path.sep, shot)):
        if t_plate.find(g_main_plate) > -1:
            mp_dir = t_plate
    if mp_dir:
        plate_basename = os.path.basename(mp_dir)
        cc_file = os.path.join(mp_dir, "_Metadata", "%s.cc"%plate_basename)
        if os.path.exists(cc_file):
            print "INFO: Found CC file: %s"%cc_file
        else:
            print "INFO: Unable to find CC file at %s."%cc_file
            cc_file = None
    else:
        print "INFO: Shot doesn't have any main plate directory in %s."%plates_dir
    return cc_file

def send_for_review_skyscraper(cc=True, current_version_notes=None, b_method_avidqt=True, b_method_vfxqt=True, b_method_exr=False, b_method_matte=False):
    oglist = []


    for nd in nuke.selectedNodes():
        nd.knob('selected').setValue(False)
        oglist.append(nd)

    start_frame = nuke.root().knob('first_frame').value()
    end_frame = nuke.root().knob('last_frame').value()

    for und in oglist:
        created_list = []
        write_list = []
        render_path = ""
        md_host_name = None
        first_frame_tc_str = ""
        last_frame_tc_str = ""
        first_frame_tc = None
        last_frame_tc = None
        slate_frame_tc = None

        if und.Class() == "Read":
            print "INFO: Located Read Node."
            und.knob('selected').setValue(True)
            render_path = und.knob('file').value()
            start_frame = und.knob('first').value()
            end_frame = und.knob('last').value()
            md_host_name = und.metadata('exr/nuke/input/hostname')
            startNode = und
        elif und.Class() == "Write":
            print "INFO: Located Write Node."
            und.knob('selected').setValue(True)
            new_read = read_from_write()
            render_path = new_read.knob('file').value()
            start_frame = new_read.knob('first').value()
            end_frame = new_read.knob('last').value()
            md_host_name = new_read.metadata('exr/nuke/input/hostname')
            created_list.append(new_read)
            startNode = new_read
        else:
            print "Please select either a Read or Write node"
            break
        if sys.platform == "win32":
            if "/Volumes/raid_vol01" in render_path:
                render_path = render_path.replace("/Volumes/raid_vol01", "Y:")
        # un-comment to use timecode information from metadata
        first_frame_tc_str = startNode.metadata("input/timecode", float(start_frame))
        last_frame_tc_str = startNode.metadata("input/timecode", float(end_frame))
        # un-comment to use timecode from start frame (1001 = 00:00:41:17) and end frame
        # first_frame_tc_str = str(TimeCode(start_frame))
        # last_frame_tc_str = str(TimeCode(end_frame))
        if first_frame_tc_str == None:
            first_frame_tc = TimeCode(start_frame)
        else:
            first_frame_tc = TimeCode(first_frame_tc_str)
        slate_frame_tc = first_frame_tc - 1
        if last_frame_tc_str == None:
            last_frame_tc = TimeCode(end_frame) + 1
        else:
            last_frame_tc = TimeCode(last_frame_tc_str) + 1

        # create the panel to ask for notes
        def_note_text = "For review"
        path_dir_name = os.path.dirname(os.path.dirname(render_path))
        version_int = int(path_dir_name.split("_v")[-1])
        if version_int == 801:
            def_note_text = "Scan Verification."

        b_execute_overall = False
        cc_delivery = False

        if current_version_notes is not None:
            cvn_txt = current_version_notes
            avidqt_delivery = b_method_avidqt
            vfxqt_delivery = b_method_vfxqt
            exr_delivery = b_method_exr
            matte_delivery = b_method_matte
            cc_delivery = cc
            b_execute_overall = True
        else:
            pnl = SkyscraperNotesPanel()
            pnl.knobs()['cvn_'].setValue(def_note_text)
            if pnl.showModalDialog():
                cvn_txt = pnl.knobs()['cvn_'].value()
                cc_delivery = pnl.knobs()['cc_'].value()
                avidqt_delivery = pnl.knobs()['avidqt_'].value()
                vfxqt_delivery = pnl.knobs()['vfxqt_'].value()
                exr_delivery = pnl.knobs()['exr_'].value()
                matte_delivery = pnl.knobs()['matte_'].value()
                b_execute_overall = True

        if b_execute_overall:
        
            # pull some things out of the show config file
            s_show_root = os.environ['IH_SHOW_ROOT']
            s_show = os.environ['IH_SHOW_CODE']
            config = ConfigParser.ConfigParser()
            config.read(os.environ['IH_SHOW_CFG_PATH'])
            if sys.platform == "win32":
                s_delivery_folder = config.get(s_show, 'delivery_folder_win32')
            else:
                s_delivery_folder = config.get(s_show, 'delivery_folder')
            # delivery template
            s_delivery_template = os.path.join(s_show_root, 'SHARED', 'lib', 'nuke', 'delivery', config.get(s_show, 'delivery_template'))
            s_filename = os.path.basename(render_path).split('.')[0]
            s_shot = s_filename.split('_')[0]
            s_sequence = s_shot[0:3]
            # allow version number to have arbitrary text after it, such as "_matte" or "_temp"
            s_version = s_filename.split('_v')[-1].split('_')[0]
            s_artist_name = "%s"%user_full_name()
            s_format = config.get(s_show, 'delivery_resolution')
            
            # notes
            l_notes = ["", "", "", "", ""]
            for idx, s_note in enumerate(cvn_txt.split('\n'), start=0):
                if idx >= len(l_notes):
                    break
                l_notes[idx] = s_note
                
            s_delivery_package_full = ""
            if exr_delivery: 
                s_delivery_package_full = get_delivery_directory_skyscraper(s_delivery_folder)
            else:
                s_delivery_package_full = get_delivery_directory_skyscraper(s_delivery_folder, b_istemp=True)
            
            s_delivery_package = os.path.split(s_delivery_package_full)[-1]
            s_seq_path = os.path.join(s_show_root, s_sequence)
            s_shot_path = os.path.join(s_seq_path, s_shot)
            
            d_files_to_copy = {}
            b_deliver_cdl = True
            
            # comp render dir
            comp_render_dir = os.path.sep.join(render_path.split(os.path.sep)[0:-2])
            
            s_avidqt_src = os.path.join(comp_render_dir, "1920x1080_QuicktimeDNxHD115", "%s.mov"%s_filename)
            s_vfxqt_src = os.path.join(comp_render_dir, "1920x1080_QuicktimeH264", "%s.m4v"%s_filename)
            s_exr_src = os.path.join(os.path.dirname(render_path), "%s.*.exr"%s_filename)
            s_matte_src = os.path.join(os.path.dirname(render_path), "%s_matte.*.tif"%s_filename)
            s_xml_src = '.'.join([os.path.splitext(render_path)[0].split('.')[0], "xml"])
            
            # copy CDL file into destination folder
            # requested by production on 11/01/2016
            s_cdl_src = get_cc_file_for_shot(s_shot)
            if not s_cdl_src:
                print "WARNING: get_cc_file_for_shot() returned NoneType. Unable to find .CC file."
                b_deliver_cdl = False
                cc_delivery = False
            if not os.path.exists(s_cdl_src):
                print "WARNING: Unable to locate CC file at: %s"%s_cdl_src
                cc_delivery = False
                b_deliver_cdl = False
            
            # open up the cdl and extract the cccid
            if cc_delivery:
                cdltext = open(s_cdl_src, 'r').read()
                cccid_re_str = r'<ColorCorrection id="([A-Za-z0-9-_]+)">'
                cccid_re = re.compile(cccid_re_str)
                cccid_match = cccid_re.search(cdltext)
                if cccid_match:
                    s_cccid = cccid_match.group(1)
                else:
                    s_cccid = os.path.basename(s_cdl_src).split('.')[0]
            
                # slope
                slope_re_str = r'<Slope>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Slope>'
                slope_re = re.compile(slope_re_str)
                slope_match = slope_re.search(cdltext)
                slope_r = slope_match.group(1)
                slope_g = slope_match.group(2)
                slope_b = slope_match.group(3)

                # offset
                offset_re_str = r'<Offset>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Offset>'
                offset_re = re.compile(offset_re_str)
                offset_match = offset_re.search(cdltext)
                offset_r = offset_match.group(1)
                offset_g = offset_match.group(2)
                offset_b = offset_match.group(3)
            
                # power
                power_re_str = r'<Power>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Power>'
                power_re = re.compile(power_re_str)
                power_match = power_re.search(cdltext)
                power_r = power_match.group(1)
                power_g = power_match.group(2)
                power_b = power_match.group(3)
            
                # saturation
                saturation_re_str = r'<Saturation>([0-9.-]+)</Saturation>'
                saturation_re = re.compile(saturation_re_str)
                saturation_match = saturation_re.search(cdltext)
                saturation = saturation_match.group(1)
            
            s_avidqt_dest = os.path.join(s_delivery_package_full, s_filename, "1920x1080_QuicktimeDNxHD115", "%s.mov"%s_filename)
            s_vfxqt_dest = os.path.join(s_delivery_package_full, s_filename, "1920x1080_QuicktimeH264", "%s.m4v"%s_filename)
            s_exr_dest = os.path.join(s_delivery_package_full, s_filename, "2880x2160_EXR-ZIP")
            s_matte_dest = os.path.join(s_delivery_package_full, s_filename, "2880x2160_TIFF")
            # copy CDL file into destination folder
            # requested by production on 11/01/2016
            s_cdl_dest = os.path.join(s_exr_dest, "%s.cdl"%s_shot)
            s_xml_dest = os.path.join(s_delivery_package_full, ".delivery", "%s.xml"%s_filename)
            
            # print out python script to a temp file
            fh_nukepy, s_nukepy = tempfile.mkstemp(suffix='.py')
            
            os.write(fh_nukepy, "#!/usr/bin/python\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "import nuke\n")
            os.write(fh_nukepy, "import os\n")
            os.write(fh_nukepy, "import sys\n")
            os.write(fh_nukepy, "import traceback\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "nuke.scriptOpen(\"%s\")\n"%s_delivery_template)
            os.write(fh_nukepy, "nd_root = root = nuke.root()\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "# set root frame range\n")
            os.write(fh_nukepy, "nd_root.knob('first_frame').setValue(%d)\n"%start_frame)
            os.write(fh_nukepy, "nd_root.knob('last_frame').setValue(%d)\n"%end_frame)
            
            # allow user to disable color correction, usually for temps
            if not cc_delivery:
                os.write(fh_nukepy, "nd_root.knob('nocc').setValue(True)\n")
            
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "nd_read = nuke.toNode('EXR_READ')\n")
            os.write(fh_nukepy, "nd_read.knob('file').setValue(\"%s\")\n"%render_path)
            os.write(fh_nukepy, "nd_read.knob('first').setValue(%d)\n"%start_frame)
            os.write(fh_nukepy, "nd_read.knob('last').setValue(%d)\n"%end_frame)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_file_name').setValue(\"%s\")\n"%s_filename)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_sequence').setValue(\"%s\")\n"%s_sequence)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_shot').setValue(\"%s\")\n"%s_shot)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_version').setValue(\"%s\")\n"%s_version)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_vendor').setValue(\"%s\")\n"%s_artist_name)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_format').setValue(\"%s\")\n"%s_format)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_1').setValue(\"%s\")\n"%l_notes[0])
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_2').setValue(\"%s\")\n"%l_notes[1])
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_3').setValue(\"%s\")\n"%l_notes[2])
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_4').setValue(\"%s\")\n"%l_notes[3])
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_5').setValue(\"%s\")\n"%l_notes[4])
            os.write(fh_nukepy, "nd_root.knob('ti_ih_delivery_folder').setValue(\"%s\")\n"%s_delivery_folder)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_delivery_package').setValue(\"%s\")\n"%s_delivery_package)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_show').setValue(\"%s\")\n"%s_show)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_show_path').setValue(\"%s\")\n"%s_show_root)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_seq').setValue(\"%s\")\n"%s_sequence)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_seq_path').setValue(\"%s\")\n"%s_seq_path)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_shot').setValue(\"%s\")\n"%s_shot)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_shot_path').setValue(\"%s\")\n"%s_shot_path)

            if not cc_delivery:
                os.write(fh_nukepy, "nuke.toNode('Colorspace1').knob('disable').setValue(True)\n")
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('disable').setValue(True)\n")
                os.write(fh_nukepy, "nuke.toNode('Vectorfield3').knob('disable').setValue(True)\n")
                os.write(fh_nukepy, "nuke.toNode('Colorspace3').knob('disable').setValue(True)\n")
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('disable').setValue(True)\n")
                os.write(fh_nukepy, "nuke.toNode('Vectorfield1').knob('disable').setValue(True)\n")
            else:
                # hard code cdl values because fuck nuke
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('file').setValue(\"%s\")\n"%s_cdl_src)
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('cccid').setValue(\"%s\")\n"%s_cccid)
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('read_from_file').setValue(False)\n")
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('slope').setValue([%s, %s, %s])\n"%(slope_r, slope_g, slope_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('offset').setValue([%s, %s, %s])\n"%(offset_r, offset_g, offset_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('power').setValue([%s, %s, %s])\n"%(power_r, power_g, power_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform1').knob('saturation').setValue(%s)\n"%saturation)

                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('file').setValue(\"%s\")\n"%s_cdl_src)
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('cccid').setValue(\"%s\")\n"%s_cccid)
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('read_from_file').setValue(False)\n")
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('slope').setValue([%s, %s, %s])\n"%(slope_r, slope_g, slope_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('offset').setValue([%s, %s, %s])\n"%(offset_r, offset_g, offset_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('power').setValue([%s, %s, %s])\n"%(power_r, power_g, power_b))
                os.write(fh_nukepy, "nuke.toNode('OCIOCDLTransform2').knob('saturation').setValue(%s)\n"%saturation)
            
            l_exec_nodes = []
            
            if not avidqt_delivery:
                os.write(fh_nukepy, "nuke.toNode('MOV_DNXHD_WRITE').knob('disable').setValue(True)\n")
            else:
                d_files_to_copy[s_avidqt_src] = s_avidqt_dest
                l_exec_nodes.append('MOV_DNXHD_WRITE')
            
            if not vfxqt_delivery:
                os.write(fh_nukepy, "nuke.toNode('MOV_H264_WRITE').knob('disable').setValue(True)\n")
            else:
                d_files_to_copy[s_vfxqt_src] = s_vfxqt_dest
                l_exec_nodes.append('MOV_H264_WRITE')
            
            if not exr_delivery:
                os.write(fh_nukepy, "nuke.toNode('EXR_WRITE').knob('disable').setValue(True)\n")
                b_deliver_cdl = False
            else:
                d_files_to_copy[s_exr_src] = s_exr_dest
                l_exec_nodes.append('EXR_WRITE')

            if not matte_delivery:
                os.write(fh_nukepy, "nuke.toNode('TIFF_MATTE_WRITE').knob('disable').setValue(True)\n")
            else:
                d_files_to_copy[s_matte_src] = s_matte_dest
                l_exec_nodes.append('TIFF_MATTE_WRITE')
            
            s_exec_nodes = (', '.join('nuke.toNode("' + write_node + '")' for write_node in l_exec_nodes))
            os.write(fh_nukepy, "print \"INFO: About to execute render...\"\n")
            os.write(fh_nukepy, "try:\n")
            if len(l_exec_nodes) == 1:
                os.write(fh_nukepy, "    nuke.execute(nuke.toNode(\"%s\"),%d,%d,1,)\n"%(l_exec_nodes[0], start_frame - 1, end_frame))
            else:
                os.write(fh_nukepy, "    nuke.executeMultiple((%s),((%d,%d,1),))\n"%(s_exec_nodes, start_frame - 1, end_frame))
            os.write(fh_nukepy, "except:\n")
            os.write(fh_nukepy, "    print \"ERROR: Exception caught!\\n%s\"%traceback.format_exc()\n")
            os.close(fh_nukepy)

            # generate the xml file
            new_submission = etree.Element('DailiesSubmission')
            sht_se = etree.SubElement(new_submission, 'Shot')
            sht_se.text = s_shot

            if avidqt_delivery:
                fname_se = etree.SubElement(new_submission, 'AvidQTFileName')
                fname_se.text = os.path.basename(s_avidqt_src)
            if vfxqt_delivery:
                vfxname_se = etree.SubElement(new_submission, 'VFXQTFileName')
                vfxname_se.text = os.path.basename(s_vfxqt_src)
            if exr_delivery:
                exr_fname_se = etree.SubElement(new_submission, 'EXRFileName')
                exr_fname_se.text = os.path.basename(s_exr_src)
            if matte_delivery:
                matte_fname_se = etree.SubElement(new_submission, 'MatteFileName')
                matte_fname_se.text = os.path.basename(s_matte_src)
            sframe_se = etree.SubElement(new_submission, 'StartFrame')
            sframe_se.text = "%d" % (start_frame - 1)
            eframe_se = etree.SubElement(new_submission, 'EndFrame')
            eframe_se.text = "%d" % end_frame
            stc_se = etree.SubElement(new_submission, 'StartTimeCode')
            stc_se.text = "%s" % slate_frame_tc
            etc_se = etree.SubElement(new_submission, 'EndTimeCode')
            etc_se.text = "%s" % last_frame_tc
            artist_se = etree.SubElement(new_submission, 'Artist')
            artist_se.text = s_artist_name
            notes_se = etree.SubElement(new_submission, 'SubmissionNotes')
            notes_se.text = cvn_txt

            # write out xml file to disk

            prettyxml = minidom.parseString(etree.tostring(new_submission)).toprettyxml(indent="  ")
            xml_ds = open(s_xml_src, 'w')
            xml_ds.write(prettyxml)
            xml_ds.close()

            d_files_to_copy[s_xml_src] = s_xml_dest
            
            # copy CDL file if we are delivering EXR frames
            if b_deliver_cdl:
                d_files_to_copy[s_cdl_src] = s_cdl_dest

            # render all frames - in a background thread
            # print s_nukepy
            threading.Thread(target=render_delivery_threaded, args=[s_nukepy, start_frame, end_frame, d_files_to_copy]).start()

        for all_nd in nuke.allNodes():
            if all_nd in oglist:
                all_nd.knob('selected').setValue(True)
            else:
                all_nd.knob('selected').setValue(False)

def create_viewer_input():
    for n in nuke.selectedNodes():
        n['selected'].setValue(False)

    grp = nuke.createNode("Group", inpanel=False)
    grp.begin()
    inp = nuke.createNode("Input", inpanel=False)
    cdl = nuke.createNode("OCIOCDLTransform", inpanel=False)
    cdl['read_from_file'].setValue(True)
    cdl['working_space'].setValue("ACES - ACEScct")
    lut = nuke.createNode("OCIOFileTransform", inpanel=False)
    lut['working_space'].setValue("ACES - ACEScct")
    out = nuke.createNode("Output", inpanel=False)
    # set file paths
    cdlfile = None
    lutfile = None
    shot = None
    try:
        shot = nuke.root().knob('txt_ih_shot').value()
        ccfile = os.path.join("%s"%nuke.root().knob('txt_ih_shot_path').value(), "elements", "%s_plt001_v001"%shot, "_Metadata", "%s_plt001_v001.cc"%shot)
        lutfile = os.environ['IH_SHOW_CFG_LUT']
        cdl['file'].setValue(ccfile)
        lut['file'].setValue(lutfile)
    except:
        print "Caught exception when trying to set .cc and .csp file paths"
    grp.end()
    grp.setName("VIEWER_INPUT")
    nuke.activeViewer().node().knob('viewerProcess').setValue('Rec.709 (ACES)')

def img_seq_builder(m_srcpath, g_dict_img_seq, g_shot_regexp, g_imgseq_regexp):
    file_basename = os.path.basename(m_srcpath)
    shot = None
    seq = None
    file_array = file_basename.split('.')

    matchobject = re.search(g_shot_regexp, file_basename)
    # make sure this file matches the shot pattern
    if not matchobject:
        return
    else:
        shot = matchobject.groupdict()['shot']
        seq = matchobject.groupdict()['sequence']

    subbed_shot_dir = os.path.sep.join(m_srcpath.split(os.path.sep)[0:-4])

    # only deal with EXR files for now
    if file_array[-1] == 'exr':
        dest_dir = os.path.dirname(m_srcpath)
        dest_file = m_srcpath
        
        # part of an image sequence?
        matchobject = re.search(g_imgseq_regexp, dest_file)
        if matchobject:
            img_seq_gd = matchobject.groupdict()
            if not g_dict_img_seq.get(subbed_shot_dir):
                g_dict_img_seq[subbed_shot_dir] = { img_seq_gd['base'] : { 'frames' : [img_seq_gd['frame']], 'ext' : img_seq_gd['ext']} }
            else:
                if not g_dict_img_seq[subbed_shot_dir].get(img_seq_gd['base']):
                    g_dict_img_seq[subbed_shot_dir][img_seq_gd['base']] = { 'frames' : [img_seq_gd['frame']], 'ext' : img_seq_gd['ext']}
                else:
                    g_dict_img_seq[subbed_shot_dir][img_seq_gd['base']]['frames'].append(img_seq_gd['frame'])

def new_shot():
    g_ih_show_code = None
    g_ih_show_root = None
    g_ih_show_cfg_path = None
    g_shot_regexp = None
    g_seq_regexp = None
    g_shot_dir = None
    g_show_file_operation = None
    g_imgseq_regexp = None
    g_shot_scripts_dir = None
    g_shot_script_start = None
    g_shot_template = None

    try:
        g_ih_show_code = os.environ['IH_SHOW_CODE']
        g_ih_show_root = os.environ['IH_SHOW_ROOT']
        g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
        config = ConfigParser.ConfigParser()
        config.read(g_ih_show_cfg_path)
        g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp')
        g_seq_regexp = config.get(g_ih_show_code, 'sequence_regexp')
        g_shot_dir = config.get(g_ih_show_code, 'shot_dir')
        g_show_file_operation = config.get(g_ih_show_code, 'show_file_operation')
        g_imgseq_regexp = config.get(g_ih_show_code, 'imgseq_regexp')
        g_shot_scripts_dir = config.get(g_ih_show_code, 'shot_scripts_dir')
        g_shot_comp_render_dir = config.get(g_ih_show_code, 'shot_comp_render_dir')
        g_shot_script_start = config.get(g_ih_show_code, 'shot_script_start')
        g_write_extension = config.get(g_ih_show_code, 'write_extension')
        g_write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
        g_write_fps = config.get(g_ih_show_code, 'write_fps')
        g_shot_template = config.get('shot_template', sys.platform)
        print "Successfully loaded show-specific config file for %s."%g_ih_show_code
    except:
        nuke.message("An unknown error has occured while trying to load the show configuration file.")
        return

    # ask the user to pick a shot
    shot_dir = nuke.getFilename("Select a new shot directory:", default=os.path.join(os.environ['IH_SHOW_ROOT'], "shots", ""))
    shot = None
    seq = None
    version = 801
    # do some basic validation to be sure this is a shot directory
    matchobject = re.search(g_shot_regexp, shot_dir)
    # make sure this file matches the shot pattern
    if not matchobject:
        nuke.message("The directory chosen, %s, does not appear to be a shot directory."%shot_dir)
        return
    else:
        shot = matchobject.groupdict()['shot']
        seq = matchobject.groupdict()['sequence']

    subbed_seq_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", '')
    subbed_shot_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)
    shot_dir = subbed_shot_dir

    plates_dir = os.path.join(shot_dir, "elements")
    available_plates = glob.glob(os.path.join(plates_dir, "%s_*"%shot))
    if len(available_plates) == 0:
        nuke.critical("Shot %s does not contain any plates in the elements directory! Exiting."%shot)
        return
        
    print "INFO: Beginning Nuke script process for %s."%shot

    nuke_script_starter = g_shot_script_start.format(**matchobject.groupdict())
    full_nuke_script_path = os.path.join(subbed_shot_dir, g_shot_scripts_dir, "%s.nk"%nuke_script_starter)
    max_version = 801
    if os.path.exists(full_nuke_script_path):
        print "INFO: Nuke script already exists at %s."%full_nuke_script_path
        nuke_scripts = glob.glob(full_nuke_script_path.replace("801", "*"))
        pattern = re.compile("_v([0-9]{3}).nk$")
        for file in nuke_scripts:
            mo = pattern.search(file)
            if mo:
                cver = int(mo.group(1))
                if cver > max_version:
                    max_version = cver
        max_version = max_version + 1
        b_overwrite = nuke.ask("Nuke scripts already exist for this shot, with the highest version being v%d. Would you like to start with v%d?"%(max_version - 1, max_version))
        if not b_overwrite:
            print "INFO: User opted to not make a new version of an existing shot."
            return
    else:
        print "INFO: Creating new Nuke script at %s!"%full_nuke_script_path

    nuke_script_starter = nuke_script_starter.replace("801", "%d"%max_version)
    full_nuke_script_path = full_nuke_script_path.replace("801", "%d"%max_version)
    
    comp_render_dir_dict = { 'pathsep' : os.path.sep, 'compdir' : nuke_script_starter }
    comp_write_path = os.path.join(shot_dir, g_shot_comp_render_dir.format(**comp_render_dir_dict), "%s.%s.%s"%(nuke_script_starter, g_write_frame_format, g_write_extension))
    
    # convert all of the CDL files first.
    main_plate = None
    main_cc_file = None
    for plate in available_plates:
        plate_base = os.path.basename(plate)
        cc_file_candidate = os.path.join(plate, "_Metadata", "%s.cc"%plate_base)
        # make the .cc file if it can't be found
        if not os.path.exists(cc_file_candidate):
            cdl_convert.reset_all()
            ccc = cdl_convert.parse_cdl(os.path.join(plate, "_Metadata", "%s.cdl"%plate_base))
            cc = ccc.color_decisions[0].cc
            cc.id=plate_base
            cc.determine_dest('cc',os.path.join(plate, "_Metadata"))
            cdl_convert.write_cc(cc)
        if plate.find("plt001") > -1:
            main_plate = plate_base
            main_cc_file = cc_file_candidate
    
    # retrieve the image sequences from the plates directory
    g_dict_img_seq = {}
    
    for dirname, subdirlist, filelist in os.walk(plates_dir):
        for fname in filelist:
            img_seq_builder(os.path.join(dirname, fname), g_dict_img_seq, g_shot_regexp, g_imgseq_regexp)

    nuke.scriptOpen(g_shot_template)
    bd_node = nuke.toNode("BackdropNode1")
    bd_node_w = nuke.toNode("BackdropNode2")
    main_read = nuke.toNode("Read1")
    main_write = nuke.toNode("Write_exr")
    main_cdl = nuke.toNode("VIEWER_INPUT.OCIOCDLTransform1")
    plates = g_dict_img_seq[shot_dir].keys()
    # handle the main plate
    mainplate_dict = None
    mainplate_name = None
    for t_plate in plates:
        if t_plate.find("_plt001_") > -1:
            mainplate_dict = g_dict_img_seq[shot_dir][t_plate]
            mainplate_name = t_plate
            plates.remove(t_plate)
            
    mainplate_ext = mainplate_dict['ext']
    mainplate_frames = sorted(mainplate_dict['frames'])
    # these scans appear to have a slate frame... yuck.
    mainplate_first = int(mainplate_frames[0])
    if mainplate_first == 1000:
        mainplate_first = 1001
    mainplate_last = int(mainplate_frames[-1])

    # set the values in the template
    bd_node.knob('label').setValue("<center>%s"%os.path.basename(mainplate_name))
    main_read.knob('file').setValue("%s.%s.%s"%(mainplate_name, g_write_frame_format, mainplate_ext))
    main_read.knob('first').setValue(mainplate_first)
    main_read.knob('last').setValue(mainplate_last)
    main_read.knob('origfirst').setValue(mainplate_first)
    main_read.knob('origlast').setValue(mainplate_last)
    nuke.root().knob('first_frame').setValue(mainplate_first)
    nuke.root().knob('last_frame').setValue(mainplate_last)
    nuke.root().knob('txt_ih_show').setValue(g_ih_show_code)
    nuke.root().knob('txt_ih_show_path').setValue(g_ih_show_root)
    nuke.root().knob('txt_ih_seq').setValue(seq)
    nuke.root().knob('txt_ih_seq_path').setValue(subbed_seq_dir)
    nuke.root().knob('txt_ih_shot').setValue(shot)
    nuke.root().knob('txt_ih_shot_path').setValue(subbed_shot_dir)
    main_cdl.knob('file').setValue(main_cc_file)
    main_write.knob('file').setValue(comp_write_path)
    bd_node_w.knob('label').setValue("<center>%s\ncomp output"%shot)
    
    # set the format of the script based on the main plate
    # requested by Holly 12/12/17
    read_node = main_read
    read_fmt = read_node.format()
    format_name = read_fmt.name()
    if not format_name:
        read_fmt.setName("%s Format"%read_node.name())
        format_name = read_fmt.name()
        format_string = "{wide} {high} 0 0 {wide} {high} {pixelaspect} {name}"
        format_dict = {}
        format_dict['wide'] = read_fmt.width()
        format_dict['high'] = read_fmt.height()
        format_dict['pixelaspect'] = read_fmt.pixelAspect()
        format_dict['name'] = read_fmt.name()
        str_fmt_rep = format_string.format(**format_dict)
        nuke.addFormat(str_fmt_rep)

    root = nuke.root()
    root['format'].setValue(format_name)

    # bring in any additional plates
    if len(plates) > 0:
        last_read = main_read
        last_read_xpos = 1292
        last_bd_xpos = 1096
        # last_sr_xpos = 1292
        last_bd = bd_node
        for addlplate in plates:
            newplate_dict = g_dict_img_seq[shot_dir][addlplate]
            newplate_ext = newplate_dict['ext']
            newplate_frames = sorted(newplate_dict['frames'])
            newplate_first = int(newplate_frames[0])
            newplate_last = int(newplate_frames[-1])
            # copy/paste read and backdrop
            new_read = nuke.createNode("Read")
            new_bd = nuke.createNode("BackdropNode")
            # new_sr = nuke.createNode("Sky_Reformat")
            # new_sr.connectInput(0, new_read)
            
            new_bd.knob('note_font_size').setValue(42)
            new_bd.knob('bdwidth').setValue(473)
            new_bd.knob('bdheight').setValue(364)
        
        
            new_bd_xpos = last_bd_xpos + 500
            new_read_xpos = last_read_xpos + 500
            # new_sr_xpos = last_sr_xpos + 500
            
            new_bd.knob('xpos').setValue(new_bd_xpos)
            new_bd.knob('ypos').setValue(-775)
            new_read.knob('xpos').setValue(new_read_xpos)
            new_read.knob('ypos').setValue(-687)
            # new_sr.knob('xpos').setValue(new_sr_xpos)
            # new_sr.knob('ypos').setValue(-509)
            
            newplate_dict = g_dict_img_seq[shot_dir][addlplate]
            newplate_ext = newplate_dict['ext']
            newplate_frames = sorted(newplate_dict['frames'])
            newplate_first = int(newplate_frames[0])
            newplate_last = int(newplate_frames[-1])
        
            new_bd.knob('label').setValue("<center>%s"%os.path.basename(addlplate))
            new_read.knob('file').setValue("%s.%s.%s"%(addlplate, g_write_frame_format, newplate_ext))
            new_read.knob('first').setValue(newplate_first)
            new_read.knob('last').setValue(newplate_last)
            new_read.knob('origfirst').setValue(newplate_first)
            new_read.knob('origlast').setValue(newplate_last)
        
            last_read = new_read
            last_read_xpos = new_read_xpos
            last_bd = new_bd
            last_bd_xpos = new_bd_xpos
            # last_sr_xpos = new_sr_xpos
        
    # that should do it!
    nuke.scriptSaveAs(full_nuke_script_path)
    print "INFO: Successfully wrote out Nuke script at %s!"%full_nuke_script_path
    