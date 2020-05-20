# kodi-addon-ffmpeg-cutter
A tool in order to cut pvr recordings and videos along bookmarks

ffmpeg-cutter enables you to cut videos directly in Kodi. The addon requires a local installation of ffmpeg which is shipped with most Linux distributions. It runs on Linux based systems only. I am not sure if it works on LibreElec, too.

The addon can cut and split video files that are located in your local filesystem. However, it can also process tv recordings of tvheadend that are listed in kodi's pvr menu. The precondition is that tvheadend runs on the same machine as Kodi and that recording's storage can be accessed in terms of path and permissions. The tvheadend api must not be protected by username and password. Read-only permissions are is good enough in order to query recordings. 

**WARNING: Use this addon at your own risk!**

The addon works as follows.

## Step 1 - Settings

You should define the output directory and decide if source file will be deleted after processing. 

<img src="plugin.video.ffmpeg-cutter/resources/screenshots/screenshot_1.png?raw=true">


## Step 2 - Add bookmarks in video player

<img src="plugin.video.ffmpeg-cutter/resources/screenshots/screenshot_2.png?raw=true">


## Step 3 - Open context menu

<img src="plugin.video.ffmpeg-cutter/resources/screenshots/screenshot_3.png?raw=true">

## Step 4 - Select chapters

According to the bookmarks that you have set before, you must select the chapters that you want to keep. 

<img src="plugin.video.ffmpeg-cutter/resources/screenshots/screenshot_4.png?raw=true">

## Step 5 - Start processing and wait

After you have confirmed to start processing the addon does the following:

1. Try to find video file in filesystem, maybe by quering tvheadend recordings

2. calculate cuttings that are really required 

3. Split the source file by using the following ffmpeg command

```
ffmpeg -i <source file> -ss <start in seconds> -to <end in seconds> -c copy -map 0 <segment n>
```

4. Join all segments by using the following ffmpeg command

```
ffmpeg -i concat:<segment 1>|...|<segment n> -c copy -map 0 <joined file>
```

There is no new encoding. The video container format is kept, e.g. ```ts```.