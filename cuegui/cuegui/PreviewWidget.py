#  Copyright Contributors to the OpenCue Project
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


"""Widget for displaying a preview of a frame in an image viewer."""


from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

# pylint: disable=wrong-import-position
from future import standard_library
standard_library.install_aliases()
# pylint: enable=wrong-import-position

import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as Et

from PySide2 import QtCore
from PySide2 import QtWidgets

import cuegui.Logger
import cuegui.Utils


logger = cuegui.Logger.getLogger(__file__)


class PreviewProcessorDialog(QtWidgets.QDialog):
    """Widget for displaying a preview of a frame in an image viewer."""

    def __init__(self, job, frame, aovs=False, parent=None):
        """
        :type  job: opencue.wrappers.job.Job
        :param job: job containing the frame
        :type  frame: opencue.wrappers.frame.Frame
        :param frame: frame to display
        :type  aovs: bool
        :param aovs: whether to display AOVs or just the main image
        :type  parent: PySide2.QtWidgets.QWidget
        :param parent: the parent widget
        """
        QtWidgets.QDialog.__init__(self, parent)
        self.app = cuegui.app()

        self.__job = job
        self.__frame = frame
        self.__aovs = aovs

        self.__previewThread = None
        self.__itvFile = None

        layout = QtWidgets.QVBoxLayout(self)

        self.__msg = QtWidgets.QLabel("Waiting for preview images...", self)
        self.__progbar = QtWidgets.QProgressBar(self)

        layout.addWidget(self.__msg)
        layout.addWidget(self.__progbar)

    def process(self):
        """Opens the image viewer."""
        items = []
        http_host = self.__frame.resource().split("/")[0]
        http_port = self.__findHttpPort()

        aovs = ""
        if self.__aovs:
            aovs = "/aovs"

        playlist = urllib.request.urlopen("http://%s:%d%s" % (http_host, http_port, aovs)).read()
        for element in Et.fromstring(playlist).findall("page/edit/element"):
            items.append(element.text)

        if not items:
            return

        self.__itvFile = self.__writePlaylist(playlist)
        self.__previewThread = PreviewProcessorWatchThread(items, self)
        self.app.threads.append(self.__previewThread)
        self.__previewThread.start()
        self.__progbar.setRange(0, len(items))

        self.__previewThread.existCountChanged.connect(self.updateProgressDialog)
        self.__previewThread.timeout.connect(self.processTimedOut)

    def updateProgressDialog(self, current, max_progress):
        """Updates the progress dialog."""
        if max_progress != current:
            self.__progbar.setValue(current)
        else:
            self.close()

    def processTimedOut(self):
        """Event handler when the process has timed out."""
        self.close()
        QtWidgets.QMessageBox.critical(
            self,
            "Preview Timeout",
            "Unable to preview images, timed out while waiting for images to be copied.")

    @staticmethod
    def __writePlaylist(data):
        (fh, name) = tempfile.mkstemp(suffix=".itv", prefix="playlist")
        os.close(fh)
        fp = open(name, "w")
        try:
            fp.write(data)
        finally:
            fp.close()
        return name

    def __findHttpPort(self):
        log = cuegui.Utils.getFrameLogFile(self.__job, self.__frame)
        fp = open(log, "r")
        try:
            counter = 0
            for line in fp:
                counter += 1
                if counter >= 5000:
                    break
                if line.startswith("Preview Server"):
                    return int(line.split(":")[1].strip())
        finally:
            fp.close()

        raise Exception("Katana 2.7.19 and above is required for preview feature.")


class PreviewProcessorWatchThread(QtCore.QThread):
    """
    Waits for preview files to appear and emits the progress every second.  This
    thread times out after 60 seconds, which should only occur if there are
    serious filer problems.
    """
    existCountChanged = QtCore.Signal(int, int)

    def __init__(self, items, parent=None):
        QtCore.QThread.__init__(self, parent)
        self.__items = items
        self.__timeout = 60 + (30 * len(items))

    def run(self):
        """
        Just check to see how many files exist and
        emit that back to our parent.
        """
        start_time = time.time()
        while 1:
            count = len([path for path in self.__items if os.path.exists(path)])
            self.emit(QtCore.SIGNAL('existCountChanged(int, int)'), count, len(self.__items))
            self.existsCountChanged.emit(count, len(self.__items))
            if count == len(self.__items):
                break
            time.sleep(1)
            if time.time() > self.__timeout + start_time:
                self.timeout.emit()
                logger.warning('Timed out waiting for preview server.')
                break
