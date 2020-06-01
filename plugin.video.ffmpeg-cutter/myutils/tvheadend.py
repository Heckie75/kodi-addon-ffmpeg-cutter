# coding=utf-8

import json
import urllib2
from myutils import kodiutils

def query_hts_finished_recordings(host, http_port, username, password):

    url = "http://%s:%s/api/dvr/entry/grid_finished?limit=%i" % (
        host, http_port, 999999)

    ressource = urllib2.urlopen(url)
    data = ressource.read()
    ressource.close()

    return json.loads(data, encoding=kodiutils.getpreferredencoding())