import constants

from PyQt5.QtCore import pyqtSlot, QByteArray, QObject, pyqtSignal, QRunnable, Qt, QTimer, QDir
from PyQt5.QtGui import QPalette, QColor, QFont, QIcon, QPixmap
from PyQt5 import QtBluetooth as QtBt
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedLayout,
    QHBoxLayout,
    QAction,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QComboBox,
    QSlider,
    QLCDNumber,
    QFileDialog,
    QCheckBox,
    QFrame,
    QTextBrowser,
    QLabel,
    QMessageBox,
)

# from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
import traceback
import sys
import struct
# import os
from pathlib import Path
from random import random
import pandas as pd
import time
from datetime import datetime

import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration  # , TaskMode
from nidaqmx import system as daq_system

from decimal import Decimal
from collections import deque

from math import log, exp
import numpy as np
from scipy.fft import fft, fftfreq

# import threading
# import statistics
try:
    # from tensorflow import config
    # from tensorflow.keras import models
    # tf = True
    tf = False
except Exception as e:
    print(e)
    tf = False
    print("Tensorflow not loaded.")
from scipy.optimize import curve_fit
from scipy.optimize import OptimizeWarning
import warnings
import json

if tf:
    try:
        gpus = config.list_physical_devices('GPU')
        if gpus:
            # Currently, memory growth needs to be the same across GPUs
            for gpu in gpus:
                config.experimental.set_memory_growth(gpu, True)
            logical_gpus = config.list_logical_devices('GPU')
            print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
    except Exception as e:
        # Memory growth must be set before GPUs have been initialized
        print(e, "- Tensorflow not loaded.")

warnings.simplefilter("error", OptimizeWarning)


class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    https://www.pythonguis.com/tutorials/multithreading-pyqt-applications-qthreadpool/

    Supported signals are:

    finished
        No data

    error
        tuple (exc_type, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    """
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    name = pyqtSignal(str)
    data = pyqtSignal(float)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['data_callback'] = self.signals.data
        self.kwargs['name_callback'] = self.signals.name

    @pyqtSlot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as ex:
            print(ex)
            traceback.print_exc()
            exc_type, value = sys.exc_info()[:2]
            self.signals.error.emit((exc_type, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class SignalCommunicate(QObject):
    # https://stackoverflow.com/a/45620056
    # got_new_sensor_data = pyqtSignal(float, float)
    # position_updated = pyqtSignal(float)
    request_graph_update = pyqtSignal()


class MainWindow(QMainWindow):
    BLE_characteristic_ready = pyqtSignal()

    ''' UI '''
    buttonCalibrate = None
    startButton = None
    startButton2 = None
    device_combo_sc = None
    device_combo_user = None
    ScaleBox = None
    bleBox = None
    SaveBox = None
    sliderX = None
    text_box = None
    bleBox2 = None
    SaveBox2 = None
    flow_label = None
    flow_label2 = None
    channel_one_box = None
    channel_two_box = None
    ''' Graph '''
    data_line_channel_one = None
    data_line_channel_two = None
    fft_line_channel_one = None
    fft_line_channel_two = None
    graphWidget = None
    fftWidget = None
    p1 = None
    p2 = None
    ''' Data '''
    x_channel_one = None
    y_channel_one = None
    x_channel_two = None
    y_channel_two = None
    data_channel_one = None
    data_channel_two = None
    yf_channel_one = None
    xf_channel_one = None
    yf_channel_two = None
    xf_channel_two = None
    values_deque = []
    ''' Flags '''
    calibrated = False
    calibration = None
    maxX = None
    deviceText = None
    ''' DAQ '''
    activeDAQ = False
    daq_device = None
    task = None
    discard = True
    discard_counter = 9
    ''' BLE '''
    useBLE = False
    activeBLE = False
    BLE_device = None
    BLE_scan_complete = False
    BLE_service = None
    BLE_UUID_service = None
    BLE_UUID_characteristic = None
    BLE_characteristic = None
    controller = None
    serviceUid = None
    scanning = False
    ''' Flow '''
    flow_detected = False
    blink = False
    blink_on = False
    steady_flow = False

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        ''' Design main window '''
        self.resize(1920, 1080)
        self.setWindowIcon(QIcon('imgs/Sencilia-Logo-RGB-darkblue-cropped2.jpg'))
        self.setWindowTitle("Sencilia Flow Sensor")
        self._createMenuBar()
        widget = QWidget()
        self.main_layout = QStackedLayout(widget)
        self.setMainLayout(self.main_layout)
        self.setCentralWidget(widget)

        ''' NI DAQ '''
        self.system = daq_system.System.local()

        ''' Graph '''
        self.p3 = pg.PlotItem()
        self.x_channel_one = list(range(256))
        self.x_channel_two = list(range(256))
        self.y_channel_one = [random() * 256 for _ in range(256)]
        self.y_channel_two = [random() * 256 for _ in range(256)]
        self.data_line_channel_one = self.p3.plot(
            self.x_channel_one,
            self.y_channel_one,
            pen=pg.mkPen(color=(255, 20, 20))
        )
        self.graphWidget.addItem(self.data_line_channel_one)

        self.data_line_channel_two = self.p3.plot(
            self.x_channel_two,
            self.y_channel_two,
            pen=pg.mkPen(color=(20, 255, 20))
        )
        self.p2.addItem(self.data_line_channel_two)

        ''' FFT '''
        self.yf_channel_one = fft(self.y_channel_one)
        self.xf_channel_one = fftfreq(constants.FFT_N1, constants.SAMPLING_RATE)[:constants.FFT_N1 // 2]
        self.fft_line_channel_one = self.fftWidget.plot(
            self.xf_channel_one[0:constants.FFT_N1 // 10 + 1],
            1.0 / constants.FFT_N1 * np.abs(self.yf_channel_one[0:constants.FFT_N1 // 2])[0:constants.FFT_N1 // 10 + 1],
            pen=pg.mkPen(color=(255, 20, 20, 255))
        )
        self.fft_line_channel_two = self.fftWidget.plot(
            list(np.linspace(0, 1, 256)),
            [random() * 128 for _ in range(256)],
            pen=pg.mkPen(color=(20, 255, 20, 255))
        )

        ''' Timer '''
        self.timerCombo = QTimer(self)
        self.timerCombo.setInterval(500)
        self.timerCombo.timeout.connect(self.update_combo)
        self.timerCombo.start()

        self.timeCounter = Decimal('0.0')
        # print(threading.currentThread().getName())
        self.signalComm = SignalCommunicate()
        self.signalComm.request_graph_update.connect(self.update_graph)
        self.last_flow = time.time() - 11

        ''' Calibration '''
        self.calibrateData = 0

        ''' Tensorflow '''
        if tf:
            self.model = models.load_model('D:/RUG/Dev/Notebooks/models/2021-10-19 first working model')
            self.model.summary()
            self.values_deque = deque()
        # except Exception as e:
        #     print(e, "- Tensorflow not loaded.")
        # end Tensorflow

        ''' BLE '''
        # print('Thread = {}          Function = init()'.format(threading.currentThread().getName()))
        self.agent = QtBt.QBluetoothDeviceDiscoveryAgent(self)
        self.agent.deviceDiscovered.connect(self.discovered_device)
        self.agent.finished.connect(self.deviceScanDone)
        self.agent.error.connect(self.deviceScanError)
        self.agent.setLowEnergyDiscoveryTimeout(2000)
        self.itemService = []
        self.BLE_characteristic_ready.connect(self.characteristic_ready)

        ''' Flow '''
        self.timerFlow = QTimer(self)
        self.timerFlow.setInterval(500)
        self.timerFlow.timeout.connect(self.check_flow)
        self.timerFlow.start()

        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
        vb = self.p1.getViewBox()
        # print(vb.sceneBoundingRect())

    from BLEfunctions import scan_for_devices
    from BLEfunctions import discovered_device
    from BLEfunctions import deviceScanError
    from BLEfunctions import deviceScanDone
    from BLEfunctions import characteristic_ready
    from BLEfunctions import deviceConnected
    from BLEfunctions import deviceDisconnected
    from BLEfunctions import errorReceived
    from BLEfunctions import addLEservice
    from BLEfunctions import serviceScanDone
    from BLEfunctions import handleServiceError
    from BLEfunctions import handleServiceOpened

    def setMainLayout(self, layout):
        scientific = self.scientificWidget()
        user = self.userWidget()

        layout.addWidget(scientific)
        layout.addWidget(user)

    def scientificWidget(self):
        scientific_widget = QWidget(self)
        scientific_layout = QHBoxLayout(scientific_widget)

        self.graphWidget = pg.PlotWidget()
        self.fftWidget = pg.PlotWidget()
        # self.fftWidget.getPlotItem().hideAxis('bottom')
        # self.fftWidget.getPlotItem().hideAxis('left')

        self.p1 = self.graphWidget.plotItem
        vb = self.p1.getViewBox()
        # print(vb)
        # print(self.p1.vb)
        self.p2 = pg.ViewBox()
        self.p1.showAxis('right')
        self.p1.scene().addItem(self.p2)
        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
        self.p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(self.p1)

        self.updateGraphViews()
        self.p1.vb.sigResized.connect(self.updateGraphViews)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(self.graphWidget, 1)
        left_layout.addWidget(self.fftWidget, 1)

        # self.left_widget.setLayout(self.left_layout)
        # self.left_widget.setFixedWidth(100)
        scientific_layout.addWidget(left_widget)
        # self.mainLayout.addWidget(self.graphWidget, 1)

        self.device_combo_sc = QComboBox(self)
        self.device_combo_sc.currentIndexChanged.connect(self.device_combo_sc_changed)

        self.bleBox = QCheckBox("Use bluetooth")
        self.bleBox.stateChanged.connect(self.ble_box_changed)
        self.bleBox.setChecked(False)

        channel_widget = QWidget()
        channel_layout = QHBoxLayout(channel_widget)
        self.channel_one_box = QCheckBox("Channel 1")
        self.channel_one_box.setChecked(True)
        self.channel_two_box = QCheckBox("Channel 2")
        self.channel_two_box.setChecked(True)
        channel_layout.addWidget(self.channel_one_box)
        channel_layout.addWidget(self.channel_two_box)
        self.channel_one_box.setFixedWidth(100)
        self.channel_two_box.setFixedWidth(100)

        self.SaveBox = QCheckBox("Save data")
        self.SaveBox.setChecked(True)

        self.sliderX = QSlider(Qt.Horizontal)
        self.sliderX.setTickInterval(10)
        self.sliderX.setSingleStep(1)
        self.sliderX.setValue(40)
        self.sliderX.setEnabled(False)

        self.ScaleBox = QCheckBox("Full scale")
        self.ScaleBox.stateChanged.connect(self.ScaleBoxChanged)
        self.ScaleBox.setChecked(True)

        self.startButton = QPushButton("Start")
        self.startButton.pressed.connect(self.start_button_click)

        self.buttonCalibrate = QPushButton("Calibrate")
        self.buttonCalibrate.pressed.connect(self.calibrateButtonClick)

        self.flow_label = QLCDNumber()
        self.flow_label.display('000')
        self.flow_label.setDigitCount(3)
        self.flow_label.setStyleSheet("QLCDNumber {color: red;}")
        self.flow_label.setFixedWidth(200)
        self.flow_label.setFixedHeight(125)
        self.flow_label.setFrameStyle(QFrame.NoFrame)
        self.flow_label.setSegmentStyle(QLCDNumber.SegmentStyle(2))

        right_widget = QWidget()
        right_widget.setFixedWidth(250)
        right_layout = QVBoxLayout(right_widget)
        right_layout.addSpacing(10)
        right_layout.addWidget(self.flow_label)
        right_layout.addSpacing(5)
        right_layout.addWidget(self.device_combo_sc)
        right_layout.addWidget(self.bleBox)
        right_layout.addStretch()
        right_layout.addWidget(channel_widget)
        right_layout.addWidget(self.startButton)
        right_layout.addWidget(self.buttonCalibrate)
        right_layout.addWidget(self.SaveBox)
        right_layout.addStretch()
        right_layout.addWidget(self.ScaleBox)
        right_layout.addWidget(self.sliderX)
        right_layout.addSpacing(10)
        right_layout.setAlignment(self.device_combo_sc, Qt.AlignTop)

        scientific_layout.addWidget(right_widget)
        return scientific_widget

    def userWidget(self):
        user_widget = QWidget(self)
        user_layout = QHBoxLayout(user_widget)

        device_combo_user_widget = QWidget()
        device_combo_user_layout = QHBoxLayout(device_combo_user_widget)
        self.device_combo_user = QComboBox(self)
        self.device_combo_user.currentIndexChanged.connect(self.device_combo_user_changed)
        device_combo_user_layout.addSpacing(1)
        device_combo_user_layout.addWidget(self.device_combo_user)
        device_combo_user_layout.addSpacing(1)

        substance_combo_user_widget = QWidget()
        substance_combo_user_layout = QHBoxLayout(substance_combo_user_widget)
        self.substance_combo_user = QComboBox(self)
        self.substance_combo_user.addItem("Demineralized water")
        # self.substance_combo_user.currentIndexChanged.connect(self.substance_combo_user_changed)
        substance_combo_user_layout.addSpacing(1)
        substance_combo_user_layout.addWidget(self.substance_combo_user)
        substance_combo_user_layout.addSpacing(1)

        pump_combo_user_widget = QWidget()
        pump_combo_user_layout = QHBoxLayout(pump_combo_user_widget)
        self.pump_combo_user = QComboBox(self)
        self.pump_combo_user.addItem("Alaris GW Volumetric Pump")
        # self.pump_combo_user.currentIndexChanged.connect(self.pump_combo_user_changed)
        pump_combo_user_layout.addSpacing(1)
        pump_combo_user_layout.addWidget(self.pump_combo_user)
        pump_combo_user_layout.addSpacing(1)

        ble_box2_widget = QWidget()
        ble_box2_layout = QHBoxLayout(ble_box2_widget)
        self.bleBox2 = QCheckBox("Use bluetooth")
        self.bleBox2.stateChanged.connect(self.ble_box2_changed)
        self.bleBox2.setChecked(False)
        ble_box2_layout.addSpacing(1)
        ble_box2_layout.addWidget(self.bleBox2)
        ble_box2_layout.addSpacing(1)

        save_box2_widget = QWidget()
        save_box2_layout = QHBoxLayout(save_box2_widget)
        self.SaveBox2 = QCheckBox("Save data")
        self.SaveBox2.setChecked(True)
        save_box2_layout.addSpacing(1)
        save_box2_layout.addWidget(self.SaveBox2)
        save_box2_layout.addSpacing(1)

        start_button2_widget = QWidget()
        start_button2_layout = QHBoxLayout(start_button2_widget)
        self.startButton2 = QPushButton("Start")
        self.startButton2.pressed.connect(self.start_button_click)
        start_button2_layout.addStretch()
        # start_button2_layout.addStretch()
        start_button2_layout.addWidget(self.startButton2)
        start_button2_layout.addStretch()

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        # left_layout.addSpacing(10)
        left_layout.addWidget(QLabel("   Device:"))
        left_layout.addWidget(device_combo_user_widget)
        left_layout.addWidget(QLabel("   Substance:"))
        left_layout.addWidget(substance_combo_user_widget)
        left_layout.addWidget(QLabel("   Pump model:"))
        left_layout.addWidget(pump_combo_user_widget)
        # left_layout.addSpacing(10)
        left_layout.addWidget(ble_box2_widget)
        # left_layout.addStretch()
        left_layout.addWidget(save_box2_widget)
        left_layout.addWidget(start_button2_widget)
        left_layout.addStretch()

        ''' Logo '''
        image = QPixmap('imgs/Sencilia-Logo-RGB-white-semi-isolated.png')
        image.setDevicePixelRatio(3)
        logo_label = QLabel()
        logo_label.setPixmap(image)
        left_layout.addWidget(logo_label)

        ''' main flow number '''
        self.flow_label2 = QLCDNumber()
        self.flow_label2.display('000')
        self.flow_label2.setDigitCount(3)
        self.flow_label2.setStyleSheet("color: red")
        self.flow_label2.setFixedWidth(400)
        self.flow_label2.setFixedHeight(250)
        self.flow_label2.setFrameStyle(QFrame.NoFrame)
        self.flow_label2.setSegmentStyle(QLCDNumber.SegmentStyle(2))

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        top_right_widget = QWidget()
        top_right_layout = QHBoxLayout(top_right_widget)
        top_right_layout.addStretch()
        top_right_layout.addWidget(self.flow_label2)
        label = QLabel()
        label.setText("mL/h")
        font = label.font()
        font.setPointSize(30)
        label.setFont(font)
        label.setStyleSheet('color: red')
        label.setAlignment(Qt.AlignmentFlag.AlignBottom)
        top_right_layout.addWidget(label)
        top_right_layout.addStretch()
        right_layout.addWidget(top_right_widget)
        right_layout.addSpacing(10)
        self.text_box = QTextBrowser()
        self.text_box.setFontPointSize(16)
        right_layout.addWidget(self.text_box)
        right_layout.addSpacing(10)

        user_layout.addWidget(left_widget, 1)
        user_layout.addWidget(right_widget, 5)

        return user_widget

    def updateGraphViews(self):
        # view has resized; update auxiliary views to match
        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
        # p3.setGeometry(p1.vb.sceneBoundingRect())

        # need to re-update linked axes since this was called
        # incorrectly while views had different shapes.
        # (probably this should be handled in ViewBox.resizeEvent)
        self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
        # p3.linkedViewChanged(p1.vb, p3.XAxis)

    def _createMenuBar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        self.new_action = QAction('&New', self)
        self.new_action.setShortcut('Ctrl+N')
        self.new_action.triggered.connect(self.setup_new_data)
        file_menu.addAction(self.new_action)
        self.save_action = QAction('&Save', self)
        self.save_action.setShortcut('Ctrl+S')
        self.save_action.triggered.connect(self.save_to_file)
        file_menu.addAction(self.save_action)
        file_menu.addSeparator()
        self.exit_action = QAction('Exit', self)
        # self.exit_action.setShortcut('Ctrl+W')
        self.exit_action.triggered.connect(self.close_application)
        file_menu.addAction(self.exit_action)

        edit_menu = menu_bar.addMenu("&Edit")

        window_menu = menu_bar.addMenu("&Window")
        self.scientific_action = QAction('&Scientific', self)
        self.scientific_action.setShortcut('Ctrl+Y')
        self.scientific_action.triggered.connect(self.scientific_action_call)
        window_menu.addAction(self.scientific_action)
        self.user_action = QAction('&User', self)
        self.user_action.setShortcut('Ctrl+U')
        self.user_action.triggered.connect(self.user_action_call)
        window_menu.addAction(self.user_action)
        help_menu = menu_bar.addMenu("&Help")

    def scientific_action_call(self):
        self.main_layout.setCurrentIndex(0)

    def user_action_call(self):
        self.main_layout.setCurrentIndex(1)

    def ble_callback(self, characteristic, ble_data_byte_array):
        # print(struct.unpack('f', ble_data_byte_array.data()))

        try:
            flow_voltage = struct.unpack('f', ble_data_byte_array.data())[0]
            temp_voltage = 1
            data_one = (flow_voltage, temp_voltage)
            data_two = (flow_voltage + 20 + random(), temp_voltage)
            # self.add_data_point(data_one, None)
        except Exception as err:
            print("ble_callback error: ", err)
        self.add_data_point(data_one, data_two)

    def ble_box_changed(self):
        self.useBLE = self.bleBox.isChecked()
        self.bleBox2.setChecked(self.useBLE)

        now = datetime.now()

        if self.useBLE:
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Bluetooth enabled.")
        else:
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Bluetooth disabled.")
        if self.useBLE and self.BLE_device is None:
            self.scan_for_devices()
            if not self.timerCombo.isActive():
                self.timerCombo.setInterval(500)
                self.timerCombo.start()

    def ble_box2_changed(self):
        self.useBLE = self.bleBox2.isChecked()
        self.bleBox.setChecked(self.useBLE)

    def update_graph(self):
        # print('Thread = {}          Function = update_graph()'.format(threading.currentThread().getName()))
        # if self.channel_one_box.isChecked():
        self.data_line_channel_one.setData(self.x_channel_one, self.y_channel_one)  # Update the data.
        # self.fft_line.setData(self.xf, 2.0 / constants.FFT_N1 * np.abs(self.yf[0:constants.FFT_N1 // 2]))
        self.fft_line_channel_one.setData(self.xf_channel_one[0:constants.FFT_N1 // 10 + 1],
                                          1.0 / constants.FFT_N1 * np.abs(self.yf_channel_one[0:constants.FFT_N1 // 2])[
                                                                   0:constants.FFT_N1 // 10 + 1])

        # if self.channel_two_box.isChecked():
        self.data_line_channel_two.setData(self.x_channel_two, self.y_channel_two)  # Update the data.
        # self.fft_line.setData(self.xf, 2.0 / constants.FFT_N1 * np.abs(self.yf[0:constants.FFT_N1 // 2]))
        self.fft_line_channel_two.setData(self.xf_channel_two[0:constants.FFT_N1 // 10 + 1],
                                          1.0 / constants.FFT_N1 * np.abs(self.yf_channel_two[0:constants.FFT_N1 // 2])[
                                                                   0:constants.FFT_N1 // 10 + 1])

        # TODO: improve scale
        # if len(self.y_channel_one) > 2:
        #     self.p1.setYRange(min(self.y_channel_one), max(self.y_channel_one))

    def add_data_point(self, data_one=None, data_two=None):

        if not self.ScaleBox.isChecked():
            self.maxX = (self.sliderX.value() + 1) * 6

        timestamp = round(time.time() * 1000)

        r1 = 0
        r2 = 0

        if data_one is not None:
            flow_voltage_one, temp_voltage_one = data_one
            if len(self.x_channel_one) == 0:
                self.x_channel_one.append(0)
            else:
                self.x_channel_one.append(self.x_channel_one[-1] + 1)
            self.y_channel_one.append(flow_voltage_one)
            if not self.ScaleBox.isChecked():
                while len(self.x_channel_one) > self.maxX:
                    self.x_channel_one = self.x_channel_one[1:]
                    self.y_channel_one = self.y_channel_one[1:]
            beta = 3760
            resistance = 9990 / ((5 / temp_voltage_one) - 1)
            temperature = beta / log(resistance / (12000 * exp(- beta / 298.15))) - 273.15
            datapoint = {'timestamp': timestamp,
                         'time': self.timeCounter,
                         'flow_voltage': flow_voltage_one,
                         'temp_voltage': temp_voltage_one,
                         'temperature': temperature}
            self.data_channel_one = self.data_channel_one.append(datapoint, ignore_index=True)
            ''' FFT'''
            if len(self.x_channel_one) > constants.FFT_N1:
                y = self.y_channel_one[-constants.FFT_N1:]
                y = y - np.average(y)
                self.yf_channel_one = fft(y)
                self.xf_channel_one = fftfreq(constants.FFT_N1, constants.SAMPLING_RATE)[:constants.FFT_N1 // 2]
                r1 = max(1.0 / constants.FFT_N1 * np.abs(self.yf_channel_one[0:constants.FFT_N1 // 2])[
                                                  0:constants.FFT_N1 // 10 + 1])

        if data_two is not None:
            flow_voltage_two, temp_voltage_two = data_two
            if len(self.x_channel_two) == 0:
                self.x_channel_two.append(0)
            else:
                self.x_channel_two.append(self.x_channel_two[-1] + 1)
            self.y_channel_two.append(flow_voltage_two)
            if not self.ScaleBox.isChecked():
                while len(self.x_channel_two) > self.maxX:
                    self.x_channel_two = self.x_channel_two[1:]
                    self.y_channel_two = self.y_channel_two[1:]
            beta = 3950
            resistance = 9980 / ((5 / temp_voltage_two) - 1)
            temperature = beta / log(resistance / (10000 * exp(- beta / 298.15))) - 273.15
            datapoint = {'timestamp': timestamp,
                         'time': self.timeCounter,
                         'flow_voltage': flow_voltage_two,
                         'temp_voltage': temp_voltage_two,
                         'temperature': temperature}
            self.data_channel_two = self.data_channel_two.append(datapoint, ignore_index=True)
            ''' FFT'''
            if len(self.x_channel_two) > constants.FFT_N1:
                y = self.y_channel_two[-constants.FFT_N1:]
                y = y - np.average(y)
                self.yf_channel_two = fft(y)
                self.xf_channel_two = fftfreq(constants.FFT_N1, constants.SAMPLING_RATE)[:constants.FFT_N1 // 2]
                r2 = max(1.0 / constants.FFT_N1 * np.abs(self.yf_channel_two[0:constants.FFT_N1 // 2])[
                                                  0:constants.FFT_N1 // 10 + 1])

        # TODO: improve scale
        # maxy = max(self.y)
        # miny = min(self.y)
        # delta = maxy - miny
        # if delta < 2:
        #     self.graphWidget.setYRange(miny, maxy)
        # else:
        #     self.graphWidget.setYRange(miny, maxy)
        # nn = 1.5
        # maxy *= nn
        # miny *= nn
        # maxabs = max([abs(maxy), abs(miny)])
        # self.graphWidget.setYRange(-maxabs, maxabs)

        self.timeCounter += Decimal('0.1')

        ''' Adjust FFT scale '''
        r = max(r1, r2)
        if r < 0.02:
            self.fftWidget.setYRange(0, 0.02)
        else:
            self.fftWidget.setYRange(0, r)

        ''' Tensorflow '''
        if len(self.x_channel_one) > 1024 and tf:
            if len(self.x_channel_one) % 5 == 0:
                chunk = np.array(self.y_channel_one[-1024:])
                value = float(self.model.predict(chunk.reshape((1, 1024))))
                self.values_deque.append(value)

                if len(self.values_deque) > 120:
                    self.values_deque.popleft()

        def func(fx, fa, fb):
            return fa + fb * fx

        if len(self.x_channel_one) > constants.FLOW_DETECTION_BLOCK_LEN:
            try:
                now = datetime.now()

                chunk = self.y_channel_one[-constants.FLOW_DETECTION_BLOCK_LEN:]
                x = np.linspace(0, len(chunk), len(chunk))
                p_opt, p_cov = curve_fit(func, x, chunk)
                b = p_opt[1]

                if b < constants.FLOW_START_NEG_THRESHOLD:
                    if not self.flow_detected:
                        print("Flow detected, b: ", b)
                        self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Flow detected.")
                    self.flow_detected = True
                if b > constants.FLOW_STOP_POS_THRESHOLD:
                    # print(b)
                    if self.flow_detected:
                        print("Flow stopped, b: ", b)
                        self.last_flow = time.time()
                        self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Flow stopped.")
                    self.flow_detected = False
            except OptimizeWarning as ex:
                print("OptimizeWarning Error: ", ex)
                pass
            except Exception as ex:
                print("Error in curve estimation ", ex)

        self.signalComm.request_graph_update.emit()

    def daq_callback(self, task_handle, every_n_samples_event_type, number_of_samples, callback_data):
        # print('Thread = {}          Function = daq_callback()'.format(threading.currentThread().getName()))
        try:
            sample = self.task.read(number_of_samples_per_channel=10)
            if self.discard:
                self.discard_counter -= 1
                if self.discard_counter < 1:
                    self.discard = False
                return 0

            i = 0
            data_one = None
            data_two = None
            if self.channel_one_box.isChecked():
                flow_voltage = 1000 * sum(sample[i]) / len(sample[i])
                i += 1
                temp_voltage = sum(sample[i]) / len(sample[i])
                i += 1
                data_one = (flow_voltage, temp_voltage)

            if self.channel_two_box.isChecked():
                flow_voltage = 1000 * sum(sample[i]) / len(sample[i])
                i += 1
                temp_voltage = sum(sample[i]) / len(sample[i])
                data_two = (flow_voltage, temp_voltage)

            self.add_data_point(data_one, data_two)
        except Exception as err:
            print("daq_callback error: ", err)
            now = datetime.now()
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Error: {0}".format(str(err)))
            return 0

        return 0

    def check_flow(self):
        if self.flow_detected:
            now = datetime.now()
            if len(self.values_deque) > 10:
                std_value = np.std(self.values_deque)
                mean_value = np.mean(self.values_deque)
                std_over_mean = abs(std_value / mean_value)
                print("std: {:.2f}, mean: {:.2f}, ratio: {:.2f}".format(std_value, mean_value, std_over_mean))
            else:
                std_over_mean = 10

            if std_over_mean > 0.5:
                if self.blink_on:
                    self.flow_label.display('---')
                    self.flow_label2.display('---')
                    self.blink_on = False
                else:
                    self.flow_label.display('')
                    self.flow_label2.display('')
                    self.blink_on = True
                if not self.blink:
                    self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Calculating...")
                self.blink = True
                self.steady_flow = False
            else:
                self.blink = False
                if not self.steady_flow:
                    self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Steady flow detected.")
                    self.steady_flow = True
                values = list(self.values_deque)
                values.sort()
                try:
                    if len(values) > 112:
                        values = values[51:111]
                    else:
                        values = values[int(len(values) / 5):int(4 * len(values) / 5)]
                    value = np.mean(values)
                    value = 0 if value < 0 else value
                    value = round(value)
                    self.flow_label.display(value)
                    self.flow_label2.display(value)
                except Exception as ex:
                    print(ex)
                    self.text_box.append(
                        now.strftime("%Y-%m-%d %H:%M:%S") + ": Error estimating flow: {0}".format(str(ex)))
        else:
            if (time.time() - self.last_flow) > 10:
                self.flow_label.display('000')
                self.flow_label2.display('000')
            else:
                if self.blink_on:
                    self.flow_label.display('---')
                    self.flow_label2.display('---')
                    self.blink_on = False
                else:
                    self.flow_label.display('')
                    self.flow_label2.display('')
                    self.blink_on = True

    def start_button_click(self) -> None:
        self.deviceText = self.device_combo_sc.currentText()
        if self.deviceText == "":
            return

        if self.device_combo_sc.currentData() == 'BLE':
            combo_ble = True
            combo_daq = False
        elif self.device_combo_sc.currentData() == 'DAQ':
            combo_daq = True
            combo_ble = False
        else:
            return

        self.startButton.setEnabled(False)
        self.startButton2.setEnabled(False)

        now = datetime.now()

        if self.activeDAQ:
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ":  Stop data acquisition.")
            self.activeDAQ = False
            self.task.stop()
            self.task.close()

            self.save_to_file()

            self.startButton.setText("Start")
            self.startButton2.setText("Start")
            self.device_combo_sc.setEnabled(True)
            self.device_combo_user.setEnabled(True)
            self.channel_one_box.setEnabled(True)
            self.channel_two_box.setEnabled(True)
        elif combo_daq:
            if not self.channel_one_box.isChecked() and not self.channel_two_box.isChecked():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Error")
                msg.setInformativeText('Select a channel.')
                msg.setWindowTitle("Error")
                msg.exec_()
                self.startButton.setEnabled(True)
                self.startButton2.setEnabled(True)
                return
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ":  Reading sensor...")
            self.device_combo_sc.setEnabled(False)
            self.device_combo_user.setEnabled(False)
            self.channel_one_box.setEnabled(False)
            self.channel_two_box.setEnabled(False)

            self.setup_new_data()

            # self.x = []
            # self.y = []
            # self.data = pd.DataFrame(columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
            # self.timeCounter = Decimal('0.0')

            self.discard = True
            self.discard_counter = 9

            self.task = nidaqmx.Task()
            self.activeDAQ = True
            # print(self.system.devices)
            self.daq_device = self.system.devices[self.device_combo_sc.currentIndex()].name

            if self.channel_one_box.isChecked():
                channel = self.daq_device + "/ai2"
                # self.device = "Dev1/ai2"
                # print('Channel: ', channel)
                _ = self.task.ai_channels.add_ai_voltage_chan(channel)

                channel = self.daq_device + "/ai0"
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)

            if self.channel_two_box.isChecked():
                channel = self.daq_device + "/ai4"
                # self.device = "Dev1/ai2"
                # print('Channel: ', channel)
                _ = self.task.ai_channels.add_ai_voltage_chan(channel)

                channel = self.daq_device + "/ai5"
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)

            self.task.timing.cfg_samp_clk_timing(100, sample_mode=AcquisitionType.CONTINUOUS)
            self.task.register_every_n_samples_acquired_into_buffer_event(10, self.daq_callback)
            self.task.start()
            self.startButton.setText("Stop")
            self.startButton2.setText("Stop")

        if self.activeBLE:
            # print("Stop BLE")
            self.activeBLE = False
            array = QByteArray(b'\x00\x00')  # turn off NOTIFY for characteristic
            self.BLE_service.writeDescriptor(self.descriptor, array)  # turn off NOTIFY
            time.sleep(0.4)
            self.save_to_file()
            self.startButton.setText("Start")
            self.startButton2.setText("Start")
            self.device_combo_sc.setEnabled(True)
            self.device_combo_user.setEnabled(True)
        elif combo_ble:
            # print("Start BLE")
            self.device_combo_sc.setEnabled(False)
            self.device_combo_user.setEnabled(False)
            self.setup_new_data()
            # start receiving data from BLE
            self.BLE_service = self.controller.createServiceObject(self.BLE_UUID_service)
            self.BLE_service.error.connect(self.handleServiceError)
            if self.BLE_service is None:
                print("ERR: Cannot open service\n")
            print('Service name: ', self.BLE_service.serviceName())
            print('Service state: ', self.BLE_service.state())

            if self.BLE_service.state() == QtBt.QLowEnergyService.ServiceDiscovered:
                self.handleServiceOpened(self.BLE_service.state())

            elif self.BLE_service.state() == QtBt.QLowEnergyService.DiscoveryRequired:
                self.BLE_service.stateChanged.connect(self.handleServiceOpened)
                self.BLE_service.discoverDetails()
            else:
                print("Cannot discover service\n")
            self.startButton.setText("Stop")
            self.startButton2.setText("Stop")

            self.activeBLE = True

        self.startButton.setEnabled(True)
        self.startButton2.setEnabled(True)

    def setup_new_data(self):
        if self.activeBLE or self.activeBLE:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Data acquisition in progress.')
            msg.setWindowTitle("Error")
            msg.exec_()
            return
        self.x_channel_one = []
        self.y_channel_one = []
        self.xf_channel_one = []
        self.yf_channel_one = []
        self.x_channel_two = []
        self.y_channel_two = []
        self.xf_channel_two = []
        self.yf_channel_two = []
        self.data_channel_one = pd.DataFrame(
            columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
        self.data_channel_two = pd.DataFrame(
            columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
        self.timeCounter = Decimal('0.0')
        self.signalComm.request_graph_update.emit()

    def save_to_file(self):
        if self.activeBLE or self.activeBLE:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Data acquisition in progress.')
            msg.setWindowTitle("Error")
            msg.exec_()
            return
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                working_dir = config["working_dir"]
        except Exception as ex:
            print(ex)
            working_dir = ""
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        now = datetime.now()
        save_file_dialog = QFileDialog()
        # if self.channel_one_box.isChecked():
        if len(self.x_channel_one) > 0:
            filename, _ = save_file_dialog.getSaveFileName(
                self,
                "Save CSV File",
                working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' data1.csv',
                filter="All Files (*);;CSV Files (*.csv)",
                options=options
            )
            if filename:
                print('Saving to: ', filename)
                self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                self.data_channel_one.to_csv(filename, index=False)
                p = Path(filename)
                working_dir = str(p.parent) + "\\"

        # if self.channel_two_box.isChecked():
        if len(self.x_channel_two) > 0:
            filename, _ = save_file_dialog.getSaveFileName(
                self,
                "Save CSV File",
                working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' data2.csv',
                filter="All Files (*);;CSV Files (*.csv)",
                options=options
            )
            if filename:
                print('Saving to: ', filename)
                self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                self.data_channel_two.to_csv(filename, index=False)
                p = Path(filename)
                working_dir = str(p.parent) + "\\"

        config = {'working_dir': working_dir}
        with open('config.json', 'w') as f:
            json.dump(config, f)

    def update_combo(self):
        # print('Thread = {}          Function = updateCombo()'.format(threading.currentThread().getName()))
        combo_ble = False
        combo_daq = False
        for i in range(self.device_combo_sc.count()):
            if self.device_combo_sc.itemData(i) == "BLE":
                combo_ble = True
            if self.device_combo_sc.itemData(i) == "DAQ":
                combo_daq = True

        if len(self.system.devices) > 0 and not combo_daq:
            combo_daq = True
            self.timerCombo.setInterval(60000)

            for device in self.system.devices:
                now = datetime.now()
                self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") +
                                     ": Data acquisition system, model {0} detected.".format(device.product_type))
                self.device_combo_sc.addItem('DAQ: {0}'.format(device.product_type), "DAQ")
                self.device_combo_user.addItem('DAQ: {0}'.format(device.product_type), "DAQ")

        if not self.scanning:
            if self.BLE_device is not None:
                pass

        if not self.scanning and self.BLE_device is None and self.useBLE:
            pass
            print("combo, launch device_scan")
            self.scan_for_devices()

        if self.BLE_scan_complete and not combo_ble:
            combo_ble = True
            self.device_combo_sc.addItem('BLE: {0}'.format(self.controller.remoteName()), "BLE")
            self.device_combo_user.addItem('BLE: {0}'.format(self.controller.remoteName()), "BLE")
            self.timerCombo.setInterval(60000)

        if combo_ble or combo_daq:
            self.startButton.setEnabled(True)
            self.startButton2.setEnabled(True)
        else:
            self.startButton.setEnabled(False)
            self.startButton2.setEnabled(False)

        if combo_ble and combo_daq:
            self.timerCombo.stop()

        # # TODO: this code is for debug
        # self.startButton.setEnabled(True)

    def calibrateButtonClick(self):
        if len(self.x_channel_one) < 200:
            print("Need more data.")
            return

        # self.calibrateData = self.y_channel_one[-200:]
        # self.calibration = np.average(self.calibrateData)
        # self.calibrated = True

    def ScaleBoxChanged(self):
        # print(self.ScaleBox.isChecked())
        self.sliderX.setEnabled(not self.ScaleBox.isChecked())
        # if not self.sliderX.isEnabled():
        #     self.sliderX.set

    def device_combo_sc_changed(self):
        self.device_combo_user.setCurrentIndex(self.device_combo_sc.currentIndex())

    def device_combo_user_changed(self):
        self.device_combo_sc.setCurrentIndex(self.device_combo_user.currentIndex())

    def close_application(self):
        self.close()


pg.setConfigOptions(antialias=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")

# Now use a palette to switch to dark colors:
palette = QPalette()
palette.setColor(QPalette.Window, QColor(53, 53, 53))
palette.setColor(QPalette.WindowText, Qt.white)
palette.setColor(QPalette.Base, QColor(25, 25, 25))
palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
palette.setColor(QPalette.ToolTipBase, Qt.black)
palette.setColor(QPalette.ToolTipText, Qt.white)
palette.setColor(QPalette.Text, Qt.white)
palette.setColor(QPalette.Button, QColor(53, 53, 53))
palette.setColor(QPalette.ButtonText, Qt.white)
palette.setColor(QPalette.BrightText, Qt.red)
palette.setColor(QPalette.Link, QColor(42, 130, 218))
palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
palette.setColor(QPalette.HighlightedText, Qt.black)
app.setPalette(palette)
w = MainWindow()
w.show()
sys.exit(app.exec_())
