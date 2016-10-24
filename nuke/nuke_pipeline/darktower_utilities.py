#!/usr/bin/python

import nuke
import nukescripts
import os
import sys
from utilities import *
import pwd
import ConfigParser
import tempfile
import threading
import glob
import shutil

class DarkTowerNotesPanel(nukescripts.PythonPanel):
    def __init__(self):
        nukescripts.PythonPanel.__init__(self, 'Dark Tower Review Submission')
        self.cvn_knob = nuke.Multiline_Eval_String_Knob('cvn_', 'current version notes', 'For review')
        self.addKnob(self.cvn_knob)
        self.cc_knob = nuke.Boolean_Knob('cc_', 'CC', True)
        self.cc_knob.setFlag(nuke.STARTLINE)
        self.addKnob(self.cc_knob)
        self.avidqt_knob = nuke.Boolean_Knob('avidqt_', 'Avid QT', True)
        self.addKnob(self.avidqt_knob)
        self.vfxqt_knob = nuke.Boolean_Knob('vfxqt_', 'VFX QT', True)
        self.addKnob(self.vfxqt_knob)
        self.dpx_knob = nuke.Boolean_Knob('dpx_', 'DPX', True)
        self.addKnob(self.dpx_knob)

def get_delivery_directory_darktower(str_path):
    delivery_folder = str_path
    tday = datetime.date.today().strftime('%Y%m%d')
    matching_folders = glob.glob(os.path.join(delivery_folder, "INH_%s_*" % tday))
    noxl = ""
    max_dir = 0
    if len(matching_folders) == 0:
        calc_folder = os.path.join(delivery_folder, "INH_%s_01_DPX" % tday)
    else:
        for suspect_folder in matching_folders:
            csv_spreadsheet = glob.glob(os.path.join(suspect_folder, "*.csv"))
            excel_spreadsheet = glob.glob(os.path.join(suspect_folder, "*.xls*"))
            if len(excel_spreadsheet) == 0 and len(csv_spreadsheet) == 0 and os.path.exists(os.path.join(suspect_folder, ".delivery")):
                noxl = suspect_folder
            else:
                dir_number = int(os.path.basename(suspect_folder).split('_')[-2])
                if dir_number > max_dir:
                    max_dir = dir_number
        if noxl != "":
            calc_folder = noxl
        else:
            calc_folder = os.path.join(delivery_folder, "INH_%s_%02d_DPX" % (tday, max_dir + 1))
    return calc_folder

def render_delivery_threaded(ms_python_script, start_frame, end_frame, md_filelist):
    progress_bar = nuke.ProgressTask("Building Delivery")
    progress_bar.setMessage("Initializing...")
    progress_bar.setProgress(0)

    s_nuke_exe_path = nuke.env['ExecutablePath']  # "/Applications/Nuke9.0v4/Nuke9.0v4.app/Contents/MacOS/Nuke9.0v4"
    s_pyscript = ms_python_script

    s_cmd = "%s -i -V 2 -t %s" % (s_nuke_exe_path, s_pyscript)
    s_err_ar = []
    f_progress = 0.0
    print "INFO: Beginning: %s" % s_cmd
    proc = subprocess.Popen(s_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    while proc.poll() is None:
        try:
            s_out = proc.stdout.readline()
            s_err_ar.append(s_out.rstrip())
            if not s_out.find(".dpx took") == -1:
                s_line_ar = s_out.split(" ")
                s_dpx_frame = s_line_ar[1].split('.')[-2]
                i_dpx_frame = int(s_dpx_frame)
            
                f_duration = float(end_frame - start_frame + 1)
                f_progress = (float(i_dpx_frame) - float(start_frame) + 1.0)/f_duration
                # print "INFO: Rendering: Frame %d"%i_dpx_frame
                progress_bar.setMessage("Rendering: Frame %d" % i_dpx_frame)
                progress_bar.setProgress(int(f_progress * 50))
        except IOError:
            print "ERROR: IOError Caught!"
            var = traceback.format_exc()
            print var
    if proc.returncode != 0:
        s_errmsg = ""
        s_err = '\n'.join(s_err_ar)
        if s_err.find("FOUNDRY LICENSE ERROR REPORT") != -1:
            s_errmsg = "Unable to obtain a license for Nuke! Package execution fails, will not proceed!"
        else:
            s_errmsg = "An unknown error has occurred. Please check the STDERR log above for more information."
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
        e_type = sys.exc_info()[0]
        e_msg = sys.exc_info()[1]
        nuke.critical("An error of type %s has occurred!\nDetails:\n%s"%(e_type, e_msg))
    else:
        progress_bar.setProgress(100)
        progress_bar.setMessage("Done!")

    del progress_bar


def send_for_review_darktower(cc=True, current_version_notes=None, b_method_avidqt=True, b_method_vfxqt=True, b_method_dpx=True):
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
        # no longer uses timecode information from metadata. hardcoded from start frame.
        # first_frame_tc_str = startNode.metadata("input/timecode", float(start_frame))
        # last_frame_tc_str = startNode.metadata("input/timecode", float(end_frame))
        first_frame_tc_str = str(TimeCode(start_frame))
        last_frame_tc_str = str(TimeCode(end_frame))
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
        path_dir_name = os.path.dirname(render_path)
        version_int = int(path_dir_name.split("_v")[-1])
        if version_int == 1:
            def_note_text = "Scan Verification."

        b_execute_overall = False

        if current_version_notes is not None:
            cvn_txt = current_version_notes
            avidqt_delivery = b_method_avidqt
            vfxqt_delivery = b_method_vfxqt
            dpx_delivery = b_method_dpx
            b_execute_overall = True
        else:
            pnl = DarkTowerNotesPanel()
            pnl.knobs()['cvn_'].setValue(def_note_text)
            if pnl.showModalDialog():
                cvn_txt = pnl.knobs()['cvn_'].value()
                cc_delivery = pnl.knobs()['cc_'].value()
                avidqt_delivery = pnl.knobs()['avidqt_'].value()
                vfxqt_delivery = pnl.knobs()['vfxqt_'].value()
                dpx_delivery = pnl.knobs()['dpx_'].value()
                b_execute_overall = True

        if b_execute_overall:
        
            # pull some things out of the show config file
            config = ConfigParser.ConfigParser()
            config.read(os.environ['IH_SHOW_CFG_PATH'])
            if sys.platform == "win32":
                s_delivery_folder = config.get('darktower', 'delivery_folder_win32')
            else:
                s_delivery_folder = config.get('darktower', 'delivery_folder')
            # delivery template
            s_show_root = os.environ['IH_SHOW_ROOT']
            s_show = os.environ['IH_SHOW_CODE']
            s_delivery_template = os.path.join(s_show_root, 'SHARED', 'lib', 'nuke', 'delivery', config.get('darktower', 'delivery_template'))
            s_filename = os.path.basename(render_path).split('.')[0]
            s_shot = s_filename.split('_')[0]
            s_sequence = s_shot[0:2]
            s_version = s_filename.split('_v')[-1]
            s_artist_name = "In House/%s"%user_full_name().split(" ")[0]
            s_format = config.get('darktower', 'delivery_resolution')
            
            # notes
            l_notes = ["", "", "", "", ""]
            for idx, s_note in enumerate(cvn_txt.split('\n'), start=0):
                if idx >= len(l_notes):
                    break
                l_notes[idx] = s_note
                
            s_delivery_package_full = get_delivery_directory_darktower(s_delivery_folder)
            s_delivery_package = os.path.split(s_delivery_package_full)[-1]
            s_seq_path = os.path.join(s_show_root, s_sequence)
            s_shot_path = os.path.join(s_seq_path, s_shot)
            
            d_files_to_copy = {}
            
            s_avidqt_src = '.'.join([os.path.splitext(render_path)[0].split('.')[0], "mov"])
            s_vfxqt_src = '.'.join(["%s_h264"%os.path.splitext(render_path)[0].split('.')[0], "mov"])
            s_dpx_src = os.path.join(os.path.dirname(render_path), "%s.*.dpx"%s_filename)
            s_xml_src = '.'.join([os.path.splitext(render_path)[0].split('.')[0], "xml"])
            
            s_avidqt_dest = os.path.join(s_delivery_package_full, "AVID", "%s.mov"%s_filename)
            s_vfxqt_dest = os.path.join(s_delivery_package_full, "VFX", "%s_h264.mov"%s_filename)
            s_dpx_dest = os.path.join(s_delivery_package_full, "DPX", s_filename, s_format)
            s_xml_dest = os.path.join(s_delivery_package_full, ".delivery", "%s.xml"%s_filename)
            
            # print out python script to a temp file
            fh_nukepy, s_nukepy = tempfile.mkstemp(suffix='.py')
            
            os.write(fh_nukepy, "#!/usr/bin/python\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "import nuke\n")
            os.write(fh_nukepy, "import os\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "nuke.scriptOpen(\"%s\")\n"%s_delivery_template)
            os.write(fh_nukepy, "nd_root = root = nuke.root()\n")
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "# set root frame range\n")
            os.write(fh_nukepy, "nd_root.knob('first_frame').setValue(%d)\n"%start_frame)
            os.write(fh_nukepy, "nd_root.knob('last_frame').setValue(%d)\n"%end_frame)
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
            
            if not dpx_delivery:
                os.write(fh_nukepy, "nuke.toNode('DPX_WRITE').knob('disable').setValue(True)\n")
            else:
                d_files_to_copy[s_dpx_src] = s_dpx_dest
                l_exec_nodes.append('DPX_WRITE')
            
            s_exec_nodes = (', '.join('nuke.toNode("' + write_node + '")' for write_node in l_exec_nodes))
            os.write(fh_nukepy, "nuke.executeMultiple((%s),((%d,%d,1),))\n"%(s_exec_nodes, start_frame - 1, end_frame))
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
            if dpx_delivery:
                dpx_fname_se = etree.SubElement(new_submission, 'DPXFileName')
                dpx_fname_se.text = os.path.basename(s_dpx_src)
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

            # render all frames - in a background thread
            threading.Thread(target=render_delivery_threaded, args=[s_nukepy, start_frame, end_frame, d_files_to_copy]).start()

        for all_nd in nuke.allNodes():
            if all_nd in oglist:
                all_nd.knob('selected').setValue(True)
            else:
                all_nd.knob('selected').setValue(False)
