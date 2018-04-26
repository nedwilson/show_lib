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
import db_access as DB
import sgtk

class SpinelNotesPanel(nukescripts.PythonPanel):
    def __init__(self):
        nukescripts.PythonPanel.__init__(self, 'Spinel Review Submission')
        self.cvn_knob = nuke.Multiline_Eval_String_Knob('cvn_', 'current version notes', 'For review')
        self.addKnob(self.cvn_knob)
        self.cc_knob = nuke.Boolean_Knob('cc_', 'CC', True)
        self.cc_knob.setFlag(nuke.STARTLINE)
        self.addKnob(self.cc_knob)
        self.avidqt_knob = nuke.Boolean_Knob('avidqt_', 'Avid QT', True)
        self.addKnob(self.avidqt_knob)
        # self.vfxqt_knob = nuke.Boolean_Knob('vfxqt_', 'VFX QT', False)
        # self.addKnob(self.vfxqt_knob)
        self.burnin_knob = nuke.Boolean_Knob('burnin_', 'QT Burnin', True)
        self.addKnob(self.burnin_knob)
        self.exr_knob = nuke.Boolean_Knob('exr_', 'EXR', True)
        self.exr_knob.setFlag(nuke.STARTLINE)
        self.addKnob(self.exr_knob)
        self.matte_knob = nuke.Boolean_Knob('matte_', 'Matte', False)
        self.addKnob(self.matte_knob)
        self.export_knob = nuke.Boolean_Knob('export_', 'Export', False)
        self.addKnob(self.export_knob)

def get_delivery_directory_spinel(str_path, b_istemp=False):
    delivery_folder = str_path
    # s_folder_contents = "EXR"
    # if b_istemp:
    #     s_folder_contents = "MOV"
    tday = datetime.date.today().strftime('%Y%m%d')
    matching_folders = glob.glob(os.path.join(delivery_folder, "INH_%s_*"%(tday)))
    noxl = ""
    max_dir = 0
    if len(matching_folders) == 0:
        calc_folder = os.path.join(delivery_folder, "INH_%s_01"%(tday))
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

def render_delivery_threaded(ms_python_script, d_db_thread_helper, start_frame, end_frame, md_filelist):
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
                progress_bar.setProgress(int(f_progress * 98))
        except IOError:
            print "ERROR: IOError Caught!"
            var = traceback.format_exc()
            print var
    if proc.returncode != 0:
        s_errmsg = ""
        s_err = '\n'.join(s_err_ar)
        l_err_verbose = []
        b_intrace = False
        for err_line in s_err_ar:
            if len(err_line) == 0:
                b_intrace = False
                continue
            if err_line.find("Traceback") != -1:
                b_intrace = True
            if err_line.find("ERROR") != -1:
                b_intrace = True
            if b_intrace:
                l_err_verbose.append(err_line)
        if s_err.find("FOUNDRY LICENSE ERROR REPORT") != -1:
            s_errmsg = "Unable to obtain a license for Nuke! Package execution fails, will not proceed!"
        else:
            s_errmsg = "Error(s) have occurred. Details:\n%s"%'\n'.join(l_err_verbose)
        nuke.critical(s_errmsg)
    else:
        print "INFO: Successfully completed delivery render."

    mov_file = d_db_thread_helper['mov_src']
    thumb_file = d_db_thread_helper['exr_src'].replace('*', '%04d'%int(((int(end_frame) - int(start_frame))/2) + int(start_frame)))
    src_imgseq_path = d_db_thread_helper['exr_src'].replace('*', '%04d')
            
    # copy the files
    d_expanded_list = {}
    for s_src in md_filelist:
        if s_src.find('*') != -1:
            src_imgseq_path = s_src.replace('*', '%04d')
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
            progress_bar.setProgress(98 + int(f_progress * 98))
    except:
        nuke.critical(traceback.format_exc())
    else:
        # add a new version to the database
        progress_bar.setProgress(99)
        progress_bar.setMessage("Creating new Version record in the database...")
        
        # initialize the DB connection
        sgdb = DB.DBAccessGlobals.get_db_access()
        
        # fetch the shot
        print "Thread: %s Fetching shot from database for %s"%(threading.current_thread().getName(), d_db_thread_helper['shot'])
        dbshot = sgdb.fetch_shot(d_db_thread_helper['shot'])
        
        # fetch the artist
        print "Thread: %s Fetching artist from database for %s"%(threading.current_thread().getName(), user_full_name())
        dbartist = sgdb.fetch_artist(user_full_name())
        
        # fetch a list of tasks for the shot
        dbtasks = sgdb.fetch_tasks_for_shot(dbshot)
        # To-do: add task creation functionality here
        # For now, just use tasks[0]
        dbtask = DB.Task("Blank Task", dbartist, 'wtg', dbshot, -1)
        if len(dbtasks) > 0:
            dbtask = dbtasks[0]
        
        # create a thumbnail
        thumb_file_gen = create_thumbnail(thumb_file)
        
        # does the version already exist?
        print "Thread: %s Fetching version for %s, for shot %s"%(threading.current_thread().getName(), os.path.basename(thumb_file).split('.')[0], d_db_thread_helper['shot'])
        dbversion = sgdb.fetch_version(os.path.basename(thumb_file).split('.')[0], dbshot)
        
        # clean up notes
        l_notes = d_db_thread_helper['notes']
        clean_notes = []
        for l_note in l_notes:
            if len(l_note) > 0:
                clean_notes.append(l_note)
        if not dbversion:
            dbversion = DB.Version(os.path.basename(thumb_file).split('.')[0], 
                                     -1, 
                                     '\n'.join(clean_notes), 
                                     int(start_frame), 
                                     int(end_frame), 
                                     int(end_frame) - int(start_frame) + 1, 
                                     src_imgseq_path, 
                                     mov_file,
                                     dbshot,
                                     dbartist,
                                     dbtask)
            sgdb.create_version(dbversion)
        sgdb.upload_thumbnail('Version', dbversion, thumb_file_gen)
        sgdb.upload_thumbnail('Shot', dbshot, thumb_file_gen)
        dbtask.g_status = 'rev'
        sgdb.update_task_status(dbtask)
        print "Successfully created version %s in database with DBID %d."%(dbversion.g_version_code, int(dbversion.g_dbid))
        progress_bar.setMessage("Publishing Nuke Script and EXR Frames to Shotgun...")
        # set shotgun authentication
        auth_user = sgtk.get_authenticated_user()
        if auth_user == None:
            sa = sgtk.authentication.ShotgunAuthenticator()
            user = sa.create_script_user(api_script='spinel_api_access', api_key='0554a1b0a4251fc84e14b78028666c4485aa873bc671246b28a914552aec1032', host='https://qppe.shotgunstudio.com')
            sgtk.set_authenticated_user(user)
        
        # retrieve Shotgun Toolkit object
        tk = sgtk.sgtk_from_entity('Task', int(dbtask.g_dbid))
        # grab context for published version
        context = tk.context_from_entity('Task', int(dbtask.g_dbid))
        sg_publish_name = os.path.basename(thumb_file).split('.')[0].split('_v')[0]
        sg_publish_ver = int(os.path.basename(thumb_file).split('.')[0].split('_v')[1])
        dbpublishexr = sgtk.util.register_publish(tk, context, src_imgseq_path, sg_publish_name, sg_publish_ver, comment = '\n'.join(clean_notes), published_file_type = 'EXR Image Sequence')
        sgdb.upload_thumbnail('PublishedFile', dbtask, thumb_file_gen, altid = dbpublishexr['id'])
        dbpublishnk = sgtk.util.register_publish(tk, context, nuke.root().name(), sg_publish_name, sg_publish_ver, comment = '\n'.join(clean_notes), published_file_type = 'Nuke Script')
        sgdb.upload_thumbnail('PublishedFile', dbtask, thumb_file_gen, altid = dbpublishnk['id'])
        progress_bar.setProgress(100)
        progress_bar.setMessage("Done!")

    del progress_bar

def send_for_review_spinel(cc=True, current_version_notes=None, b_method_avidqt=True, b_method_burnin=True, b_method_exr=True, b_method_matte=False, b_method_artist=None):
    oglist = []
    vfxqt_delivery = False

    for nd in nuke.selectedNodes():
        nd.knob('selected').setValue(False)
        oglist.append(nd)

    start_frame = nuke.root().knob('first_frame').value()
    end_frame = nuke.root().knob('last_frame').value()
    
    global_width = nuke.root().knob('format').value().width()
    global_height = nuke.root().knob('format').value().height()

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
            global_width = und.knob('format').value().width()
            global_height = und.knob('format').value().height()
            md_host_name = und.metadata('exr/nuke/input/hostname')
            startNode = und
        elif und.Class() == "Write":
            print "INFO: Located Write Node."
            und.knob('selected').setValue(True)
            global_width = und.knob('format').value().width()
            global_height = und.knob('format').value().height()
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
        path_dir_name = os.path.dirname(render_path)
        version_int = int(path_dir_name.split("_v")[-1])
        if version_int == 1:
            def_note_text = "Scan Verification."

        b_execute_overall = False
        cc_delivery = False
        burnin_delivery = False
        export_delivery = False

        if current_version_notes is not None:
            cvn_txt = current_version_notes
            avidqt_delivery = b_method_avidqt
            burnin_delivery = b_method_burnin
            exr_delivery = b_method_exr
            matte_delivery = b_method_matte
            cc_delivery = cc
            b_execute_overall = True
        else:
            pnl = SpinelNotesPanel()
            pnl.knobs()['cvn_'].setValue(def_note_text)
            if pnl.showModalDialog():
                cvn_txt = pnl.knobs()['cvn_'].value()
                cc_delivery = pnl.knobs()['cc_'].value()
                avidqt_delivery = pnl.knobs()['avidqt_'].value()
                burnin_delivery = pnl.knobs()['burnin_'].value()
                exr_delivery = pnl.knobs()['exr_'].value()
                matte_delivery = pnl.knobs()['matte_'].value()
                export_delivery = pnl.knobs()['export_'].value()
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
                
            # project FPS
            s_project_fps = config.get(s_show, 'write_fps')
            # delivery template
            s_delivery_template = os.path.join(s_show_root, 'SHARED', 'lib', 'nuke', 'delivery', config.get(s_show, 'delivery_template'))
            s_filename = os.path.basename(render_path).split('.')[0]
            s_shot = "%s_%s"%(s_filename.split('_')[0],s_filename.split('_')[1])
            s_sequence = s_shot[0:5]
            # allow version number to have arbitrary text after it, such as "_matte" or "_temp"
            s_version = s_filename.split('_v')[-1].split('_')[0]
            s_artist_name = None
            if b_method_artist == None:
                s_artist_name = "%s"%user_full_name()
            else:
                s_artist_name = b_method_artist
            # this will vary based on camera format, so, pull the default from the config file, and then try and get the right one from the read node
            s_format = config.get(s_show, 'delivery_resolution')
            tmp_width = startNode.knob('format').value().width()
            tmp_height = startNode.knob('format').value().height()
            s_format = "%sx%s"%(tmp_width, tmp_height)
            
            # notes
            l_notes = ["", "", "", "", ""]
            for idx, s_note in enumerate(cvn_txt.split('\n'), start=0):
                if idx >= len(l_notes):
                    break
                l_notes[idx] = s_note
                
            s_delivery_package_full = ""
            if exr_delivery: 
                s_delivery_package_full = get_delivery_directory_spinel(s_delivery_folder)
            else:
                s_delivery_package_full = get_delivery_directory_spinel(s_delivery_folder, b_istemp=True)
            
            s_delivery_package = os.path.split(s_delivery_package_full)[-1]
            s_seq_path = os.path.join(s_show_root, s_sequence)
            s_shot_path = os.path.join(s_seq_path, s_shot)
            
            d_files_to_copy = {}
            b_deliver_cdl = True
            
            s_avidqt_src = '.'.join([os.path.splitext(render_path)[0].split('.')[0], "mov"])
            s_vfxqt_src = '.'.join(["%s_h264"%os.path.splitext(render_path)[0].split('.')[0], "mov"])
            s_exr_src = os.path.join(os.path.dirname(render_path), "%s.*.exr"%s_filename)
            s_matte_src = os.path.join(os.path.dirname(render_path), "%s_matte.*.tif"%s_filename)
            s_xml_src = '.'.join([os.path.splitext(render_path)[0].split('.')[0], "xml"])
            
            d_db_thread_helper = {}
            d_db_thread_helper['exr_src'] = s_exr_src
            d_db_thread_helper['mov_src'] = s_avidqt_src
            d_db_thread_helper['shot'] = s_shot
            d_db_thread_helper['notes'] = l_notes
                        
            # copy CDL file into destination folder
            # requested by production on 11/01/2016
            s_cdl_src = os.path.join(s_shot_path, "data", "cdl", "%s.ccc"%s_shot)
            if not os.path.exists(s_cdl_src):
                print "WARNING: Unable to locate CCC file at: %s"%s_cdl_src
                b_deliver_cdl = False
            
            # open up the cdl and extract the cccid
            cdltext = open(s_cdl_src, 'r').read()
            cccid_re_str = r'<ColorCorrection id="([A-Za-z0-9-_]+)">'
            cccid_re = re.compile(cccid_re_str)
            cccid_match = cccid_re.search(cdltext)
            s_cccid = cccid_match.group(1)
            
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

            
            s_avidqt_dest = os.path.join(s_delivery_package_full, "AVID", "%s.mov"%s_filename)
            s_vfxqt_dest = os.path.join(s_delivery_package_full, "VFX", "%s_h264.mov"%s_filename)
            s_exr_dest = os.path.join(s_delivery_package_full, s_filename, s_format)
            s_matte_dest = os.path.join(s_delivery_package_full, "%s_matte"%s_filename, s_format)
            # copy CDL file into destination folder
            # requested by production on 11/01/2016
            s_cdl_dest = os.path.join(s_delivery_package_full, "support_files", "%s.ccc"%s_shot)
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
            
            # set the format in both the read node and the project settings
            fstring = '%d %d Submission Format'%(tmp_width, tmp_height)
            os.write(fh_nukepy, "fobj = nuke.addFormat('%s')\n"%fstring)
            os.write(fh_nukepy, "nuke.root().knob('format').setValue(fobj)\n")
            os.write(fh_nukepy, "nuke.root().knob('format').setValue(fobj)\n")

            # allow user to disable color correction, usually for temps
            if not cc_delivery:
                os.write(fh_nukepy, "nd_root.knob('nocc').setValue(True)\n")
            
            os.write(fh_nukepy, "\n")
            os.write(fh_nukepy, "nd_read = nuke.toNode('EXR_READ')\n")
            os.write(fh_nukepy, "nd_read.knob('file').setValue(\"%s\")\n"%render_path)
            os.write(fh_nukepy, "nd_read.knob('first').setValue(%d)\n"%start_frame)
            os.write(fh_nukepy, "nd_read.knob('last').setValue(%d)\n"%end_frame)
            os.write(fh_nukepy, "nd_read.knob('format').setValue(fobj)\n")

            os.write(fh_nukepy, "nd_root.knob('ti_ih_file_name').setValue(\"%s\")\n"%s_filename)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_sequence').setValue(\"%s\")\n"%s_sequence)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_shot').setValue(\"%s\")\n"%s_shot)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_version').setValue(\"%s\")\n"%s_version)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_vendor').setValue(\"%s\")\n"%s_artist_name)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_format').setValue(\"%s\")\n"%s_format)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_1').setValue(\"%s\")\n"%l_notes[0].replace(r'"', r'\"'))
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_2').setValue(\"%s\")\n"%l_notes[1].replace(r'"', r'\"'))
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_3').setValue(\"%s\")\n"%l_notes[2].replace(r'"', r'\"'))
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_4').setValue(\"%s\")\n"%l_notes[3].replace(r'"', r'\"'))
            os.write(fh_nukepy, "nd_root.knob('ti_ih_notes_5').setValue(\"%s\")\n"%l_notes[4].replace(r'"', r'\"'))
            os.write(fh_nukepy, "nd_root.knob('ti_ih_delivery_folder').setValue(\"%s\")\n"%s_delivery_folder)
            os.write(fh_nukepy, "nd_root.knob('ti_ih_delivery_package').setValue(\"%s\")\n"%s_delivery_package)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_show').setValue(\"%s\")\n"%s_show)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_show_path').setValue(\"%s\")\n"%s_show_root)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_seq').setValue(\"%s\")\n"%s_sequence)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_seq_path').setValue(\"%s\")\n"%s_seq_path)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_shot').setValue(\"%s\")\n"%s_shot)
            os.write(fh_nukepy, "nd_root.knob('txt_ih_shot_path').setValue(\"%s\")\n"%s_shot_path)
            # encode with plate timecode
            os.write(fh_nukepy, "nuke.toNode('AddTimeCode1').knob('startcode').setValue(\"%s\")\n"%first_frame_tc_str)
            os.write(fh_nukepy, "nuke.toNode('AddTimeCode1').knob('frame').setValue(%s)\n"%start_frame)
            os.write(fh_nukepy, "nuke.toNode('AddTimeCode1').knob('fps').setValue(%s)\n"%s_project_fps)

            if not burnin_delivery:
                os.write(fh_nukepy, "nd_root.knob('noburnin').setValue(True)\n")

            if export_delivery:
                os.write(fh_nukepy, "nd_root.knob('exportburnin').setValue(True)\n")

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
            s_exr_node = None
            
            if not avidqt_delivery:
                os.write(fh_nukepy, "nuke.toNode('MOV_DNXHD_WRITE').knob('disable').setValue(True)\n")
            else:
                # d_files_to_copy[s_avidqt_src] = s_avidqt_dest
                l_exec_nodes.append('MOV_DNXHD_WRITE')
            
            if not vfxqt_delivery:
                os.write(fh_nukepy, "nuke.toNode('MOV_H264_WRITE').knob('disable').setValue(True)\n")
            else:
                # d_files_to_copy[s_vfxqt_src] = s_vfxqt_dest
                l_exec_nodes.append('MOV_H264_WRITE')

            if not export_delivery:
                os.write(fh_nukepy, "nuke.toNode('MOV_DNXHD_EXPORT_WRITE').knob('disable').setValue(True)\n")
            else:
                # d_files_to_copy[s_vfxqt_src] = s_vfxqt_dest
                l_exec_nodes.append('MOV_DNXHD_EXPORT_WRITE')
            
            if not exr_delivery:
                os.write(fh_nukepy, "nuke.toNode('EXR_WRITE').knob('disable').setValue(True)\n")
                b_deliver_cdl = False
            else:
                # d_files_to_copy[s_exr_src] = s_exr_dest
                l_exec_nodes.append('EXR_WRITE')
                # s_exr_node = 'EXR_WRITE'

            if not matte_delivery:
                os.write(fh_nukepy, "nuke.toNode('TIFF_MATTE_WRITE').knob('disable').setValue(True)\n")
            else:
                # d_files_to_copy[s_matte_src] = s_matte_dest
                l_exec_nodes.append('TIFF_MATTE_WRITE')
            
            s_exec_nodes = (', '.join('nuke.toNode("' + write_node + '")' for write_node in l_exec_nodes))
            os.write(fh_nukepy, "print \"INFO: About to execute render...\"\n")
            os.write(fh_nukepy, "try:\n")
            # if s_exr_node:
            #     os.write(fh_nukepy, "    nuke.execute(nuke.toNode(\"%s\"),%d,%d,1,)\n"%(s_exr_node, start_frame - 1, start_frame - 1))
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
            threading.Thread(target=render_delivery_threaded, args=[s_nukepy, d_db_thread_helper, start_frame, end_frame, d_files_to_copy]).start()

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
    cs = nuke.createNode("OCIOColorSpace", inpanel=False)
    cs['out_colorspace'].setValue("AlexaV3LogC")
    cdl = nuke.createNode("OCIOCDLTransform", inpanel=False)
    cdl['read_from_file'].setValue(True)
    lut = nuke.createNode("OCIOFileTransform", inpanel=False)
    out = nuke.createNode("Output", inpanel=False)
    # set file paths
    cdlfile = None
    lutfile = None
    try:
        cdlfile = os.path.join("%s"%nuke.root().knob('txt_ih_shot_path').value(), "data", "cdl", "%s.ccc"%nuke.root().knob('txt_ih_shot').value())
        lutfile = os.environ['IH_SHOW_CFG_LUT']
        cdl['file'].setValue(cdlfile)
        lut['file'].setValue(lutfile)
    except:
        print "Caught exception when trying to set .ccc and .cube file paths"
    grp.end()
    grp.setName("VIEWER_INPUT")
    nuke.activeViewer().node().knob('viewerProcess').setValue('None')