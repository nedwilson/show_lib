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
import smtplib
import ConfigParser

# mime/multipart stuff
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.utils import COMMASPACE, formatdate

g_delivery_folder = None
DISTRO_LIST_TO = None
DISTRO_LIST_CC = None
MAIL_FROM = None
g_mail_from_address = None
g_mail_username = None
g_mail_password = None
g_mail_smtp_server = None

try:
    config = ConfigParser.ConfigParser()
    config.read(os.environ['IH_SHOW_CFG_PATH'])
    if sys.platform == "win32":
        g_delivery_folder = config.get('darktower', 'delivery_folder_win32')
    else:
        g_delivery_folder = config.get('darktower', 'delivery_folder')
    DISTRO_LIST_TO = set(config.get('email', 'distro_list_to').split(', '))
    DISTRO_LIST_CC = set(config.get('email', 'distro_list_cc').split(', '))
    MAIL_FROM = config.get('email', 'mail_from')
    g_mail_from_address = config.get('email', 'mail_from_address')
    g_mail_username = config.get('email', 'mail_username')
    g_mail_password = config.get('email', 'mail_password')
    g_mail_smtp_server = config.get('email', 'mail_smtp_server')
except:
    # Todo: Handle exception
    pass

class ALEWriter():

    ale_fh = None
    header_list = None

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
TAPE	MLIH_AVID
FPS	24

Column
%s

Data
"""%(header_string)
        self.ale_fh.write(ale_header)
        return

    # takes an array of arrays. the master array contains a list of arrays, which represent individual rows in
    # the table. the individual rows contain values that match the headers provided to the write_header method.
    def write_data(self, row_data_list):
        for row in row_data_list:
            row_match_list = []
            for col_hdr in self.header_list:
                row_match_list.append(row[col_hdr])
            self.ale_fh.write('\t'.join(row_match_list))
            self.ale_fh.write('\n')
        return

##USES GLOBALS FROM TOP
def send_email(delivery_directory, file_list):

    formatted_list= "\r\n".join(file_list)

    msg="Hello Diane,\n\
\n\
The following shots are ready in %s:\n\
\n\
%s\n\
\n\
Enjoy!\n\
\n\n" %(delivery_directory, formatted_list)
    print msg
    email = "\r\n".join([
        "From: Dark Tower In House",
        "To: %s" %", ".join(DISTRO_LIST_TO),
        "Cc: %s"%", ".join(DISTRO_LIST_CC),
        "Subject: In House delivery: %s" %os.path.split(delivery_directory)[-1]
        ,
        msg
    ])

    mime_msg = MIMEMultipart()
    mime_msg['from'] = MAIL_FROM
    mime_msg['to'] = COMMASPACE.join(DISTRO_LIST_TO)
    mime_msg['cc'] = COMMASPACE.join(DISTRO_LIST_CC)
    mime_msg['subject'] = "In House delivery: %s" %os.path.split(delivery_directory)[-1]
    mime_msg.attach(MIMEText(msg))
    csvfiles = glob.glob(os.path.join(delivery_directory, '*.csv'))
    for f in csvfiles or []:
        with open(f, "rb") as fil:
            mime_msg.attach(MIMEApplication(
                fil.read(),
                Content_Disposition='attachment; filename="%s"' % os.path.basename(f),
                Name=os.path.basename(f)
            ))

    fromaddr = g_mail_from_address
    toaddrs = DISTRO_LIST_CC.union(DISTRO_LIST_TO)
    # print toaddrs
    # Credentials (if needed)
    username = g_mail_username
    password = g_mail_password

    # The actual mail send
    print g_mail_smtp_server
    server = smtplib.SMTP(g_mail_smtp_server)
    server.starttls()
    server.login(username,password)
    server.sendmail(fromaddr, toaddrs, mime_msg.as_string())
    server.quit()

    return email


def deliver(f):

    delivery_path = f.rstrip()
    if delivery_path[-1]=="/":
        delivery_path=delivery_path[:-1]
    email_list=[]
    if os.path.exists(delivery_path):
        delivery_directory = os.path.split(delivery_path)[-1]
        xmlfile_list = glob.glob(os.path.join(delivery_path, ".delivery", "*.xml"))
        headers = ['Submission', 'Submission Date', 'Vendor', 'Submission Type', 'Asset Name', 'Asset Detail', 'Shot Number', 'Version', 'Filetype', 'Filename', 'FirstFrame', 'LastFrame', 'Submitted For', 'Vendor Comments', 'Client Feedback']
        rows = []
        ale_rows = []
        for xmlfile in sorted(xmlfile_list):
            isdpx = False
            isexr = False
            ismatte = False
            dpxfilename = ""
            exrfilename = ""
            rowdict = {}
            dpxdict = {}
            exrdict = {}
            ale_row_single = {}
            shot = ""
            start = ""
            end = ""
            tree = ET.parse(xmlfile)
            root = tree.getroot()
            rowdict['Submission'] = delivery_directory
            rowdict['Submission Date'] = datetime.date.today().strftime('%m/%d/%Y')
            rowdict['Vendor'] = 'INH'
            rowdict['Submission Type'] = 'SHOT'
            rowdict['Asset Name'] = ''
            rowdict['Asset Detail'] = ''
            if xmlfile.find("_pkg") != -1:
                rowdict['Submitted For'] = 'For Archive'
                for child in root:
                    if child.tag == 'Shot':
                        nukescript = child.text
                        rowdict['Filename'] = nukescript
                        rowdict['Shot Number'] = '_'.join(nukescript.split("_")[0:2])
                        email_list.append(os.path.join(delivery_path, "%s"%rowdict['Filename']))
                rowdict['Vendor Comments'] = ""
                rows.append(rowdict)
            else:
                rowdict['Submitted For'] = 'TEMP'
                ale_row_single['Tracks'] = 'V'
                for child in root:
                    if child.tag == 'Shot':
                        shot = child.text
                        rowdict['Shot Number'] = child.text
                    elif child.tag == 'AvidQTFileName':
                        rowdict['Filename'] = child.text
                        rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        rowdict['Filetype'] = 'MOV'
                        # email_list.append(rowdict['Filename'])
                        ale_row_single['Name'] = child.text
                        ale_row_single['Tape'] = os.path.splitext(child.text)[0]
                        if 'matte' in child.text:
                            ismatte=True
                    elif child.tag == 'DPXFileName':
                        dpxfilename = child.text
                        # email_list.append(dpxfilename)
                        rowdict['Submitted For'] = 'REVIEW'
                        rowdict['Filetype'] = 'DPX'
                        rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        isdpx = True
                    elif child.tag == 'MatteFileName':
                        mattefilename = child.text
                        # email_list.append(dpxfilename)
                        rowdict['Filetype'] = 'TIF'
                        rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        if not rowdict['Submitted For'] == 'REVIEW':
                            rowdict['Submitted For'] = 'MATTE'
                        ismatte = True
#                     elif child.tag == 'EXRFileName':
#                         exrfilename = '.'.join([child.text.split('.')[0], 'exr'])
#                         email_list.append(exrfilename)
#                         rowdict['Version'] = child.text.split('.')[0].split('_')[-1]
#                         isexr = True
                    elif child.tag == 'StartTimeCode':
                        ale_row_single['Start'] = child.text
                    elif child.tag == 'EndTimeCode':
                        ale_row_single['End'] = child.text
                    elif child.tag == 'StartFrame':
                        start = child.text
                        rowdict['FirstFrame'] = start
                    elif child.tag == 'EndFrame':
                        end = child.text
                        rowdict['LastFrame'] = end
                    elif child.tag == 'SubmissionNotes':
                        rowdict['Vendor Comments'] = child.text
#                     elif child.tag == 'Hours':
#                         rowdict['Hours'] = child.text
#                     elif child.tag == 'Artist':
#                         rowdict['Artist'] = child.text
#                 rowdict['Frames'] = int(end) - int(start) + 1
                if isdpx:
                    rowdict['Filename'] = "%s.%s-%s.dpx"%(dpxfilename.split('.')[0], start, end)
                if ismatte:
                    rowdict['Filename'] = "%s.%s-%s.tif"%(mattefilename.split('.')[0], start, end)
#                 if isexr:
#                     exrdict = copy.deepcopy(rowdict)
#                     exrdict['Filename'] = exrfilename
#                     exrdict['Hours']=''
#                     rows.append(exrdict)
                #add _vfx qt to export
#                 if not ismatte:
#                     vfxdict = copy.deepcopy(rowdict)
#                     vfxdict['Filename']= vfxdict['Filename'].replace(".mov","_vfx.mov")
#                     vfxdict['Hours']=''
#                     rows.append(vfxdict)

                rowdict['Client Feedback'] = ''
                email_list.append(rowdict['Filename'])
                rows.append(rowdict)
                ale_row_single['frame_range'] = "%s-%s"%(start, end)
                # Let's try and open the CDL for this shot... hopefully it exists
                # First, let's try Gastown
                sequence = shot[0:2]
                slope = ["1.0","1.0","1.0"]
                offset = ["0.0","0.0","0.0"]
                power = ["1.0","1.0","1.0"]
                saturation = "1.0"
                first_cdl_path = os.path.join(os.environ['IH_SHOW_ROOT'], sequence, shot, "data", "cdl", "%s.cdl"%shot)
                second_cdl_path = os.path.join(os.environ['IH_SHOW_ROOT'], sequence, shot, "data", "cdl", "%s.cdl"%shot)
                cdl_path = ""
                # print first_cdl_path
                if os.path.exists(first_cdl_path):
                    # print "os.path.exists(%s) returns true."%first_cdl_path
                    cdl_path = first_cdl_path
                else:
                    cdl_path = second_cdl_path
                if os.path.exists(cdl_path):
                    print cdl_path
                    cdltree = ET.parse(cdl_path)
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



        csvfile_path = os.path.join(delivery_path, "_TDT_%s.csv"%delivery_directory)
        csvfile_fh = open(csvfile_path, 'w')
        csvfile_dw = csv.DictWriter(csvfile_fh, headers)
        csvfile_dw.writeheader()

        csvfile_dw.writerows(rows)
        csvfile_fh.close()
#         alefile_path = os.path.join(delivery_path, "Monolith_IH_Sub_%s.ale"%delivery_directory)
#         alefile_fh = open(alefile_path, 'w')
#         alefile_w = ALEWriter(alefile_fh)
#         alefile_w.write_header(['Name', 'Tracks', 'Start', 'End', 'Tape', 'ASC_SOP', 'ASC_SAT', 'frame_range'])
#         alefile_w.write_data(ale_rows)
#         alefile_fh.close()
#         hidden_xml_dir = os.path.join(delivery_path, ".delivery")
#         if not os.path.exists(hidden_xml_dir):
#             os.makedirs(hidden_xml_dir)
#         xml_files = glob.glob(os.path.join(delivery_path, '*.xml'))
#         for xml_file in xml_files:
#             shutil.move(xml_file, os.path.join(hidden_xml_dir, os.path.basename(xml_file)))
        return send_email(delivery_path,email_list)


if not sys.platform == "linux2":
    import Tkinter as tk
    import tkFileDialog



    if __name__ == "__main__":
        root = tk.Tk()
        root.withdraw()
        file_path = tkFileDialog.askdirectory()
        if file_path:
            deliver(file_path)
