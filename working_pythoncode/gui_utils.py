"""
Library for GUI of Audio 3D Project, Group B
author: H. Zhu, M. Heiss
"""

from PySide import QtCore, QtGui
from plot import GLPlotWidget
from dt2 import DT2
from math import acos, degrees, cos, sin, radians
import headtracker_data as headtracker
import threading




class State(QtCore.QObject):

    def __init__(self):
        super(State, self).__init__()
        # variables which are shared between gui and dsp algorithm
        self.gui_sp = []
        self.gui_settings = {}
        self.gui_error = []
        self.dsp_run = False
        self.dsp_stop = False
        self.dsp_pause = False
        self.dsp_sp_spectrum = []
        self.dsp_hrtf_spectrum = []

        # mutex for exchanging data between gui and dsp algorithm
        self.mtx_sp = threading.Lock()
        self.mtx_settings = threading.Lock()
        self.mtx_error = threading.Lock()
        self.mtx_run = threading.Lock()
        self.mtx_stop = threading.Lock()
        self.mtx_pause = threading.Lock()

        # gui state variables
        # enable head tracker
        self.enable_headtracker = False
        # head position in gui coordinates
        self.audience_pos = QtCore.QPoint(170, 170)
        self.speaker_list = []
        self.speaker_to_show = 0

    # @brief stop button clicked alternates dsp_stop boolean and stops dsp
    # algorithm
    # @details
    # @author Felix
    def switch_stop_playback(self):
        self.mtx_stop.acquire()
        if self.dsp_stop is False:
            self.dsp_stop = True
        else:
            self.dsp_stop = False
        self.mtx_stop.release()

    # @brief pause button clicked alternates dsp_pause boolean and pause dsp
    # algorithm
    # @details
    # @author Felix
    def switch_pause_playback(self):
        # start pause
        self.mtx_pause.acquire()
        if self.dsp_pause is False:
            self.dsp_pause = True
        # end pause
        else:
            self.dsp_pause = False
        self.mtx_pause.release()

    def send_error(self, message):
        self.mtx_error.acquire()
        if message not in self.gui_error:
            self.gui_error.append(message)
        self.mtx_error.release()

    def check_error(self):
        self.mtx_error.acquire()
        if len(self.gui_error) > 0:
            msgbox = QtGui.QMessageBox()
            msgbox.setText(self.gui_error.pop(0))
            msgbox.exec_()
        self.mtx_error.release()


# @class <Headtracker> This class integrates the headtracker
#
#
#
class Headtracker(object):

    def __init__(self):
        self.head_deg = 0
        self.dt2 = DT2()

    # @brief This function calls the azimuth_angle function of DT2 object
    # which only extracts the azimuthal head movement
    # recorded by the headtracking setup
    def cal_head_deg(self):
        self.head_deg = headtracker.azimuth_angle(self.dt2.angle()[0])

    # @brief This function returns the azimuth angle, which is recorded
    #        with the headtracker setup
    def get_head_deg(self):
        return self.head_deg


# Items inside the QGraphicsScene, including Speaker and Audience
# @class <Itemr> This class defines items inside the QGraphicsScene,
# including Speaker and Audience.
#
class Item(QtGui.QGraphicsPixmapItem):

    def __init__(self, state):

        image = self.origin_image.scaled(
            50, 50, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        super(Item, self).__init__(QtGui.QPixmap.fromImage(image))

        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.setFlag(QtGui.QGraphicsItem.ItemIsSelectable)
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtGui.QGraphicsItem.ItemIsFocusable)
        self.state = state

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            event.ignore()
            return

        self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):

        if QtCore.QLineF(QtCore.QPointF(event.screenPos()),
                         QtCore.QPointF(event.buttonDownScreenPos(
                             QtCore.Qt.LeftButton))).length() < \
           QtGui.QApplication.startDragDistance():
                                return

        drag = QtGui.QDrag(event.widget())
        mime = QtCore.QMimeData()
        drag.setMimeData(mime)
        drag.exec_()
        self.setCursor(QtCore.Qt.OpenHandCursor)

    def mouseReleaseEvent(self, event):
        self.setCursor(QtCore.Qt.OpenHandCursor)


# @class <Room> This class defines the Gui Scene
# A Room object displays the relative Audience and Speaker items positions
#
#
class Room(QtGui.QGraphicsScene):
    current_item = 0

    def __init__(self, state):
        super(Room, self).__init__()
        self.state = state

    # Definition of mouse move events related to the QGraphicsScene:

    def mousePressEvent(self, e):
        self.current_item = self.itemAt(e.scenePos())
        QtGui.QGraphicsScene.mousePressEvent(self, e)

    def dragEnterEvent(self, e):
        e.acceptProposedAction()

    def dragMoveEvent(self, e):

        e.acceptProposedAction()
        speaker_list = self.state.speaker_list
        try:
            self.current_item.setPos(e.scenePos().x() - 25, e.scenePos().y(
            ) - 25)
            bounded_x, bounded_y = self.get_bound_pos(e.scenePos().x() - 25,
                                                      e.scenePos().y() - 25)
            self.current_item.setPos(bounded_x, bounded_y)

            if self.current_item.type == 'audience':
                self.state.audience_pos = self.current_item.pos()

                for speaker in speaker_list:
                    deg, dis = speaker.cal_rel_pos()
                    if dis < 50:
                        x, y = self.get_abs_pos(deg, 50)
                        x, y = self.get_bound_pos(x, y)
                        speaker.setPos(x, y)
                    speaker.cal_rel_pos()

            elif self.current_item.type == 'speaker':
                deg, dis = self.current_item.cal_rel_pos()
                if dis < 50:
                    x, y = self.get_abs_pos(deg, 50)
                    self.current_item.setPos(x, y)
                self.current_item.cal_rel_pos()
                self.state.speaker_to_show = self.current_item.index

        except AttributeError:
            pass

    # @brief keeps cursor inside gui_scene
    # @details
    # @author Huijiang
    def get_bound_pos(self, x, y):

        if x >= 350 and y >= 350:
            x = 350
            y = 350
        if x >= 350 and y <= 0:
            x = 350
            y = 0
        if x <= 0 and y <= 0:
            x = 0
            y = 0
        if x <= 0 and y >= 350:
            x = 0
            y = 350

        return x, y

    # @brief returns new position of item
    # @details
    # @author
    def get_abs_pos(self, azimuth, dist):
        x0 = self.state.audience_pos.x()
        y0 = self.state.audience_pos.y()

        x = x0 + dist * sin(radians(azimuth))
        y = y0 - dist * cos(radians(azimuth))

        return x, y


# @class <View> This class is responsible for displaying the contents of on the
# QGraphicsScene
#
class View(QtGui.QGraphicsView):

    def __init__(self, state, scene):
        super(View, self).__init__(scene)
        self.state = state

    def dragEnterEvent(self, e):
        e.acceptProposedAction()
        QtGui.QGraphicsView.dragEnterEvent(self, e)

    def dropEvent(self, e):
        self.viewport().update()
        QtGui.QGraphicsView.dropEvent(self, e)

    def dragMoveEvent(self, e):
        e.acceptProposedAction()
        QtGui.QGraphicsView.dragMoveEvent(self, e)

    # this will disable scrolling of the view
    def wheelEvent(self, q_wheel_event):
        pass

    def keyPressEvent(self, q_key_event):
        pass


# @class <SignalHandler> Signal handler for QGraphicsItem
# which doesn't provide the signal/slot function
#
class SignalHandler(QtCore.QObject):

    show_property = QtCore.Signal()

    def __init__(self, index):
        super(SignalHandler, self).__init__()
        self.index = index


# @class <Speaker> Speaker item represent the source positions in
# the QGraphicsScene relative to the Audience item
#
#
class Speaker(Item):

    type = 'speaker'
    path = 'unknown'

    def __init__(self, state, index, path, posx=0, posy=0, norm=False):

        self.state = state
        speaker_list = self.state.speaker_list
        self.index = index
        image_path = './image/speaker' + str(index + 1) + '.png'
        self.origin_image = QtGui.QImage(image_path)
        super(Speaker, self).__init__(state)
        self.setPos(posx, posy)
        self.path = path
        self.norm = norm
        self.signal_handler = SignalHandler(self.index)
        speaker_list.append(self)
        self.state.mtx_sp.acquire()
        self.state.gui_sp.append({"angle": None, "distance": None, "path":
                                  self.path, "normalize": self.norm})
        self.state.mtx_sp.release()
        self.cal_rel_pos()

    # @brief this function returns the relative position of the speaker
    # to the 'audience', defined by a radial variable deg (defined counter
    # clockwise) and the distance
    # @details head_deg can take the azimuthal angle set by the headtracker
    # into account
    # @author
    def cal_rel_pos(self, head_deg=0):

        dx = self.x() - self.state.audience_pos.x()
        dy = self.state.audience_pos.y() - self.y()
        dis = (dx ** 2 + dy ** 2) ** 0.5
        if dis == 0:
            dis += 0.1

        # required geometric transformation due to the difference in definition
        # used by the headtracker setup
        deg = degrees(acos(dy / dis))
        if dx < 0:
            deg = 360 - deg

        deg -= head_deg

        if deg <= 0:
            deg += 360
        self.state.mtx_sp.acquire()
        # write new relative position in exchange variable gui - dsp
        self.state.gui_sp[self.index]["angle"] = deg
        self.state.gui_sp[self.index]["distance"] = dis / 100
        self.state.mtx_sp.release()
        return deg, dis

    # @brief double click on speaker item offers the opportunity to change
    # the speaker settings in a seperate QWidget window
    def mouseDoubleClickEvent(self, event):
        self.state.speaker_to_show = self.index
        self.signal_handler.show_property.emit()


# @class <Audience> Audience item represents the relative user position,
# without headtracker in the QGraphicsScene
#
class Audience(Item):

    type = 'audience'
    origin_image = QtGui.QImage('./image/audience.png')

    def __init__(self, state):
        self.state = state
        super(Audience, self).__init__(state)
        self.setPos(170, 170)


# @class <SpeakerProperty> Additional widget window to define speaker .wav path
# speaker position and to activate inverse filtering for speaker before
# adding it to the scene and afterwards by double click on the speaker item
#
class SpeakerProperty(QtGui.QWidget):

    added = QtCore.Signal()
    posx = 0
    posy = 0

    def __init__(self, state):
        super(SpeakerProperty, self).__init__()
        self.state = state
        self.is_on = False
        # set labels
        self.path_label = QtGui.QLabel('Audio Source:')
        self.position_label = QtGui.QLabel(
            'Relative Position to the Audience:')
        self.azimuth_label = QtGui.QLabel('Azimuth:')
        self.distance_label = QtGui.QLabel('Distance:')        # set line edit
        self.path_line_edit = QtGui.QLineEdit()
        self.azimuth_line_edit = QtGui.QLineEdit()
        self.distance_line_edit = QtGui.QLineEdit()

        # set buttons
        self.file_select_button = QtGui.QPushButton('Browse')
        self.confirm_button = QtGui.QPushButton('Confirm')
        self.cancel_button = QtGui.QPushButton('Cancel')
        self.normalize_box = QtGui.QCheckBox('Normalize Audio')
        self.normalize_box.setCheckState(QtCore.Qt.Checked)
        self.combo_box = QtGui.QComboBox()
        self.combo_box.addItem('Standard')
        self.combo_box.addItem('Big')
        self.path = 'unknown'
        self.init_ui()

    def init_ui(self):

        # set layout
        layout = QtGui.QGridLayout()
        layout.addWidget(self.path_label, 0, 0, 1, 4)
        layout.addWidget(self.path_line_edit, 1, 0, 1, 3)
        layout.addWidget(self.file_select_button, 1, 3, 1, 1)
        layout.addWidget(self.position_label, 4, 0, 1, 4)
        layout.addWidget(self.azimuth_label, 5, 0, 1, 1)
        layout.addWidget(self.azimuth_line_edit, 5, 1, 1, 1)
        layout.addWidget(self.distance_label, 5, 2, 1, 1)
        layout.addWidget(self.distance_line_edit, 5, 3, 1, 1)
        layout.addWidget(self.confirm_button, 6, 0, 1, 2)
        layout.addWidget(self.cancel_button, 6, 2, 1, 2)
        layout.addWidget(self.normalize_box, 4, 3, 1, 1)

        # connect signal and slots
        self.file_select_button.clicked.connect(self.browse)
        self.confirm_button.clicked.connect(self.confirm)
        self.cancel_button.clicked.connect(self.cancel)

        # set window
        self.setLayout(layout)
        self.setWindowTitle('Speaker Properties')

    # @brief function corresponding to the browse button on the settings
    # widget, to open a file dialog in order to choose a .wav file
    #
    @QtCore.Slot()
    def browse(self):

        file_browser = QtGui.QFileDialog()
        self.path = file_browser.getOpenFileName()[0]
        self.path_line_edit.setText(self.path)

    # @brief function corresponding to the confirm button on the settings
    # widget, to add a speaker to the QGraphicsScene with the choosen
    # properties
    #
    @QtCore.Slot()
    def confirm(self):
        x0 = self.state.audience_pos.x()
        y0 = self.state.audience_pos.y()
        azimuth = float(self.azimuth_line_edit.text())
        dist = 100 * float(self.distance_line_edit.text())
        self.posx = x0 + dist * sin(radians(azimuth))
        self.posy = y0 - dist * cos(radians(azimuth))

        x = self.posx
        y = self.posy

        self.posx, self.posy = self.get_bound_pos(x, y)
        self.added.emit()
        self.close()

    @QtCore.Slot()
    def cancel(self):
        self.close()

    def clear(self):
        self.normalize_box.setCheckState(QtCore.Qt.Unchecked)
        self.path_line_edit.clear()
        self.azimuth_line_edit.clear()
        self.distance_line_edit.clear()
        self.posx = 0
        self.posy = 0

    def closeEvent(self, q_close_event):   # flake8: noqa
        self.is_on = False
        self.added.disconnect()
        self.clear()

    # @brief keeps cursor inside gui_scene
    # @details
    # @author Huijiang
    def get_bound_pos(self, x, y):

        if x >= 350 and y >= 350:
            x = 350
            y = 350
        if x >= 350 and y <= 0:
            x = 350
            y = 0
        if x <= 0 and y <= 0:
            x = 0
            y = 0
        if x <= 0 and y >= 350:
            x = 0
            y = 350

        return x, y

# @class <SequencePlot> Additional window is created to display plot of speaker
# and HRTF spectrum while .wav is played
#
class SequencePlot(QtGui.QWidget):

    plot_on = QtCore.Signal()

    def __init__(self, parent=None):
        super(SequencePlot, self).__init__(parent)
        self.is_on = False

        # initialize the GL widget
        self.speaker_spec = GLPlotWidget()
        self.lhrtf_spec = GLPlotWidget()
        self.rhrtf_spec = GLPlotWidget()

        self.layoutVertical = QtGui.QVBoxLayout(self)
        self.layoutVertical.addWidget(self.speaker_spec)
        self.layoutVertical.addWidget(self.lhrtf_spec)
        self.layoutVertical.addWidget(self.rhrtf_spec)
        self.setGeometry(100, 100, self.speaker_spec.width,
                         2 * self.speaker_spec.height)

        self.setWindowTitle('Sequence Plot')
        self.timer = QtCore.QTimer(self)

    def closeEvent(self, event):   # flake8: noqa
        self.timer.timeout.disconnect()
        self.timer.stop()
        self.is_on = False
