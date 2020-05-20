# -*- coding: utf-8 -*-
import datetime
import json
import os
import re
import sqlite3
from sqlite3 import Error
import subprocess
import sys
import time
from time import sleep
import urllib
import urllib2
import xbmc
import xbmcaddon
import xbmcgui




_TIMEFRAME = 300
__PLUGIN_ID__ = "plugin.video.ffmpeg-cutter"
__PVR_HTS_ID__ = "pvr.hts"
pvr_hts_settings = xbmcaddon.Addon(id=__PVR_HTS_ID__)




def _seconds_to_time_str(secs):

    return time.strftime('%H:%M:%S', time.gmtime(secs))




def _lookup_db(dbName):

    database_dir = xbmc.translatePath("special://database")
    entries = os.listdir(database_dir)
    entries.sort()
    entries.reverse()
    for entry in entries:
        if entry.startswith(dbName) and entry.endswith(".db"):
            return "%s%s" % (database_dir, entry)

    return None




def _create_connection(db_file):

    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        xbmc.log(e, xbmc.LOGERROR)

    return conn




def _select_bookmarks(conn, strFilename):

    bookmarks = []
    cur = conn.cursor()
    cur.execute("""
        SELECT b.idBookmark, b.timeInSeconds, b.totalTimeInSeconds, b.thumbNailImage, p.strPath, f.strFilename
        FROM bookmark b
        INNER JOIN files f ON (f.idFile=b.idFile)
        INNER JOIN path p ON (f.idPath=p.idPath)
        WHERE p.strPath || f.strFilename = ?
        AND b.thumbNailImage <> ''
        ORDER BY b.timeInSeconds;
        """, (strFilename,))

    rows = cur.fetchall()
    for row in rows:
        bookmarks += [
            {
                "idBookmark" : row[0],
                "timeInSeconds" : int(row[1]),
                "timeInStr" : _seconds_to_time_str(row[1]),
                "totalTimeInSeconds" : int(row[2]),
                "totalTimeInStr" : _seconds_to_time_str(row[2]),
                "thumbNailImage" : row[3],
                "strPath" : row[4],
                "strFilename" : row[5]
            }
        ]

    return bookmarks




def _delete_bookmarks(conn, bookmarks):

    cur = conn.cursor()
    for bookmark in bookmarks:
        cur.execute("DELETE FROM bookmark WHERE idBookmark = ?;", (bookmark["idBookmark"],))

    conn.commit()




def _show_bookmark_selection(bookmarks):

    last_secs = 0
    selection = []

    for i in range(len(bookmarks) + 1):
        startStr = bookmarks[i]["timeInStr"] if i < len(bookmarks) else bookmarks[i - 1]["totalTimeInStr"]
        start = bookmarks[i]["timeInSeconds"] if i < len(bookmarks) else bookmarks[i - 1]["totalTimeInSeconds"]
        selection += [ "%s ... %s  |  duration %s" % (_seconds_to_time_str(last_secs),
                                        startStr,
                                        _seconds_to_time_str(start - last_secs)) ]
        last_secs = start

    return xbmcgui.Dialog().multiselect("Select chapters that you want to keep", selection)




def _show_recordings_selection(recordings):

    if len(recordings) == 1:

        return recordings[0]

    elif len(recordings) == 0:

        return None

    selection = []
    for recording in recordings:
        timeStr = time.strftime("%H:%M", time.localtime(recording["start"]))
        title = recording["disp_title"]
        if recording["disp_subtitle"] != "":
            title += " (%s)" % recording["disp_subtitle"]

        selection += [ "%s | %s" % (title, timeStr) ]

    dialog = xbmcgui.Dialog()
    i = dialog.select("More than one canditate found. Select recording", selection)
    return recordings[i] if i >= 0 else None




def _query_hts_finished_recordings():

    host = pvr_hts_settings.getSetting("host")
    http_port = pvr_hts_settings.getSetting("http_port")
    username = pvr_hts_settings.getSetting("user")
    password = pvr_hts_settings.getSetting("pass")

    url = "http://%s:%s/api/dvr/entry/grid_finished?limit=%i" % (host, http_port, 999999)

    ressource = urllib2.urlopen(url)
    data = ressource.read()
    ressource.close()

    return json.loads(data)




def _derive_record_entry_from_pvr_filename(pvrFilename):

    pvrFilename = urllib.unquote(pvrFilename)
    pattern = re.compile("^pvr://recordings/tv/active/(.*/)*(.+), TV \((.+)\), (19[0-9][0-9]|20[0-9][0-9])([0-9][0-9])([0-9][0-9])_([0-9][0-9])([0-9][0-9])([0-9][0-9]), (.+)\.pvr$")
    m = pattern.match(pvrFilename)

    record_datetime = datetime.datetime(int(m.group(4)), int(m.group(5)), int(m.group(6)), int(m.group(7)), int(m.group(8)), int(m.group(9)))
    epoche = (record_datetime - datetime.datetime(1970, 1, 1)).total_seconds()
    record = {
        "pvrFilename" : pvrFilename,
        "disp_title" : m.group(2),
        "channelname" : m.group(3),
        "start" : epoche
    }

    return record




def _lookup_pvr_file(pvrFilename):

    matching_recording = []

    local_record = _derive_record_entry_from_pvr_filename(pvrFilename)
    finished_recordings = _query_hts_finished_recordings()
    for recording in finished_recordings["entries"]:
        if recording["channelname"] == local_record["channelname"] and abs(recording["start_real"] - local_record["start"]) <= _TIMEFRAME:
            matching_recording += [ recording ]

    return matching_recording




def _is_pvr_recording(filename):

    pattern = re.compile("^pvr://recordings/.+\\.pvr$")
    return pattern.match(filename) is not None




def _get_local_file(listitem):

    filename = listitem.getfilename()


    localfile = None
    recording = None

    if _is_pvr_recording(filename):

        recordings = _lookup_pvr_file(filename)
        recording = _show_recordings_selection(recordings)
        if recording != None:
            localfile = recording["filename"]

    else:

        localfile = filename

    if localfile == None or not os.path.isfile(localfile):
        xbmcgui.Dialog().notification("File not accessable",
                                    "Video file not found in local filesystem",
                                    xbmcgui.NOTIFICATION_ERROR)
        return None, None

    else:

        return localfile, recording




def _get_bookmarks(conn, listitem):

    bookmarks = _select_bookmarks(conn, listitem.getfilename())

    if len(bookmarks) > 0:

        selected = _show_bookmark_selection(bookmarks)
        if selected == None or len(selected) == 0 or len(selected) == len(bookmarks) + 1:
            xbmcgui.Dialog().notification("Cancel",
                                        "Nothing to do",
                                        xbmcgui.NOTIFICATION_INFO)
            return None, None

        return bookmarks, selected

    else:

        xbmcgui.Dialog().notification("No bookmarks found",
                                    "File does not have any bookmarks",
                                    xbmcgui.NOTIFICATION_INFO)
        return None, None




def _exec_ffmpeg(params):

    call = [ "ffmpeg", "-hide_banner", "-y" ]
    call += params

    xbmc.log(" ".join(call), xbmc.LOGNOTICE)
    p = subprocess.Popen(call,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)

    out, err = p.communicate()
    xbmc.log(out, xbmc.LOGNOTICE)
    xbmc.log(err, xbmc.LOGNOTICE)
    return out.decode("utf-8")




def _seperate_filename_and_extention(filename):

    name_parts = filename.split(".")
    name_wo_ext = ".".join(name_parts[0:-1])
    extension = name_parts[-1]
    return name_wo_ext, extension




def _calculate_real_cuts(bookmarks, markers):

    real_cuts = []

    start = 0
    prev_end = 0
    pending = False
    len_bookmarks = len(bookmarks)

    for i in range(len_bookmarks + 1):

        if i in markers and not pending:
            start = prev_end
            pending = True
        elif i not in markers and pending:
            real_cuts += [
                {
                    "start" : start,
                    "startStr" : _seconds_to_time_str(start),
                    "end" : prev_end,
                    "endStr" : _seconds_to_time_str(prev_end)
                }
            ]
            pending = False

        prev_end = bookmarks[i]["timeInSeconds"] if i < len_bookmarks else bookmarks[i - 1]["totalTimeInSeconds"]

    if pending:
        real_cuts += [
            {
                "start" : start,
                "startStr" : _seconds_to_time_str(start),
                "end" : bookmarks[i - 1]["totalTimeInSeconds"],
                "endStr" : _seconds_to_time_str(bookmarks[i - 1]["totalTimeInSeconds"])
            }
        ]

    return real_cuts




def _split(filename, bookmarks, markers, progress = None, max_progress = 100):

    segments = []

    cuts = _calculate_real_cuts(bookmarks, markers)
    name_wo_ext, extension = _seperate_filename_and_extention(filename)

    counter = 0
    for cut in cuts:
        counter += 1

        progress.update(percent = int(counter / float(len(cuts)) * max_progress), message = "Splitting %i of %i ..." % (counter, len(cuts)))

        segment_name = "%s.%03i.%s" % (name_wo_ext, counter, extension)
        params = [ "-i", filename, "-ss", str(cut["start"]), "-to", str(cut["end"]), "-c", "copy", "-map", "0", segment_name]
        _exec_ffmpeg(params)
        segments += [ segment_name ]

    return segments




def _join(filename, segments):

    name_wo_ext, extension = _seperate_filename_and_extention(filename)
    joined_filename = "%s.%s.%s" % (name_wo_ext, "cut", extension)

    if len(segments) == 1:

        os.rename(segments[0], joined_filename)

    else:
        concat = "concat:%s" % "|".join(segments)
        params = [ "-i", concat, "-c", "copy", "-map", "0", joined_filename ]
        _exec_ffmpeg(params)




def _clean(segments):

    for segment in segments:
        if os.path.isfile(segment):
            os.remove(segment)




def _get_db_connection():

    dbFile = _lookup_db("MyVideos")
    if dbFile is None:
        xbmcgui.Dialog().notification("Video database not found",
                                    "Video database not found",
                                    xbmcgui.NOTIFICATION_ERROR)
        return None

    conn = _create_connection(dbFile)
    if conn is None:
        xbmcgui.Dialog().notification("Video database not accessable",
                                    "Cannot open video database",
                                    xbmcgui.NOTIFICATION_ERROR)
        return None


    return conn




def cut(listitem):

    filename, recording = _get_local_file(listitem)
    if filename is None:
        return

    conn = _get_db_connection()
    if conn == None:
        return

    bookmarks, markers = _get_bookmarks(conn, listitem)
    if bookmarks == None or markers == None:
        return

    progress = xbmcgui.DialogProgressBG()
    progress.create("FFMPEG Cutter", "Splitting file...")

    segments = _split(filename, bookmarks, markers, progress, 50)

    progress.update(55, "Joining segments...")
    _join(filename, segments)

    progress.update(95, "Clean workspace...")
    _clean(segments)

    progress.update(97, "Wipe bookmarks...")
    _delete_bookmarks(conn, bookmarks)

    progress.close()
    conn.close()




def split(listitem):

    filename, recording = _get_local_file(listitem)
    if filename is None:
        return

    conn = _get_db_connection()
    if conn == None:
        return

    bookmarks, markers = _get_bookmarks(conn, listitem)
    if bookmarks == None or markers == None:
        return

    progress = xbmcgui.DialogProgressBG()
    progress.create("FFMPEG Splitter", "Splitting file...")

    segments = _split(filename, bookmarks, markers, progress, 90)

    progress.update(95, "Wipe bookmarks...")
    _delete_bookmarks(conn, bookmarks)

    progress.close()
    conn.close()