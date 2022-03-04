import constants, filters

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

from scipy.optimize import curve_fit
from scipy.optimize import OptimizeWarning
from scipy import signal
import warnings
import json

import timeit

import logging
import os

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
        except Exception as err:
            print(err)
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
    button_report = None
    startButton = None
    startButton2 = None
    device_combo_sc = None
    device_combo_user = None
    ScaleBox = None
    bleBox = None
    SaveBox = None
    raw_data_box = None
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
    base_voltage_box = None
    drop_voltage_box = None
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
    filename = None
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

        logging.debug("Initialization.")

        ''' Design main window '''
        self.resize(1920, 1080)
        self.icon_logo = QIcon('imgs/Sencilia-Logo-RGB-darkblue-cropped2.jpg')
        self.setWindowIcon(self.icon_logo)
        self.setWindowTitle("Sencilia Flow Sensor")
        self._create_menu_bar()
        widget = QWidget()
        self.main_layout = QStackedLayout(widget)
        self.set_main_layout(self.main_layout)
        self.setCentralWidget(widget)

        ''' NI DAQ '''
        self.system = daq_system.System.local()
        self.zi_1 = [None, None, None, None, None, None, None, None, None, None, None, None]
        self.zi_2 = [None, None, None, None, None, None, None, None, None, None, None, None]
        self.zi_3 = [None, None, None, None, None, None, None, None, None, None, None, None]
        self.tempos = []

        ''' Raw data '''
        self.raw_data_channel_one = []
        self.raw_data_channel_two = []

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
        self.yf_channel_one = fft(self.y_channel_one, constants.FFT_N2)
        self.yf_channel_one = 2.0 / constants.FFT_N1 * np.abs(self.yf_channel_one[0:constants.FFT_N2 // 2])
        self.xf_channel_one = fftfreq(constants.FFT_N2, constants.SAMPLING_RATE)[:constants.FFT_N2 // 2]
        self.fft_line_channel_one = self.fftWidget.plot(
            self.xf_channel_one[0:constants.FFT_N2 // 7 + 1],
            self.yf_channel_one[0:constants.FFT_N2 // 7 + 1],
            pen=pg.mkPen(color=(255, 20, 20, 255))
        )
        self.fft_line_channel_two = self.fftWidget.plot(
            list(np.linspace(
                0,
                self.xf_channel_one[0:constants.FFT_N2 // 7 + 1][-1],
                len(self.xf_channel_one[0:constants.FFT_N2 // 7 + 1]))),
            [random() * 32 + 16 for _ in range(len(self.xf_channel_one[0:constants.FFT_N2 // 7 + 1]))],
            pen=pg.mkPen(color=(20, 255, 20, 255))
        )

        ''' Timer '''
        self.timerCombo = QTimer(self)
        self.timerCombo.setInterval(500)
        self.timerCombo.timeout.connect(self.update_combo)
        self.timerCombo.start()

        self.timeCounter = Decimal('0.0')
        self.signalComm = SignalCommunicate()
        self.signalComm.request_graph_update.connect(self.update_graph)
        self.last_flow = time.time() - 11

        ''' Calibration '''
        self.calibrateData = 0

        ''' Flow estimation through frequency components '''
        self.values_deque = deque()

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

    def set_main_layout(self, layout):
        scientific = self.scientific_widget()
        user = self.user_widget()

        layout.addWidget(scientific)
        layout.addWidget(user)

    def scientific_widget(self):
        scientific_widget = QWidget(self)
        scientific_layout = QHBoxLayout(scientific_widget)

        self.graphWidget = pg.PlotWidget()
        self.fftWidget = pg.PlotWidget()
        # self.fftWidget.getPlotItem().hideAxis('bottom')
        # self.fftWidget.getPlotItem().hideAxis('left')

        self.p1 = self.graphWidget.plotItem
        vb = self.p1.getViewBox()
        self.p2 = pg.ViewBox()
        self.p1.showAxis('right')
        self.p1.scene().addItem(self.p2)
        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
        self.p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(self.p1)

        self._update_graph_views()
        self.p1.vb.sigResized.connect(self._update_graph_views)

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

        self.raw_data_box = QCheckBox("Save raw data")
        self.raw_data_box.setChecked(False)

        self.sliderX = QSlider(Qt.Horizontal)
        self.sliderX.setTickInterval(10)
        self.sliderX.setSingleStep(1)
        self.sliderX.setValue(40)
        self.sliderX.setEnabled(False)

        self.ScaleBox = QCheckBox("Full scale")
        self.ScaleBox.stateChanged.connect(self.scale_box_changed)
        self.ScaleBox.setChecked(True)

        self.startButton = QPushButton("Start")
        self.startButton.pressed.connect(self.start_button_click)

        self.button_report = QPushButton("Report")
        self.button_report.pressed.connect(self.report_button_click)

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
        right_layout.addWidget(self.button_report)
        right_layout.addWidget(self.SaveBox)
        right_layout.addWidget(self.raw_data_box)
        right_layout.addStretch()
        right_layout.addWidget(self.ScaleBox)
        right_layout.addWidget(self.sliderX)
        right_layout.addSpacing(10)
        right_layout.setAlignment(self.device_combo_sc, Qt.AlignTop)

        scientific_layout.addWidget(right_widget)
        return scientific_widget

    def user_widget(self):
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

    def _update_graph_views(self):
        try:
            # view has resized; update auxiliary views to match
            self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
            # p3.setGeometry(p1.vb.sceneBoundingRect())

            # need to re-update linked axes since this was called
            # incorrectly while views had different shapes.
            # (probably this should be handled in ViewBox.resizeEvent)
            self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
            # p3.linkedViewChanged(p1.vb, p3.XAxis)
        except Exception as err:
            logging.exception("_update_graph_views error: %s", str(err))

    def _create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        self.new_action = QAction('&New', self)
        self.new_action.setShortcut('Ctrl+N')
        self.new_action.triggered.connect(self.setup_new_data)
        file_menu.addAction(self.new_action)
        self.open_action = QAction('&Open', self)
        self.open_action.setShortcut('Ctrl+O')
        self.open_action.triggered.connect(self.open_data)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        # file_menu.addAction(QAction('', self).setSeparator(True))
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
            logging.exception("ble_callback error: %s", str(err))
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
        try:
            # print('Thread = {}          Function = update_graph()'.format(threading.currentThread().getName()))
            # if self.channel_one_box.isChecked():
            self.data_line_channel_one.setData(self.x_channel_one, self.y_channel_one)  # Update the data.
            # self.fft_line.setData(self.xf, 2.0 / constants.FFT_N1 * np.abs(self.yf[0:constants.FFT_N1 // 2]))
            self.fft_line_channel_one.setData(self.xf_channel_one[0:constants.FFT_N2 // 7 + 1],
                                              self.yf_channel_one[0:constants.FFT_N2 // 7 + 1])

            # if self.channel_two_box.isChecked():
            self.data_line_channel_two.setData(self.x_channel_two, self.y_channel_two)  # Update the data.
            # self.fft_line.setData(self.xf, 2.0 / constants.FFT_N1 * np.abs(self.yf[0:constants.FFT_N1 // 2]))
            self.fft_line_channel_two.setData(self.xf_channel_two[0:constants.FFT_N2 // 7 + 1],
                                              self.yf_channel_two[0:constants.FFT_N2 // 7 + 1])

            # TODO: improve scale
            # if len(self.y_channel_one) > 2:
            #     self.p1.setYRange(min(self.y_channel_one), max(self.y_channel_one))
        except Exception as err:
            logging.exception("update_graph error: %s", str(err))

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
                self.x_channel_one.append(self.x_channel_one[-1] + 0.1)
            self.y_channel_one.append(flow_voltage_one)
            if not self.ScaleBox.isChecked():
                while len(self.x_channel_one) > self.maxX:
                    self.x_channel_one = self.x_channel_one[1:]
                    self.y_channel_one = self.y_channel_one[1:]
            beta = 3760
            try:
                resistance = 9990 / ((5 / temp_voltage_one) - 1)
                temperature = beta / log(resistance / (12000 * exp(- beta / 298.15))) - 273.15
            except Exception as err:
                logging.exception("math error: %s", str(err))
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
                self.yf_channel_one = fft(y * constants.KAISER_WINDOW, constants.FFT_N2)
                self.yf_channel_one = 2.0 / constants.FFT_N1 * np.abs(self.yf_channel_one[0:constants.FFT_N2 // 2])
                self.xf_channel_one = fftfreq(constants.FFT_N2, constants.SAMPLING_RATE)[:constants.FFT_N2 // 2]
                r1 = max(self.yf_channel_one[0:constants.FFT_N2 // 7 + 1])

        if data_two is not None:
            flow_voltage_two, temp_voltage_two = data_two
            if len(self.x_channel_two) == 0:
                self.x_channel_two.append(0)
            else:
                self.x_channel_two.append(self.x_channel_two[-1] + 0.1)
            self.y_channel_two.append(flow_voltage_two)
            if not self.ScaleBox.isChecked():
                while len(self.x_channel_two) > self.maxX:
                    self.x_channel_two = self.x_channel_two[1:]
                    self.y_channel_two = self.y_channel_two[1:]
            beta = 3950
            try:
                resistance = 9980 / ((5 / temp_voltage_two) - 1)
                temperature = beta / log(resistance / (10000 * exp(- beta / 298.15))) - 273.15
            except Exception as err:
                logging.exception("math error: %s", str(err))
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
                self.yf_channel_two = fft(y * constants.KAISER_WINDOW, constants.FFT_N2)
                self.yf_channel_two = 2.0 / constants.FFT_N1 * np.abs(self.yf_channel_two[0:constants.FFT_N2 // 2])
                self.xf_channel_two = fftfreq(constants.FFT_N2, constants.SAMPLING_RATE)[:constants.FFT_N2 // 2]
                r2 = max(self.yf_channel_two[0:constants.FFT_N2 // 7 + 1])

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

        ''' Flow estimation through frequency components '''

        def freq_to_flow(frequency):
            return frequency / 0.001251233545

        # 0.00123995
        # 0.001251233545

        if len(self.x_channel_one) > constants.FFT_N1:
            yf = np.copy(self.yf_channel_one)
            value = False
            peaks, properties = signal.find_peaks(yf, constants.MIN_PEAKS)
            if len(properties['peak_heights']) > 0:
                index_max = np.argmax(properties['peak_heights'])
                if peaks[index_max] < 30:
                    properties['peak_heights'] = np.delete(properties['peak_heights'], index_max)
                    peaks = np.delete(peaks, index_max)
                    if len(properties['peak_heights']) > 0:
                        index_max = np.argmax(properties['peak_heights'])
                        # print("Removed the first peak, peak: ", peaks[index_max], " Frequency: ",
                        #       peaks[index_max] / constants.FFT_N2, " Flow: ",
                        #   freq_to_flow((peaks[index_max] / constants.FFT_N2) / constants.SAMPLING_RATE))
                        value = freq_to_flow((peaks[index_max] / constants.FFT_N2) / constants.SAMPLING_RATE)
                    else:
                        # print("Removed the only peak.")
                        value = np.NAN
                else:
                    # print("Using the first peak, peak: ", peaks[index_max], " Frequency: ",
                    #       peaks[index_max] / constants.FFT_N2, " Flow: ",
                    #       freq_to_flow((peaks[index_max] / constants.FFT_N2) / constants.SAMPLING_RATE))
                    value = freq_to_flow((peaks[index_max] / constants.FFT_N2) / constants.SAMPLING_RATE)
            else:
                # print("There are no peaks.")
                value = np.NAN

            # if not value:
            #     for j in range(int(0.00067138 * constants.FFT_N2) + 1):
            #         yf[j] = 0.0
            #     index_max = np.argmax(yf)
            #     value = freq_to_flow(index_max * constants.SAMPLING_RATE / constants.FFT_N2)

            self.values_deque.append(value)

            if len(self.values_deque) > constants.MAX_DEQUE_SIZE:
                self.values_deque.popleft()

        ''' Flow detection '''

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
            except OptimizeWarning as err:
                logging.exception("OptimizeWarning error: %s", str(err))
            except Exception as err:
                logging.exception("Generic error in curve estimation: %s", str(err))

            # DEBUG
            # self.flow_detected = True

        self.signalComm.request_graph_update.emit()

    def daq_callback(self, task_handle, every_n_samples_event_type, number_of_samples, callback_data):
        # print('Thread = {}          Function = daq_callback()'.format(threading.currentThread().getName()))
        # DEBUG
        start_time = timeit.default_timer()
        try:
            sample = self.task.read(number_of_samples_per_channel=1_000)
            i = 0
            if self.channel_one_box.isChecked():
                self.raw_data_channel_one.extend(sample[i])

            if self.channel_two_box.isChecked():
                i += 2
                self.raw_data_channel_two.extend(sample[i])

            for i in range(len(sample)):
                sample[i], self.zi_1[i] = filters.decimate(sample[i], 10, zi=self.zi_1[i])
                sample[i], self.zi_2[i] = filters.decimate(sample[i], 10, zi=self.zi_2[i])
                sample[i], self.zi_3[i] = filters.decimate(sample[i], 10, zi=self.zi_3[i])
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
            logging.exception("daq_callback error: : %s", str(err))
        self.tempos.append(timeit.default_timer() - start_time)
        if len(self.tempos) % 600 == 0:
            logging.debug("[DAQ processing time] Mean: {:.4f}s, Deviation: {:.2e}s, Max: {:.4f}s".format(
                np.mean(self.tempos), np.std(self.tempos), max(self.tempos)))
            self.tempos = []
        return 0

    def check_flow(self):
        if self.flow_detected:
            now = datetime.now()
            if len(self.values_deque) > 20:
                std_value = np.std(self.values_deque)
                mean_value = np.mean(self.values_deque)
                std_over_mean = abs(std_value / mean_value)
                logging.debug("[FLOW ESTIMATION] std: {:.2f}, mean: {:.2f}, ratio: {:.2f}".format(
                    std_value, mean_value, std_over_mean))
            else:
                std_over_mean = 10

            if std_over_mean > 0.5 or np.isnan(np.sum(self.values_deque)):
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
                    value = np.mean(values)
                    value = 0 if value < 0 else value
                    value = round(value)
                    self.flow_label.display(value)
                    self.flow_label2.display(value)
                except Exception as err:
                    logging.exception("flow calculation error: : %s", str(err))
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
        logging.debug("start_button_click called.")
        self.deviceText = self.device_combo_sc.currentText()
        if self.deviceText == "":
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('No device available.')
            msg.setWindowTitle("Error")
            msg.exec_()
            logging.debug("There is no device connected. Returning from start_button_click.")
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
            logging.debug("Stop DAQ data acquisition.")

            self.save_to_file()

            self.startButton.setText("Start")
            self.startButton2.setText("Start")
            self.device_combo_sc.setEnabled(True)
            self.device_combo_user.setEnabled(True)
            self.channel_one_box.setEnabled(True)
            self.channel_two_box.setEnabled(True)
            self.raw_data_box.setEnabled(True)
        elif combo_daq:
            if not self.channel_one_box.isChecked() and not self.channel_two_box.isChecked():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Error")
                msg.setInformativeText('Select at least one channel.')
                msg.setWindowTitle("Error")
                msg.exec_()
                self.startButton.setEnabled(True)
                self.startButton2.setEnabled(True)
                logging.debug("No channel selected. Returning from start_button_click.")
                return
            self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ":  Reading sensor...")
            self.device_combo_sc.setEnabled(False)
            self.device_combo_user.setEnabled(False)
            self.channel_one_box.setEnabled(False)
            self.channel_two_box.setEnabled(False)
            self.raw_data_box.setEnabled(False)

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
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)

                channel = self.daq_device + "/ai0"
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)

            if self.channel_two_box.isChecked():
                channel = self.daq_device + "/ai4"
                # self.device = "Dev1/ai2"
                # print('Channel: ', channel)
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)

                channel = self.daq_device + "/ai5"
                _ = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                              terminal_config=TerminalConfiguration.RSE)
                # DEBUG
            self.task.timing.cfg_samp_clk_timing(10_000, sample_mode=AcquisitionType.CONTINUOUS)
            self.task.register_every_n_samples_acquired_into_buffer_event(1_000, self.daq_callback)
            self.task.start()
            logging.debug("Start DAQ data acquisition.")
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
            logging.debug("Stop BLE data acquisition.")
            self.device_combo_sc.setEnabled(True)
            self.device_combo_user.setEnabled(True)
            self.raw_data_box.setEnabled(True)
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
            # print('Service name: ', self.BLE_service.serviceName())
            # print('Service state: ', self.BLE_service.state())

            if self.BLE_service.state() == QtBt.QLowEnergyService.ServiceDiscovered:
                self.handleServiceOpened(self.BLE_service.state())

            elif self.BLE_service.state() == QtBt.QLowEnergyService.DiscoveryRequired:
                self.BLE_service.stateChanged.connect(self.handleServiceOpened)
                self.BLE_service.discoverDetails()
            else:
                print("Cannot discover service\n")

            logging.debug("Start BLE data acquisition.")
            self.startButton.setText("Stop")
            self.startButton2.setText("Stop")
            self.raw_data_box.setEnabled(False)

            self.activeBLE = True

        self.startButton.setEnabled(True)
        self.startButton2.setEnabled(True)

    def setup_new_data(self):
        logging.debug("setup_new_data called.")
        if self.activeBLE or self.activeDAQ:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Data acquisition in progress.')
            msg.setWindowTitle("Error")
            msg.exec_()
            logging.debug("Data acquisition in progress. Returning from setup_new_data.")
            return
        self.x_channel_one = []
        self.y_channel_one = []
        self.xf_channel_one = []
        self.yf_channel_one = []
        self.x_channel_two = []
        self.y_channel_two = []
        self.xf_channel_two = []
        self.yf_channel_two = []

        ''' Raw data '''
        self.raw_data_channel_one = []
        self.raw_data_channel_two = []

        self.filename = None
        if self.base_voltage_box is not None:
            self.base_voltage_box.setData([], [])
        if self.drop_voltage_box is not None:
            self.drop_voltage_box.setData([], [])
        self.data_channel_one = pd.DataFrame(
            columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
        self.data_channel_two = pd.DataFrame(
            columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
        self.timeCounter = Decimal('0.0')
        self.signalComm.request_graph_update.emit()
        logging.debug("setup_new_data returning.")

    def save_to_file(self):
        logging.debug("save_to_file called.")
        if self.activeBLE or self.activeBLE:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Data acquisition in progress.')
            msg.setWindowTitle("Error")
            msg.exec_()
            logging.debug("Data acquisition in progress. Returning from save_to_file.")
            return
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                working_dir = config["working_dir"]
        except Exception as err:
            logging.exception("No configuration file found. %s", str(err))
            working_dir = ""
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        now = datetime.now()
        save_file_dialog = QFileDialog()
        if len(self.x_channel_one) > 0:
            filename, _ = save_file_dialog.getSaveFileName(
                self,
                "Save CSV File",
                working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' data1.csv',
                filter="All Files (*);;CSV Files (*.csv)",
                options=options
            )
            if filename:
                logging.debug("Saving to: {0}".format(str(filename)))
                self.filename = filename
                self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                self.data_channel_one.to_csv(filename, index=False)
                p = Path(filename)
                working_dir = str(p.parent) + "\\"
            else:
                logging.debug("Not saving file 1.")

        if len(self.x_channel_two) > 0:
            filename, _ = save_file_dialog.getSaveFileName(
                self,
                "Save CSV File",
                working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' data2.csv',
                filter="All Files (*);;CSV Files (*.csv)",
                options=options
            )
            if filename:
                logging.debug("Saving to: {0}".format(str(filename)))
                # print('Saving to: ', filename)
                self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                self.data_channel_two.to_csv(filename, index=False)
                p = Path(filename)
                working_dir = str(p.parent) + "\\"
            else:
                logging.debug("Not saving file 2.")

            if len(self.raw_data_channel_one) > 0:
                filename, _ = save_file_dialog.getSaveFileName(
                    self,
                    "Save CSV File",
                    working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' raw data1.csv',
                    filter="All Files (*);;CSV Files (*.csv)",
                    options=options
                )
                if filename:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    logging.debug("Saving to: {0}".format(str(filename)))
                    # print('Saving to: ', filename)
                    self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                    raw_data_one = pd.DataFrame(
                        data=self.raw_data_channel_one,
                        columns=['flow_voltage'])
                    raw_data_one.to_csv(filename, index=False)
                    p = Path(filename)
                    working_dir = str(p.parent) + "\\"
                    QApplication.restoreOverrideCursor()
                else:
                    logging.debug("Not saving raw data file 1.")

            if len(self.raw_data_channel_two) > 0:
                filename, _ = save_file_dialog.getSaveFileName(
                    self,
                    "Save CSV File",
                    working_dir + now.strftime("%Y-%m-%d %H-%M-%S") + ' raw data2.csv',
                    filter="All Files (*);;CSV Files (*.csv)",
                    options=options
                )
                if filename:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    logging.debug("Saving to: {0}".format(str(filename)))
                    # print('Saving to: ', filename)
                    self.text_box.append(now.strftime("%Y-%m-%d %H:%M:%S") + ": Saving to: {0}".format(str(filename)))
                    raw_data_two = pd.DataFrame(
                        data=self.raw_data_channel_two,
                        columns=['flow_voltage'])
                    raw_data_two.to_csv(filename, index=False)
                    p = Path(filename)
                    working_dir = str(p.parent) + "\\"
                    QApplication.restoreOverrideCursor()
                else:
                    logging.debug("Not saving raw data file 2.")

            self.raw_data_channel_one = []
            self.raw_data_channel_two = []

        config = {'working_dir': working_dir}
        with open('config.json', 'w') as f:
            json.dump(config, f)
            logging.debug("Configuration file saved.")

    def open_data(self):
        logging.debug("open_data called.")
        if self.activeBLE or self.activeDAQ:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Data acquisition in progress.')
            msg.setWindowTitle("Error")
            msg.exec_()
            logging.debug("Data acquisition in progress, returning from open_data.")
            return

        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        filename, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                  "Data files (*.csv);;All Files (*)", options=options)

        if filename:
            logging.debug("filename: %s", filename)
            pd_file = pd.read_csv(filename)

            try:
                y = pd_file['flow_voltage']
            except KeyError as err:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Error")
                msg.setInformativeText('Incompatible file format.')
                msg.setWindowTitle("Error")
                msg.exec_()
                logging.exception("Incompatible file format. Exception: %s", str(err))
                return

            self.setup_new_data()

            self.x_channel_one = np.array(list(range(len(y)))) / 10
            self.y_channel_one = y

            self.filename = filename
            logging.debug("File loaded, updating graph.")

            self.signalComm.request_graph_update.emit()
        else:
            logging.debug("No file selected.")

    def update_combo(self):
        logging.debug("update_combo called.")
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

                logging.debug("Data acquisition system, model {0} detected.".format(device.product_type))

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

    def report_button_click(self):
        logging.debug("Report button pressed.")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        if len(self.x_channel_one) < 1:
            print("Need more data.")
            return

        def func(fx, fa, fb):
            return fa + fb * fx

        flow_detected_channel_1 = False
        starting_index_channel_1 = 0
        stopping_index_channel_1 = 0
        for i in range(len(self.y_channel_one) - constants.FLOW_DETECTION_BLOCK_LEN):
            cut = self.y_channel_one[i - constants.FLOW_DETECTION_BLOCK_LEN:i]
            if len(cut) < constants.FLOW_DETECTION_BLOCK_LEN:
                continue
            x = np.linspace(0, len(cut), len(cut))
            try:
                popt, pcov = curve_fit(func, x, cut)
            except OptimizeWarning as err:
                logging.exception("report_button_click OptimizeWarning error: %s", str(err))
            except Exception as err:
                logging.exception("report_button_click curve_fit error: %s", str(err))

            if popt[1] < constants.FLOW_START_NEG_THRESHOLD and not flow_detected_channel_1:
                flow_detected_channel_1 = True
                starting_index_channel_1 = i
            if popt[1] > constants.FLOW_STOP_POS_THRESHOLD:
                if flow_detected_channel_1: stopping_index_channel_1 = i
                break
                # flow_detected_channel_1 = False

        if starting_index_channel_1 == 0 or stopping_index_channel_1 == 0:
            QApplication.restoreOverrideCursor()
            logging.error("report_button_click flow not detected, starting_index_channel_1=%s, " +
                          "stopping_index_channel_1=%s  ", starting_index_channel_1, stopping_index_channel_1)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Error")
            msg.setInformativeText('Flow not detected on data.')
            msg.setWindowTitle("Error")
            msg.exec_()
            return

        base_start = starting_index_channel_1 - constants.BASE_VOLTAGE_START
        base_stop = starting_index_channel_1 - constants.BASE_VOLTAGE_STOP

        drop_start = starting_index_channel_1 + constants.DROP_VOLTAGE_START
        drop_stop = stopping_index_channel_1 - constants.DROP_VOLTAGE_STOP

        base_voltage_channel_1 = self.y_channel_one[base_start:base_stop]
        drop_voltage_channel_1 = self.y_channel_one[drop_start:drop_stop]

        avg_base = np.average(base_voltage_channel_1)
        avg_drop = np.average(drop_voltage_channel_1)

        voltage_drop = avg_base - avg_drop
        percentage_drop = 100 - ((avg_base / avg_drop) * 100)

        max_base_y = np.max(base_voltage_channel_1)
        max_base_x = np.argmax(base_voltage_channel_1) + base_start
        min_base_y = np.min(base_voltage_channel_1)
        min_base_x = np.argmin(base_voltage_channel_1) + base_start

        max_drop_y = np.max(drop_voltage_channel_1)
        max_drop_x = np.argmax(drop_voltage_channel_1)
        min_drop_y = np.min(drop_voltage_channel_1)
        min_drop_x = np.argmin(drop_voltage_channel_1)

        drop_range = np.abs(max_drop_y - min_drop_y)

        # Create the box around the data used to calculate the base voltage
        self.base_voltage_box = self.p1.plot(
            [base_start / 10, base_stop / 10, base_stop / 10, base_start / 10, base_start / 10],
            [min_base_y - 0.2, min_base_y - 0.2, max_base_y + 0.2, max_base_y + 0.2, min_base_y - 0.2],
            pen=pg.mkPen(color=(20, 255, 20))
        )
        # Create the box around the data used to calculate the drop voltage
        self.drop_voltage_box = self.p1.plot(
            [drop_start / 10, drop_stop / 10, drop_stop / 10, drop_start / 10, drop_start / 10],
            [min_drop_y - 0.2, min_drop_y - 0.2, max_drop_y + 0.2, max_drop_y + 0.2, min_drop_y - 0.2],
            pen=pg.mkPen(color=(20, 255, 20))
        )

        report_text = "{}\t{}\t{}\t{}\tauto\tauto\t{}\t{}\t{}".format(
            avg_base, avg_drop, voltage_drop, percentage_drop,
            max_drop_y, min_drop_y, drop_range)
        clipboard.setText(report_text)

        logging.info(
            "file: %s, avg_base: %s, avg_drop: %s, voltage_drop: %s, percentage_drop: %s, "
            "max_drop: %s, min_drop: %s, drop_range: %s",
            self.filename,
            avg_base,
            avg_drop,
            voltage_drop,
            percentage_drop,
            max_drop_y,
            min_drop_y,
            drop_range
        )
        QApplication.restoreOverrideCursor()
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText("Result")
        msg.setInformativeText('Data is on clipboard.')
        msg.setWindowTitle("Report")
        msg.exec_()

    def scale_box_changed(self):
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

    def closeEvent(self, event):

        if not self.activeDAQ and not self.activeBLE:
            event.accept()
            logging.debug("Exiting.")
            return

        quit_msg = "Are you sure you want to exit the program?"
        reply = QMessageBox.question(self, 'Message',
                                     quit_msg, QMessageBox.Yes, QMessageBox.No)

        if reply == QMessageBox.Yes:
            logging.debug("Canceling data acquisition and exiting.")
            self.task.stop()
            self.task.close()
            event.accept()
        else:
            logging.debug("Ignoring attempt to exit.")
            event.ignore()


try:
    os.mkdir("log")
except FileExistsError as ex:
    pass

logging.basicConfig(
    filename="log/log.txt",
    format='%(asctime)s: %(levelname)s - %(message)s',
    # format='%(asctime)s %(message)s',
    datefmt='%Y/%m/%d %I:%M:%S',
    # encoding='utf-8',
    level=logging.DEBUG
)

pg.setConfigOptions(antialias=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
clipboard = app.clipboard()

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
