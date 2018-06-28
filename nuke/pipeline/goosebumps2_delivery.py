#!/usr/bin/python

# designed to receive a directory path from stdin, and create a conflagration-specific
# delivery package. reads all of the XML files within a directory, creates a CSV, and an
# ALE. Prints the name of the delivery file to stdout.

import sys
import os
import glob
import xml.etree.ElementTree as ET
import pprint
import datetime
import csv
import copy
import shutil
import ConfigParser
import db_access as DB
import subprocess

ihdb = DB.DBAccessGlobals.get_db_access()

# gmail authentication
if not sys.platform == 'win32':
    import httplib2
    import oauth2client
    from oauth2client import client, tools
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from apiclient import errors, discovery
    import mimetypes
    from email.mime.image import MIMEImage
    from email.mime.audio import MIMEAudio
    from email.mime.base import MIMEBase

g_delivery_folder = None
DISTRO_LIST_TO = None
DISTRO_LIST_CC = None
MAIL_FROM = None
g_mail_from_address = None
g_write_ale = False
g_show_code = ""
g_shared_root = ""
g_credentials_dir = ""
g_client_secret = ""
g_gmail_creds = ""
g_gmail_scopes = ""
g_application_name = ""
g_shot_count = 0
g_email_text = ""
g_rsync_enabled = False
g_rsync_filetypes = []
g_rsync_dest = ""

try:
    g_show_code = os.environ['IH_SHOW_CODE']
    config = ConfigParser.ConfigParser()
    config.read(os.environ['IH_SHOW_CFG_PATH'])
    if sys.platform == "win32":
        g_delivery_folder = config.get(g_show_code, 'delivery_folder_win32')
    else:
        g_delivery_folder = config.get(g_show_code, 'delivery_folder')
    DISTRO_LIST_TO = config.get('email', 'distro_list_to')
    DISTRO_LIST_CC = config.get('email', 'distro_list_cc')
    MAIL_FROM = config.get('email', 'mail_from')
    if config.get(g_show_code, 'write_ale') == 'yes':
        g_write_ale = True
    
    g_shared_root = config.get('shared_root', sys.platform)
    credentials_dir_dict = { 'pathsep' : os.path.sep, 'shared_root' : g_shared_root }
    g_credentials_dir = config.get('email', 'credentials_dir').format(**credentials_dir_dict)
    g_client_secret = config.get('email', 'client_secret')
    g_gmail_creds = config.get('email', 'gmail_creds')
    g_gmail_scopes = config.get('email', 'gmail_scopes')
    g_application_name = config.get('email', 'application_name')
    g_email_text = config.get('email', 'email_text')
    g_rsync_enabled = True if config.get(g_show_code, 'delivery_rsync_enabled') == 'yes' else False
    g_rsync_filetypes = config.get(g_show_code, 'delivery_rsync_filetypes').split(',')
    g_rsync_dest = config.get(g_show_code, 'delivery_rsync_dest')
except:
    print "UNEXPECTED ERROR"
    print sys.exc_info()[0]
    print sys.exc_info()[1]
    raise
   
def handle_rsync(m_source_folder):
    rsync_cmd = ['rsync',
                 '-auv',
                 '--prune-empty-dirs',
                 '--include="*/"']
    for valid_ext in g_rsync_filetypes:
        rsync_cmd.append('--include="*.%s"'%valid_ext)
    rsync_cmd.append('--exclude="*"')    
    rsync_cmd.append(m_source_folder.rstrip('/'))
    rsync_cmd.append(g_rsync_dest)
    print "INFO: Executing command: %s"%" ".join(rsync_cmd)
    subprocess.Popen(" ".join(rsync_cmd), shell=True)
            
def get_credentials():
    if not os.path.exists(g_credentials_dir):
        print "WARNING: Credentials directory in config file %s does not exist. Creating."%g_credentials_dir
        os.makedirs(g_credentials_dir)
    credential_path = os.path.join(g_credentials_dir, g_gmail_creds)
    print "INFO: Searching for credential: %s"%credential_path
    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(g_client_secret, g_gmail_scopes)
        flow.user_agent = g_application_name
        credentials = tools.run_flow(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

def SendMessage(sender, to, cc, subject, msgHtml, msgPlain, attachmentFile=None):
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('gmail', 'v1', http=http)
    if attachmentFile:
        message1 = createMessageWithAttachment(sender, to, cc, subject, msgHtml, msgPlain, attachmentFile)
    else: 
        message1 = CreateMessageHtml(sender, to, cc, subject, msgHtml, msgPlain)
    result = SendMessageInternal(service, "me", message1)
    return result

def SendMessageInternal(service, user_id, message):
    try:
        message = (service.users().messages().send(userId=user_id, body=message).execute())
        print('Message Id: %s' % message['id'])
        return message
    except errors.HttpError as error:
        print('An error occurred: %s' % error)
        return "Error"
    return "OK"

def CreateMessageHtml(sender, to, cc, subject, msgHtml, msgPlain):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    msg['Cc'] = cc
    msg.attach(MIMEText(msgPlain, 'plain'))
    msg.attach(MIMEText(msgHtml, 'html'))
    return {'raw': base64.urlsafe_b64encode(msg.as_string())}

def createMessageWithAttachment(
    sender, to, cc, subject, msgHtml, msgPlain, attachmentFile):
    """Create a message for an email.

    Args:
      sender: Email address of the sender.
      to: Email address of the receiver.
      subject: The subject of the email message.
      msgHtml: Html message to be sent
      msgPlain: Alternative plain text message for older email clients          
      attachmentFile: The path to the file to be attached.

    Returns:
      An object containing a base64url encoded email object.
    """
    message = MIMEMultipart()
    message['to'] = to
    message['cc'] = cc
    message['from'] = sender
    message['subject'] = subject

    print "Email Message: %s"%msgPlain
    message.attach(MIMEText(msgPlain))

    print("create_message_with_attachment: file: %s" % attachmentFile)
    content_type, encoding = mimetypes.guess_type(attachmentFile)

    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    if main_type == 'text':
        fp = open(attachmentFile, 'rb')
        msg = MIMEText(fp.read(), _subtype=sub_type)
        fp.close()
    elif main_type == 'image':
        fp = open(attachmentFile, 'rb')
        msg = MIMEImage(fp.read(), _subtype=sub_type)
        fp.close()
    elif main_type == 'audio':
        fp = open(attachmentFile, 'rb')
        msg = MIMEAudio(fp.read(), _subtype=sub_type)
        fp.close()
    else:
        fp = open(attachmentFile, 'rb')
        msg = MIMEBase(main_type, sub_type)
        msg.set_payload(fp.read())
        fp.close()
    filename = os.path.basename(attachmentFile)
    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg)

    return {'raw': base64.urlsafe_b64encode(message.as_string())}

class ALEWriter():

    ale_fh = None
    header_list = None
    tape_name = "INHOUSE_AVID"

    def __init__(self, input_filehandle):
        self.ale_fh = input_filehandle

    # takes an array containing the names of the column headings.
    # example: column_header_list = ['Name', 'Tracks', 'Start', 'End', 'Tape', 'ASC_SOP', 'ASC_SAT', 'frame_range']
    # write_header(column_header_list)
    def write_header(self, column_headers):
        self.header_list = column_headers
        header_string = '\t'.join(self.header_list)
        ale_header = """Heading
FIELD_DELIM	TABS
VIDEO_FORMAT	1080
TAPE	%s
FPS	23.976

Column
%s

Data
"""%(self.tape_name, header_string)
        self.ale_fh.write(ale_header)
        return

    # takes an array of arrays. the master array contains a list of arrays, which represent individual rows in
    # the table. the individual rows contain values that match the headers provided to the write_header method.
    
    def set_tape_name(self, m_tape_name):
        self.tape_name = m_tape_name
        
    def write_data(self, row_data_list):
        for row in row_data_list:
            row_match_list = []
            for col_hdr in self.header_list:
                row_match_list.append(row[col_hdr])
            self.ale_fh.write('\t'.join(row_match_list))
            self.ale_fh.write('\n')
        return

##USES GLOBALS FROM TOP
def send_email(delivery_directory, file_list, shot_count):

    formatted_list= "\n".join(file_list)

    final_destination_dir = os.path.join(g_rsync_dest, os.path.split(delivery_directory)[-1])
    	
    d_email_text = {'shot_count' : shot_count, 'delivery_folder' : final_destination_dir, 'shot_list' : formatted_list}
    msg = g_email_text.format(**d_email_text).replace('\\r', '\r')
    csvfiles = glob.glob(os.path.join(delivery_directory, '*.csv'))
    s_subject = "In-House Submission: %s"%os.path.split(delivery_directory)[-1]
    # print csvfiles[0]
    
    if len(csvfiles) > 0:
        SendMessage(MAIL_FROM, DISTRO_LIST_TO, DISTRO_LIST_CC, s_subject, msg, msg, csvfiles[0])
    else:
        SendMessage(MAIL_FROM, DISTRO_LIST_TO, DISTRO_LIST_CC, s_subject, msg, msg)
        
    return msg


def deliver(f):

    if f == None:
        return "User Cancelled Operation"
    delivery_path = f.rstrip()
    if delivery_path[-1]=="/":
        delivery_path=delivery_path[:-1]
    email_list=[]
    shot_count = 0
    if os.path.exists(delivery_path):
        delivery_directory = os.path.split(delivery_path)[-1]
        xmlfile_list = glob.glob(os.path.join(delivery_path, ".delivery", "*.xml"))
        shot_count = len(xmlfile_list)
        headers = ['FACILITY', 'BATCH ID', 'SUBMISSION DATE', 'VFX NUMBER', 'FILENAME', 'VERSION', 'FACILITY NOTES', 'SUBMITTED FOR', 'FILE TYPE', 'START FRAME', 'END FRAME', 'FRAMES']
        rows = []
        ale_rows = []
        dbversions = []
        for xmlfile in sorted(xmlfile_list):
            isdpx = False
            ismatte = False
            dpxfilename = ""
            exrfilename = ""
            rowdict = {}
            mattedict = {}
            exrdict = {}
            ale_row_single = {}
            shot = ""
            start = ""
            end = ""
            xml_base = os.path.basename(xmlfile).split('.')[0]
            tree = ET.parse(xmlfile)
            root = tree.getroot()
            rowdict['BATCH ID'] = delivery_directory.split('_')[-1]
            rowdict['SUBMISSION DATE'] = datetime.date.today().strftime('%m/%d/%y')
            rowdict['FACILITY'] = 'IHT'
            if xmlfile.find("_pkg") != -1:
                rowdict['SUBMITTED FOR'] = 'Archive'
                for child in root:
                    if child.tag == 'Shot':
                        nukescript = child.text
                        rowdict['FILENAME'] = nukescript
                        rowdict['VFX NUMBER'] = nukescript.split("_")[0]
                        email_list.append(os.path.join(delivery_path, "%s"%rowdict['FILENAME']))
                rowdict['FACILITY NOTES'] = ""
                rows.append(rowdict)
            else:
                rowdict['SUBMITTED FOR'] = 'Temp'
                ale_row_single['Tracks'] = 'V'
                for child in root:
                    if child.tag == 'Shot':
                        shot = child.text
                        rowdict['VFX NUMBER'] = shot
                        # fetch an object from the database for this version
                        dbshot = ihdb.fetch_shot(shot)
                        dbversion = ihdb.fetch_version(xml_base, dbshot)
                        if dbversion:
                            print "Located version %s in database with id %d."%(xml_base, dbversion.g_dbid)
                            dbversions.append(dbversion)
                        else:
                            print "ERROR: Unable to locate version in database with name %s!"%xml_base
                    elif child.tag == 'AvidQTFileName':
                        rowdict['VERSION'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        rowdict['FILENAME'] = "%s_v%s.mov"%(shot, rowdict['VERSION'])
                        rowdict['FILE TYPE'] = 'MOV'
                        email_list.append(rowdict['FILENAME'])
                        ale_row_single['Name'] = child.text
                        ale_row_single['Tape'] = os.path.splitext(child.text)[0]
                        if 'matte' in child.text:
                            ismatte=True
                    elif child.tag == 'DPXFileName':
                        rowdict['SUBMITTED FOR'] = 'Final'
                        rowdict['VERSION'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        dpxfilename = "%s_v%s.dpx"%(shot, rowdict['VERSION'])
                        # email_list.append(dpxfilename)
                        isdpx = True
                    elif child.tag == 'MatteFileName':
                        rowdict['VERSION'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        mattefilename = "%s_v%s_matte.tif"%(shot, rowdict['VERSION'])
                        # email_list.append(mattefilename)
                        if not rowdict['SUBMITTED FOR'] == 'Final':
                           rowdict['SUBMITTED FOR'] = 'DI Matte'
                        ismatte = True
                    elif child.tag == 'StartTimeCode':
                        ale_row_single['Start'] = child.text
                    elif child.tag == 'EndTimeCode':
                        ale_row_single['End'] = child.text
                    elif child.tag == 'StartFrame':
                        start = child.text
                    elif child.tag == 'EndFrame':
                        end = child.text
                    elif child.tag == 'SubmissionNotes':
                        rowdict['FACILITY NOTES'] = child.text
                rowdict['START FRAME'] = start
                rowdict['END FRAME'] = end
                rowdict['FRAMES'] = int(end) - int(start) + 1
                if isdpx:
                    dpxdict = copy.deepcopy(rowdict)
                    dpxdict['FILENAME'] = dpxfilename
                    dpxdict['FILE TYPE'] = 'DPX'
                    # rows.append(dpxdict)
                if ismatte:
                    mattedict = copy.deepcopy(rowdict)
                    mattedict['FILENAME']= mattefilename
                    mattedict['FILE TYPE'] = 'TIF'
                    # rows.append(mattedict)

                rows.append(rowdict)
                ale_row_single['frame_range'] = "%s-%s"%(start, end)
                sequence = shot[0:2]
                slope = ["1.0","1.0","1.0"]
                offset = ["0.0","0.0","0.0"]
                power = ["1.0","1.0","1.0"]
                saturation = "1.0"
                first_cdl_path = os.path.join(os.environ['IH_SHOW_ROOT'], sequence, shot, "data", "cdl", "%s.cc"%shot)
                second_cdl_path = os.path.join(os.environ['IH_SHOW_ROOT'], sequence, shot, "data", "cdl", "%s.cc"%shot)
                cdl_path = ""
                if os.path.exists(first_cdl_path):
                    # print "os.path.exists(%s) returns true."%first_cdl_path
                    cdl_path = first_cdl_path
                else:
                    cdl_path = second_cdl_path
                if os.path.exists(cdl_path):
                    print "Reading SOP and SAT values from: %s"%cdl_path
                    try:
                        cdltree = ET.parse(cdl_path)
                    except:
                        raise
                        # nuke.critical("Malformed XML in .CC file %s"%cdl_path)
                        return
                    cdlroot = cdltree.getroot()
                    for cdlchild in cdlroot:
                        if cdlchild.tag == 'SOPNode':
                            for sopchild in cdlchild:
                                if sopchild.tag == 'Slope':
                                    slope = sopchild.text.split()
                                elif sopchild.tag == 'Offset':
                                    offset = sopchild.text.split()
                                elif sopchild.tag == 'Power':
                                    power = sopchild.text.split()
                        elif cdlchild.tag == 'SatNode':
                            for satchild in cdlchild:
                                if satchild.tag == 'Saturation':
                                    saturation = satchild.text.strip()
                asc_sop_concat = "(%s)(%s)(%s)"%(' '.join(slope), ' '.join(offset), ' '.join(power))
                ale_row_single['ASC_SOP'] = asc_sop_concat
                ale_row_single['ASC_SAT'] = str(saturation)
                ale_rows.append(ale_row_single)



        csvfile_path = os.path.join(delivery_path, "%s.csv"%delivery_directory)
        csvfile_fh = open(csvfile_path, 'w')
        csvfile_dw = csv.DictWriter(csvfile_fh, headers)
        csvfile_dw.writeheader()
        csvfile_dw.writerows(rows)
        csvfile_fh.close()        
        
        if g_write_ale:
            alefile_path = os.path.join(delivery_path, "%s.ale"%delivery_directory)
            alefile_fh = open(alefile_path, 'w')
            alefile_w = ALEWriter(alefile_fh)
            alefile_w.set_tape_name(delivery_directory)
            alefile_w.write_header(['Name', 'Tracks', 'Start', 'End', 'Tape', 'ASC_SOP', 'ASC_SAT', 'frame_range'])
            alefile_w.write_data(ale_rows)
            alefile_fh.close()
        
        # create a playlist in the database based on this submission
        dbplaylist = ihdb.fetch_playlist(delivery_directory)
        if not dbplaylist:
            dbplaylist = DB.Playlist(delivery_directory, [], -1)
        dbplaylist.g_playlist_versions = dbversions
        ihdb.create_playlist(dbplaylist)
        print "Created playlist %s in database."%(delivery_directory)
        handle_rsync(delivery_path)
        return send_email(delivery_path,email_list,shot_count)

# if not sys.platform == "linux2":
#     import Tkinter as tk
#     import tkFileDialog
# 
# 
# 
if __name__ == "__main__":
    if len(sys.argv) >= 2:
        file_path = sys.argv[1]
        if os.path.exists(file_path) and os.path.isdir(file_path):
            print "Executing from command line! Using directory: %s"%file_path
            print deliver(file_path)
