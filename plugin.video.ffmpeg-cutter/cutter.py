# -*- coding: utf-8 -*-

import json
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from myutils import ffmpegutils, kodiutils, tvheadend


_TIMEFRAME = 300
__PLUGIN_ID__ = "plugin.video.ffmpeg-cutter"
__PVR_HTS_ID__ = "pvr.hts"

EXTENSIONS = [None, ".mkv", ".mp4", ".avi"]

addon = xbmcaddon.Addon()
getMsg = addon.getLocalizedString


class Cutter:

    CONTAINER = [None, ".mkv"]
    VCODEC = [None, "h264"]

    ffmpegUtils = None

    setting_container = None
    setting_streams = None
    setting_video = None
    setting_x264_preset = None
    setting_x264_tune = None
    setting_pvr_dir = None
    setting_pvr_dirname = None
    setting_dir_selection = None
    setting_confirm = None
    setting_delete = None
    setting_backup = None
    setting_recording_rename = None
    setting_recording_rename_subtitle = None
    setting_recording_rename_timestamp = None
    setting_recording_rename_directory = None

    setting_hts_host = None
    setting_hts_http_port = None
    setting_hts_username = None
    setting_hts_password = None

    def __init__(self):

        plugin_settings = xbmcaddon.Addon(id=__PLUGIN_ID__)
        pvr_hts_settings = xbmcaddon.Addon(id=__PVR_HTS_ID__)

        _ffmpeg_executable = plugin_settings.getSetting("ffmpeg")
        _ffprobe_executable = plugin_settings.getSetting("ffprobe")
        self.ffmpegUtils = ffmpegutils.FFMpegUtils(ffmpeg_executable=_ffmpeg_executable,
                                                   ffprobe_executable=_ffprobe_executable)

        self.setting_container = self.CONTAINER[int(
            plugin_settings.getSetting("container"))]
        self.setting_streams = int(plugin_settings.getSetting("streams"))
        self.setting_video = int(plugin_settings.getSetting("video"))
        self.setting_x264_preset = self.ffmpegUtils.X264_PRESETS[int(
            plugin_settings.getSetting("x264_preset"))]
        self.setting_x264_tune = self.ffmpegUtils.X264_TUNES[int(
            plugin_settings.getSetting("x264_tune"))]
        self.setting_pvr_dir = int(plugin_settings.getSetting("pvr_dir"))
        self.setting_pvr_dirname = plugin_settings.getSetting("pvr_dirname")
        self.setting_dir_selection = plugin_settings.getSetting(
            "dir_selection") == "true"
        self.setting_confirm = plugin_settings.getSetting("confirm") == "true"
        self.setting_delete = plugin_settings.getSetting("delete") == "true"
        self.setting_backup = plugin_settings.getSetting("backup") == "true"
        self.setting_recording_rename = plugin_settings.getSetting(
            "recording_rename") == "true"
        self.setting_recording_rename_subtitle = plugin_settings.getSetting(
            "recording_rename_subtitle") == "true"
        self.setting_recording_rename_timestamp = plugin_settings.getSetting(
            "recording_rename_timestamp") == "true"
        self.setting_recording_rename_directory = plugin_settings.getSetting(
            "recording_rename_directory") == "true"

        self.setting_hts_host = pvr_hts_settings.getSetting("host")
        self.setting_hts_http_port = pvr_hts_settings.getSetting("http_port")
        self.setting_hts_username = pvr_hts_settings.getSetting("user")
        self.setting_hts_password = pvr_hts_settings.getSetting("pass")

    def cut(self, listitem):

        # determine full-qualified filename
        filename, recording = self._select_source(listitem)
        if filename is None or not os.path.isfile(filename):
            xbmc.log(filename, xbmc.LOGERROR)
            xbmcgui.Dialog().notification(getMsg(32101),
                                          getMsg(32102),
                                          xbmcgui.NOTIFICATION_ERROR)
            return

        # inspect file
        ffprobe_json = self.ffmpegUtils.inspect_media(filename)

        # filter or select streams (depends on settings)
        if self.setting_streams == 0:
            streams = self._select_streams(filename, ffprobe_json)
            if streams == None:
                return

            # remove unsupported streams for container "mkv"
            if self.setting_container == self.CONTAINER[1]:
                streams = self._unselect_unsupported_streams(
                    ffprobe_json, streams)

        else:
            streams = self._filter_streams(filename, ffprobe_json,
                                           audio_visual_impaired=False,
                                           subtitle_hearing_impaired=False,
                                           subtitle_teletext=False)

        if len(streams) == 0:
            xbmcgui.Dialog().notification(getMsg(32105),
                                          getMsg(32106),
                                          xbmcgui.NOTIFICATION_INFO)
            return

        # select bookmarks and markers
        bookmarks, markers = self._select_bookmarks(listitem, ffprobe_json)
        if len(bookmarks) > 0 and (markers == None or len(markers) == 0):
            return

        # determine target directory
        if self.setting_dir_selection:
            target_directory = self._select_target_directory(filename)
            if target_directory == None:
                return
        else:
            target_directory = os.path.dirname(filename)

        # start processing
        if self.setting_confirm:
            rv = xbmcgui.Dialog().yesno(getMsg(32109), getMsg(32119))
            if not rv:
                return

        progress = xbmcgui.DialogProgressBG()
        progress.create(getMsg(32001), getMsg(32110))
        segments, duration = self._encode(filename=filename,
                                          target_directory=target_directory,
                                          ffprobe_json=ffprobe_json,
                                          streams=streams,
                                          bookmarks=bookmarks,
                                          markers=markers,
                                          progress=progress)

        if self.setting_recording_rename and recording != None:
            filename, target_directory = self._name_recording(
                filename, target_directory, recording)

        self._join(filename, segments,
                   target_directory, duration, progress)

        if self.setting_delete:
            if self.setting_backup:
                self._backup(filename)
            else:
                segments += [filename]

        progress.update(98, getMsg(32112))
        self._clean(segments)

        progress.update(99, getMsg(32113))
        kodiutils.delete_bookmarks(bookmarks)

        progress.close()

    def _select_source(self, listitem):
        """
        Determines full-qualified filename in filesystem for given listitem.

        If listitem is PFR recording it trys to derive file in local filesystem or share location given by settings.

        Returns full-qualified filename in filesystem or None
        """

        filename = listitem.getfilename()

        localfile = None
        recording = None

        if kodiutils.is_pvr_recording(filename):

            candidates = self._lookup_pvr_candidates(filename)
            if len(candidates) == 1:
                recording = candidates[0]
            elif len(candidates) == 0:
                recording = None
            else:
                recording = self._display_recordings_selection(candidates)

            if recording != None:
                if self.setting_pvr_dir:
                    localfile = self._translate_pvr_to_shared_location(
                        recording["filename"])
                else:
                    localfile = recording["filename"]

        else:

            localfile = filename

        if kodiutils.getOS() in [kodiutils.OS_WINDOWS, kodiutils.getOS()]:
            localfile = localfile.replace(
                "smb://", os.path.sep * 2).replace("/", os.path.sep)

        return localfile, recording

    def _lookup_pvr_candidates(self, pvrFilename):
        """
        Looksup pvr recoring or recordings by calling tvheadend API and tries to match given recording by channelname and timeframe,
        since it is not possible to get specific recording, e.g. by using ID.

        returns array of candidates, in best case just one
        """

        matching_recording = []

        title, channelname, start = kodiutils.parse_recording_from_pvr_url(
            pvrFilename)
        finished_recordings = tvheadend.query_hts_finished_recordings(self.setting_hts_host, self.setting_hts_http_port,
                                                                      self.setting_hts_username, self.setting_hts_password)
        for recording in finished_recordings["entries"]:
            if recording["channelname"] == channelname and abs(recording["start_real"] - start) <= _TIMEFRAME:
                matching_recording += [recording]

        return matching_recording

    def _display_recordings_selection(self, recordings):
        """
        Displays selection dialog in order to select specific recording

        returns object of selected recording
        """

        selection = []
        for recording in recordings:
            timeStr = time.strftime(
                "%H:%M", time.localtime(recording["start"]))
            title = recording["disp_title"]
            if recording["disp_subtitle"] != "":
                title += " (%s)" % recording["disp_subtitle"]

            selection += ["%s | %s" % (title, timeStr)]

        dialog = xbmcgui.Dialog()
        i = dialog.select(getMsg(32114), selection)
        return recordings[i] if i >= 0 else None

    def _translate_pvr_to_shared_location(self, remotefile):
        """
        Translates remote path (of recording) on machine where tvheadend is running to
        path of shared location that is accessable from machine where Kodi is running

        returns full-qualified path in shared location including spefic file
        """

        shared_location = self.setting_pvr_dirname.split(os.sep)
        shared_location = list(filter(lambda s: s != "",  shared_location))
        if len(shared_location) < 2:
            return None

        anchor = shared_location.pop()

        remote = remotefile.split("/")
        try:
            i = remote.index(anchor)
        except:
            return None

        for s in remote[i:]:
            shared_location.append(s)

        shared_location = os.sep.join(shared_location)
        return shared_location

    def _select_bookmarks(self, listitem, ffprobe_json):

        bookmarks = kodiutils.select_bookmarks(listitem.getfilename())
        markers = None

        if len(bookmarks) > 0:

            markers = self._show_bookmark_selection(bookmarks)
            return bookmarks, markers

        else:

            return bookmarks, None

    def _show_bookmark_selection(self, bookmarks):

        last_secs = 0
        selection = []

        for i in range(len(bookmarks) + 1):
            startStr = bookmarks[i]["timeInStr"] if i < len(
                bookmarks) else bookmarks[i - 1]["totalTimeInStr"]
            start = bookmarks[i]["timeInSeconds"] if i < len(
                bookmarks) else bookmarks[i - 1]["totalTimeInSeconds"]
            selection += ["%s ... %s  |  %s %s" % (kodiutils.seconds_to_time_str(last_secs),
                                                   startStr,
                                                   getMsg(32115),
                                                   kodiutils.seconds_to_time_str(start - last_secs))]
            last_secs = start

        return xbmcgui.Dialog().multiselect(getMsg(32116), selection)

    def _select_target_directory(self, filename):

        sources = [
            {
                "file": os.path.dirname(filename),
                "label": getMsg(32014)
            }
        ]

        try:
            sources += kodiutils.json_rpc("Files.GetSources",
                                          {"media": "video"})
        except:
            pass

        selection = ["%s (%s)" % (s["label"], s["file"]) for s in sources]

        i = xbmcgui.Dialog().select(getMsg(32047), selection)
        if i == -1:
            return None

        return sources[i]["file"]

    def _select_streams(self, filename, ffprobe_json):

        selection = []

        for stream in ffprobe_json["streams"]:

            if stream["codec_type"] == "video":

                s = "%s: %sx%s, %s, %s" % (
                    stream["codec_type"], stream["width"], stream["height"], stream["display_aspect_ratio"], stream["codec_long_name"])

            elif stream["codec_type"] == "audio":

                impaired = ", %s" % getMsg(32117) if "disposition" in stream and "visual_impaired" in stream[
                    "disposition"] and stream["disposition"]["visual_impaired"] == 1 else ""
                lang = " (%s%s)" % (
                    stream["tags"]["language"], impaired) if "tags" in stream and "language" in stream["tags"] else ""
                s = "%s: %sch %s%s, %s" % (
                    stream["codec_type"], stream["channels"], stream["channel_layout"], lang, stream["codec_long_name"])

            elif stream["codec_type"] == "subtitle":

                impaired = ", %s" % getMsg(32118) if "disposition" in stream and "hearing_impaired" in stream[
                    "disposition"] and stream["disposition"]["hearing_impaired"] == 1 else ""
                lang = " (%s%s)" % (
                    stream["tags"]["language"], impaired) if "tags" in stream and "language" in stream["tags"] else ""
                s = "%s: %s%s" % (stream["codec_type"],
                                  stream["codec_long_name"], lang)

            else:

                s = "%s: %s" % (stream["codec_type"],
                                stream["codec_long_name"])

            selection += [s]

        return xbmcgui.Dialog().multiselect(getMsg(32120), selection)

    def _filter_streams(self, filename, ffprobe_json, audio_visual_impaired=False, subtitle_hearing_impaired=False, subtitle_teletext=False):

        stream_ids = []

        for stream in ffprobe_json["streams"]:

            if stream["codec_type"] == "video":

                stream_ids += [stream["index"]]

            elif stream["codec_type"] == "audio":

                if not audio_visual_impaired and "disposition" in stream and "visual_impaired" in stream["disposition"] and stream["disposition"]["visual_impaired"] == 1:
                    pass
                else:
                    stream_ids += [stream["index"]]

            elif stream["codec_type"] == "subtitle":

                if not subtitle_teletext and stream["codec_name"] == "dvb_teletext":
                    pass
                elif not subtitle_hearing_impaired and "disposition" in stream and "hearing_impaired" in stream["disposition"] and stream["disposition"]["hearing_impaired"] == 1:
                    pass
                else:
                    stream_ids += [stream["index"]]

        return stream_ids

    def _unselect_unsupported_streams(self, ffprobe_json, selected_streams):

        teletext_streams = list(filter(
            lambda stream: stream["codec_type"] == "subtitle" and stream["codec_name"] == "dvb_teletext", ffprobe_json["streams"]))
        for stream in teletext_streams:
            try:
                selected_streams.remove(stream["index"])
            except:
                pass

        return selected_streams

    def _needs_encoding(self, ffprobe_json, wanted_video_codec_name):

        for stream in ffprobe_json["streams"]:
            if stream["codec_type"] == "video":
                return stream["codec_name"] != wanted_video_codec_name

        return False

    def _encode(self, filename, target_directory, ffprobe_json, streams, bookmarks, markers, progress):

        PROGRESS_START_LEVEL = 0
        PROGRESS_MAX_LEVEL = 80

        segments = []

        # basename and extension
        basename = os.path.basename(os.path.splitext(filename)[0])
        if self.setting_container == None:
            extension = os.path.splitext(filename)[1]
        else:
            extension = self.setting_container

        # determine cuts
        cuts = self._calculate_real_cuts(bookmarks, markers)
        total_cuts = max(1, len(cuts))

        # ffmpeg filter and codec settings
        codecs = ["-c", "copy", "-c:a", "copy"]
        if self.setting_video == 2 or self.setting_video == 1 and self._needs_encoding(ffprobe_json, "h264"):
            codecs += ["-fflags", "+igndts",
                       "-vf", "yadif",
                       "-c:v", "libx264",
                       "-preset", self.setting_x264_preset,
                       "-tune", self.setting_x264_tune]
        else:
            codecs += ["-c:v", "copy"]

        # duration for progress
        processed_duration = 0
        if len(cuts) > 0:
            total_duration = sum(
                list(map(lambda c: c["end"] - c["start"], cuts)))
        else:
            total_duration = float(ffprobe_json["format"]["duration"])

        # process segments
        for counter in range(total_cuts):

            # inpput file
            params = ["-i", filename]

            # cuts
            if len(cuts) > 0:
                cut = cuts[counter]
                params += ["-ss", str(cut["start"]), "-to", str(cut["end"])]
                segment_duration = cut["end"] - cut["start"]
            else:
                segment_duration = total_duration

            # codecs
            params += codecs

            # mapping streams
            for s in streams:
                params += ["-map", "0:%s" % s]

            # output file
            segment_name = os.path.join(
                target_directory, "%s.%03d%s" % (basename, counter + 1, extension))
            params += [segment_name]

            # progress
            def _callback(level):
                progress.update(level, message="%s %i %s %i ..." % (
                    getMsg(32121), counter + 1, getMsg(32122), total_cuts))

            current_start_level = PROGRESS_START_LEVEL + processed_duration / \
                float(total_duration) * \
                (PROGRESS_MAX_LEVEL - PROGRESS_START_LEVEL)
            ffmpeg_progress = ffmpegutils.Progress(
                _callback, current_start_level, PROGRESS_MAX_LEVEL, total_duration)

            # call ffmpeg
            self.ffmpegUtils.exec_ffmpeg(params, progress=ffmpeg_progress)

            segments += [segment_name]
            processed_duration += segment_duration

        return segments, processed_duration

    def _calculate_real_cuts(self, bookmarks, markers):

        real_cuts = []
        len_bookmarks = len(bookmarks)
        if len_bookmarks == 0 or len(markers) == 0:
            return real_cuts

        start = 0
        prev_end = 0
        pending = False

        for i in range(len_bookmarks + 1):

            if i in markers and not pending:
                start = prev_end
                pending = True
            elif i not in markers and pending:
                real_cuts += [
                    {
                        "start": start,
                        "startStr": kodiutils.seconds_to_time_str(start),
                        "end": prev_end,
                        "endStr": kodiutils.seconds_to_time_str(prev_end)
                    }
                ]
                pending = False

            prev_end = bookmarks[i]["timeInSeconds"] if i < len_bookmarks else bookmarks[i -
                                                                                         1]["totalTimeInSeconds"]

        else:

            if pending:
                real_cuts += [
                    {
                        "start": start,
                        "startStr": kodiutils.seconds_to_time_str(start),
                        "end": bookmarks[i - 1]["totalTimeInSeconds"],
                        "endStr": kodiutils.seconds_to_time_str(bookmarks[i - 1]["totalTimeInSeconds"])
                    }
                ]

        return real_cuts

    def _name_recording(self, filename, directory, recording):

        splitext = os.path.splitext(filename)
        extension = splitext[1]

        renamed_filename = recording["disp_title"].encode(kodiutils.getpreferredencoding())

        if self.setting_recording_rename_subtitle and recording["disp_subtitle"] and recording["disp_subtitle"] != recording["disp_title"]:
            renamed_filename += " - %s" % recording["disp_subtitle"].encode(kodiutils.getpreferredencoding())

        if self.setting_recording_rename_timestamp:
            timeStr = time.strftime(time.strftime(
                "%Y-%m-%d %H-%M", time.localtime(recording["start"])))
            renamed_filename += " (%s)" % timeStr

        renamed_filename += extension.encode(kodiutils.getpreferredencoding())
        renamed_filename = kodiutils.makeLegalFilename(renamed_filename)

        if self.setting_recording_rename_directory and "directory" in recording and recording["directory"]:
            target_directory = "%s%s%s" % (
                directory, os.path.sep, kodiutils.makeLegalFilename(
                    recording["directory"]))
        else:
            target_directory = directory.encode(kodiutils.getpreferredencoding())

        xbmc.log(renamed_filename, xbmc.LOGNOTICE)

        return renamed_filename, target_directory

    def _join(self, filename, segments, dirname, duration, progress):

        PROGRESS_START_LEVEL = 80
        PROGRESS_MAX_LEVEL = 98

        splitext = os.path.splitext(filename)
        basename = os.path.basename(splitext[0])
        if self.setting_container == None:
            extension = splitext[1]
        else:
            extension = self.setting_container

        if not os.path.exists(dirname):
            os.makedirs(dirname)

        joined_filename = os.path.join(
            dirname, "%s%s%s" % (basename, ".cut", extension))

        if len(segments) == 1:

            progress.update(90, getMsg(32111))
            os.rename(segments[0], joined_filename)

        else:

            # progress
            def _callback(level):
                progress.update(level, message="%s ..." % getMsg(32111))

            ffmpeg_progress = ffmpegutils.Progress(
                _callback, PROGRESS_START_LEVEL, PROGRESS_MAX_LEVEL, duration)

            concat = "concat:%s" % "|".join(segments)
            params = ["-i", concat, "-c", "copy", "-map", "0", joined_filename]
            self.ffmpegUtils.exec_ffmpeg(params, progress=ffmpeg_progress)

        return joined_filename

    def _backup(self, filename):

        splitext = os.path.splitext(filename)
        backup_filename = "%s%s%s" % (splitext[0], ".bak", splitext[1])
        os.rename(filename, backup_filename)

        return backup_filename

    def _clean(self, segments):

        for segment in segments:
            if os.path.isfile(segment):
                os.remove(segment)
