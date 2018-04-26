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
import db_access as DB

ihdb = DB.DBAccessGlobals.get_db_access()

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
g_write_ale = False

try:
    config = ConfigParser.ConfigParser()
    config.read(os.environ['IH_SHOW_CFG_PATH'])
    if sys.platform == "win32":
        g_delivery_folder = config.get('spinel', 'delivery_folder_win32')
    else:
        g_delivery_folder = config.get('spinel', 'delivery_folder')
    DISTRO_LIST_TO = set(config.get('email', 'distro_list_to').split(', '))
    DISTRO_LIST_CC = set(config.get('email', 'distro_list_cc').split(', '))
    MAIL_FROM = config.get('email', 'mail_from')
    g_mail_from_address = config.get('email', 'mail_from_address')
    g_mail_username = config.get('email', 'mail_username')
    g_mail_password = config.get('email', 'mail_password')
    g_mail_smtp_server = config.get('email', 'mail_smtp_server')
    if config.get('spinel', 'write_ale') == 'yes':
        g_write_ale = True
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
FPS	23.976

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

    msg="Hello Shannon Leigh,\n\
\n\
The following shots are ready in %s:\n\
\n\
%s\n\
\n\
Enjoy!\n\
\n\n" %(delivery_directory, formatted_list)
    email = "\r\n".join([
        "From: Ned Wilson",
        "To: %s" %", ".join(DISTRO_LIST_TO),
        "Cc: %s"%", ".join(DISTRO_LIST_CC),
        "Subject: In-House delivery: %s" %os.path.split(delivery_directory)[-1]
        ,
        msg
    ])

    mime_msg = MIMEMultipart()
    mime_msg['from'] = MAIL_FROM
    mime_msg['to'] = COMMASPACE.join(DISTRO_LIST_TO)
    mime_msg['cc'] = COMMASPACE.join(DISTRO_LIST_CC)
    mime_msg['subject'] = "In-House delivery: %s" %os.path.split(delivery_directory)[-1]
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
#     print g_mail_smtp_server
#     server = smtplib.SMTP(g_mail_smtp_server)
#     server.starttls()
#     server.login(username,password)
#     server.sendmail(fromaddr, toaddrs, mime_msg.as_string())
#     server.quit()

    return email


def deliver(f):

    delivery_path = f.rstrip()
    if delivery_path[-1]=="/":
        delivery_path=delivery_path[:-1]
    email_list=[]
    if os.path.exists(delivery_path):
        delivery_directory = os.path.split(delivery_path)[-1]
        xmlfile_list = glob.glob(os.path.join(delivery_path, ".delivery", "*.xml"))
        # headers = ['Submission', 'Submission Date', 'Vendor', 'Submission Type', 'Asset Name', 'Asset Detail', 'VFX ID', 'Version', 'File Type', 'Filename', 'FirstFrame', 'LastFrame', 'Submitted For', 'Shot Notes', 'Client Feedback']
        headers = ['Submission Date', 'VFX ID', 'Filename', 'File Type', 'Submitted For', 'Shot Notes']
        rows = []
        exr_rows = []
        matte_rows = []
        ale_rows = []
        dbversions = []
        for xmlfile in sorted(xmlfile_list):
            isexr = False
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
            # rowdict['Submission'] = delivery_directory
            rowdict['Submission Date'] = datetime.date.today().strftime('%m/%d/%Y')
            # rowdict['Vendor'] = 'INH'
            # rowdict['Submission Type'] = 'SHOT'
            # rowdict['Asset Name'] = ''
            # rowdict['Asset Detail'] = ''
            if xmlfile.find("_pkg") != -1:
                rowdict['Submitted For'] = 'For Archive'
                for child in root:
                    if child.tag == 'Shot':
                        nukescript = child.text
                        rowdict['Filename'] = nukescript
                        rowdict['VFX ID'] = '_'.join(nukescript.split("_")[0:2])
                        email_list.append(os.path.join(delivery_path, "%s"%rowdict['Filename']))
                rowdict['Shot Notes'] = ""
                rows.append(rowdict)
            else:
                rowdict['Submitted For'] = 'TEMP'
                ale_row_single['Tracks'] = 'V'
                for child in root:
                    if child.tag == 'Shot':
                        shot = child.text
                        rowdict['VFX ID'] = shot
                        # fetch an object from the database for this version
                        dbshot = ihdb.fetch_shot(shot)
                        dbversion = ihdb.fetch_version(xml_base, dbshot)
                        if dbversion:
                            print "Located version %s in database with id %d."%(xml_base, dbversion.g_dbid)
                            dbversions.append(dbversion)
                        else:
                            print "ERROR: Unable to locate version in database with name %s!"%xml_base
                    elif child.tag == 'AvidQTFileName':
                        rowdict['Filename'] = child.text
                        # rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]000
                        rowdict['File Type'] = 'MOV'
                        email_list.append(rowdict['Filename'])
                        ale_row_single['Name'] = child.text
                        ale_row_single['Tape'] = os.path.splitext(child.text)[0]
                        if 'matte' in child.text:
                            ismatte=True
                    elif child.tag == 'EXRFileName':
                        exrfilename = child.text
                        email_list.append(exrfilename)
                        rowdict['Submitted For'] = 'REVIEW'
                        # rowdict['File Type'] = 'EXR'
                        # rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        isexr = True
                    elif child.tag == 'MatteFileName':
                        mattefilename = child.text
                        email_list.append(mattefilename)
                        # rowdict['File Type'] = 'TIF'
                        # rowdict['Version'] = child.text.split('.')[0].split('_v')[-1].split('_')[0]
                        # if not rowdict['Submitted For'] == 'REVIEW':
                        #    rowdict['Submitted For'] = 'MATTE'
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
                        rowdict['Shot Notes'] = child.text
                    # elif child.tag == 'Artist':
                    #     rowdict['Artist'] = child.text
                # rowdict['Frames'] = int(end) - int(start) + 1
                # if isexr:
                #     rowdict['Filename'] = "%s.%s-%s.exr"%(exrfilename.split('.')[0], start, end)
                # if ismatte:
                #     rowdict['Filename'] = "%s.%s-%s.tif"%(mattefilename.split('.')[0], start, end)
                if isexr:
                    exrdict = copy.deepcopy(rowdict)
                    exrdict['Filename'] = exrfilename.replace('*', '%s-%s#'%(start, end))
                    exrdict['File Type'] = 'EXR'
                    exr_rows.append(exrdict)
                if ismatte:
                    mattedict = copy.deepcopy(rowdict)
                    mattedict['Filename']= mattefilename.replace('*', '%s-%s#'%(start, end))
                    mattedict['File Type'] = 'TIF'
                    matte_rows.append(mattedict)

                # email_list.append(rowdict['Filename'])
                rows.append(rowdict)
                ale_row_single['frame_range'] = "%s-%s"%(start, end)
                # Let's try and open the CDL for this shot... hopefully it exists
                # First, let's try Gastown
                sequence = shot[0:5]
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



        csvfile_path = os.path.join(delivery_path, "SPINEL_%s_MOV.csv"%delivery_directory)
        csvfile_fh = open(csvfile_path, 'w')
        csvfile_dw = csv.DictWriter(csvfile_fh, headers)
        csvfile_dw.writeheader()
        csvfile_dw.writerows(rows)
        csvfile_fh.close()

        if len(exr_rows) > 0:
            exrcsvfile_path = os.path.join(delivery_path, "SPINEL_%s_EXR.csv"%delivery_directory)
            exrcsvfile_fh = open(exrcsvfile_path, 'w')
            exrcsvfile_dw = csv.DictWriter(exrcsvfile_fh, headers)
            exrcsvfile_dw.writeheader()
            exrcsvfile_dw.writerows(exr_rows)
            exrcsvfile_fh.close()

        if len(matte_rows) > 0:
            mattecsvfile_path = os.path.join(delivery_path, "SPINEL_%s_MATTE.csv"%delivery_directory)
            mattecsvfile_fh = open(mattecsvfile_path, 'w')
            mattecsvfile_dw = csv.DictWriter(mattecsvfile_fh, headers)
            mattecsvfile_dw.writeheader()
            mattecsvfile_dw.writerows(matte_rows)
            mattecsvfile_fh.close()
        
        
        if g_write_ale:
            alefile_path = os.path.join(delivery_path, "SPINEL_%s.ale"%delivery_directory)
            alefile_fh = open(alefile_path, 'w')
            alefile_w = ALEWriter(alefile_fh)
            alefile_w.write_header(['Name', 'Tracks', 'Start', 'End', 'Tape', 'ASC_SOP', 'ASC_SAT', 'frame_range'])
            alefile_w.write_data(ale_rows)
            alefile_fh.close()
#         hidden_xml_dir = os.path.join(delivery_path, ".delivery")
#         if not os.path.exists(hidden_xml_dir):
#             os.makedirs(hidden_xml_dir)
#         xml_files = glob.glob(os.path.join(delivery_path, '*.xml'))
#         for xml_file in xml_files:
#             shutil.move(xml_file, os.path.join(hidden_xml_dir, os.path.basename(xml_file)))
#        we aren't sending email right now since no internet access.
        
        # create a playlist in the database based on this submission
        dbplaylist = ihdb.fetch_playlist(delivery_directory)
        if not dbplaylist:
            dbplaylist = DB.Playlist(delivery_directory, [], -1)
        dbplaylist.g_playlist_versions = dbversions
        ihdb.create_playlist(dbplaylist)
        print "Created playlist %s in database."%(delivery_directory)
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
