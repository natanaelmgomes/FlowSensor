from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSlot, QByteArray
from PyQt5.QtGui import QPalette, QColor, QFont
from PyQt5 import QtBluetooth as QtBt
from PyQt5.QtWidgets import (
    # QApplication,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QWidget,
    QComboBox,
    QSlider,
    QLCDNumber,
    QFileDialog,
    QCheckBox,
    QFrame,
)

# from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
import traceback
import sys
import struct
# import os
from random import random
import pandas as pd
import time
# from datetime import date
from datetime import datetime

import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration  # , TaskMode
from nidaqmx import system as daq_system

from decimal import Decimal
from collections import deque

from math import log, exp
import numpy as np
from scipy.fft import fft, fftfreq

import threading
import statistics

# import tensorflow as tf
# from tensorflow import keras

# from bleak import BleakScanner, BleakClient
# from bleak.backends.scanner import AdvertisementData
# from bleak.backends.device import BLEDevice


# SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
# # RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
# CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

SERVICE_UUID = "A7EA14CF-1000-43BA-AB86-1D6E136A2E9E"
CHAR_UUID = "A7EA14CF-1100-43BA-AB86-1D6E136A2E9E"

# All BLE devices have MTU of at least 23. Subtracting 3 bytes overhead, we can
# safely send 20 bytes at a time to any device supporting this service.
UART_SAFE_SIZE = 20


# gpus = tf.config.list_physical_devices('GPU')
# if gpus:
#   try:
#     # Currently, memory growth needs to be the same across GPUs
#     for gpu in gpus:
#       tf.config.experimental.set_memory_growth(gpu, True)
#     logical_gpus = tf.config.list_logical_devices('GPU')
#     print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
#   except RuntimeError as e:
#     # Memory growth must be set before GPUs have been initialized
#     print(e)


class WorkerSignals(QtCore.QObject):
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
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(tuple)
    result = QtCore.pyqtSignal(object)
    name = QtCore.pyqtSignal(str)
    data = QtCore.pyqtSignal(float)


class Worker(QtCore.QRunnable):
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
        except:
            traceback.print_exc()
            exc_type, value = sys.exc_info()[:2]
            self.signals.error.emit((exc_type, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


class SignalCommunicate(QtCore.QObject):
    # https://stackoverflow.com/a/45620056
    # got_new_sensor_data = QtCore.pyqtSignal(float, float)
    # position_updated = QtCore.pyqtSignal(float)
    request_graph_update = QtCore.pyqtSignal()


class MainWindow(QtWidgets.QMainWindow):
    BLE_characteristic_ready = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.system = daq_system.System.local()
        self.activeDAQ = False

        self.setWindowTitle("Data acquisition with National Instrument DAQ")

        self.mainLayout = QHBoxLayout()

        self.graphWidget = pg.PlotWidget()
        # self.graphWidget.getPlotItem().hideAxis('bottom')
        # self.graphWidget.getPlotItem().hideAxis('left')
        # self.setCentralWidget(generalLayout)

        self.fftWidget = pg.PlotWidget()
        # self.fftWidget.getPlotItem().hideAxis('bottom')
        # self.fftWidget.getPlotItem().hideAxis('left')

        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.graphWidget, 1)
        self.left_layout.addWidget(self.fftWidget, 1)

        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)
        # self.left_widget.setFixedWidth(100)
        self.mainLayout.addWidget(self.left_widget)
        # self.mainLayout.addWidget(self.graphWidget, 1)

        self.right_layout = QVBoxLayout()
        # self.lateral = QWidget()
        # self.right_layout.addWidget()

        self.combo = QComboBox(self)
        for device in self.system.devices:
            # print('Device Name: {0}, Product Category: {1}, Product Type: {2}'.format(
            #     device.name, device.product_category, device.product_type))
            self.combo.addItem('Name: {0}, Model: {1}'.format(device.name, device.product_type), "DAQ")

        self.b1 = QCheckBox("Save data")
        self.b1.setChecked(True)

        self.b2 = QCheckBox("Full scale")
        self.b2.setChecked(True)

        self.sliderX = QSlider(QtCore.Qt.Horizontal)
        self.sliderX.setTickInterval(10)
        self.sliderX.setSingleStep(1)
        self.sliderX.setValue(40)

        self.startButton = QPushButton("Start")
        self.startButton.pressed.connect(self.start_button_click)

        # self.buttonCharacteristic = QPushButton("Characteristic")
        # self.buttonCharacteristic.pressed.connect(self.CharacteristicButtonClick)

        self.buttonCalibrate = QPushButton("Calibrate")
        self.buttonCalibrate.pressed.connect(self.calibrateButtonClick)

        self.mainLabel = QLCDNumber()
        self.mainLabel.display('000')
        self.mainLabel.setDigitCount(3)
        # self.mainLabel.setStyleSheet('background-color:dark')
        self.mainLabel.setStyleSheet("QLCDNumber {color: red;}")
        # self.mainLabel.setMinimumSize(150, 100)
        # self.mainLabel.setFixedWidth(100)
        self.mainLabel.setFixedWidth(200)
        self.mainLabel.setFixedHeight(125)
        self.mainLabel.setFrameStyle(QFrame.NoFrame)
        self.mainLabel.setSegmentStyle(QLCDNumber.SegmentStyle(2))

        # add the elements to the window
        self.right_layout.addSpacing(10)
        self.right_layout.addWidget(self.mainLabel)
        self.right_layout.addSpacing(10)
        self.right_layout.addWidget(self.combo)
        self.right_layout.addStretch()
        self.right_layout.addWidget(self.b1)
        self.right_layout.addWidget(self.startButton)
        self.right_layout.addWidget(self.buttonCalibrate)
        # self.right_layout.addWidget(self.buttonCharacteristic)
        self.right_layout.addStretch()
        self.right_layout.addWidget(self.b2)
        self.right_layout.addWidget(self.sliderX)
        self.right_layout.addSpacing(10)
        # self.right_layout.setStretchFactor(0)

        self.right_layout.setAlignment(self.combo, QtCore.Qt.AlignTop)

        self.right_widget = QWidget()
        self.right_widget.setLayout(self.right_layout)
        self.right_widget.setFixedWidth(250)
        self.right_widget.setFont(QFont('Segoe', 9))
        # self.right_widget.setStyleSheet('.QLabel { font-size: 14pt;}')
        self.mainLayout.addWidget(self.right_widget)
        # self.mainLayout.addLayout(self.right_layout)

        # self.setLayout(self.mainLayout)
        # self.setCentralWidget(self.graphWidget)
        # self.setCentralWidget(self.mainLayout)

        ww = QWidget()
        ww.setLayout(self.mainLayout)
        self.setCentralWidget(ww)

        # Graph
        self.x = list(range(256))  # 100 time points
        self.y = [random() * 256 for _ in range(256)]  # 100 data points
        # self.graphWidget.setBackground('w')

        pen = pg.mkPen(color=(255, 20, 20))
        self.data_line = self.graphWidget.plot(self.x, self.y, pen=pen)

        # FFT
        self.N = 256
        self.T = 1.0 / 10.0
        self.yf = fft(self.y)
        self.xf = fftfreq(self.N, self.T)[:self.N // 2]

        # print(self.yf)
        # self.fft_line = self.fftWidget.plot(self.xf, 2.0/self.N * np.abs(self.yf[0:self.N//2]), pen=pen)
        # print(self.xf)
        # print(self.yf)

        self.fft_line = self.fftWidget.plot(self.xf[0:self.N // 10 + 1],
                                            1.0 / self.N * np.abs(self.yf[0:self.N // 2])[0:self.N // 10 + 1],
                                            pen=pen)

        # self.timer = QtCore.QTimer(self)
        # self.timer.setInterval(50)
        # self.timer.timeout.connect(self.update_plot_data)
        # # self.timer.start()
        # self.activeRandom = False

        print(self.children())

        self.timerCombo = QtCore.QTimer(self)
        self.timerCombo.setInterval(500)
        self.timerCombo.timeout.connect(self.updateCombo)
        self.timerCombo.start()

        self.daq_device = None
        self.maxX = None
        self.deviceText = None
        self.task = None

        self.data = pd.DataFrame(columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
        self.timeCounter = Decimal('0.0')

        # print(threading.currentThread().getName())
        self.signalComm = SignalCommunicate()
        self.signalComm.request_graph_update.connect(self.update_graph)

        # Calibration

        self.calibrated = False
        self.calibrateData = 0

        # just test
        # delta = int(2.1)
        # # delta = int(delta)
        # self.mainLabel.display(delta)

        # Tensorflow
        # self.model = tf.keras.models.load_model('D:/RUG/Dev/Notebooks/models/2021-10-19 first working model')
        # self.model.summary()
        self.values_deque = deque()
        # end Tensorflow

        # BLE
        # print('Thread = {}          Function = init()'.format(threading.currentThread().getName()))
        self.activeBLE = False
        self.BLE_device = None
        self.BLE_scan_complete = False
        self.BLE_service = None
        self.BLE_UUID_service = None
        self.BLE_UUID_characteristic = None
        self.BLE_characteristic = None
        self.controller = None
        self.serviceUid = None
        self.agent = QtBt.QBluetoothDeviceDiscoveryAgent(self)
        self.agent.deviceDiscovered.connect(self.discovered_device)
        self.agent.finished.connect(self.deviceScanDone)
        self.agent.error.connect(self.deviceScanError)
        self.agent.setLowEnergyDiscoveryTimeout(2000)
        self.scanning = False
        self.BLE_scan_complete = False
        self.scan_for_devices()
        self.itemService = []
        self.BLE_characteristic_ready.connect(self.characteristic_ready)
        # end BLE

    def discovered_device(self, *args, **kwargs):
        pass

    @pyqtSlot(QtBt.QBluetoothDeviceDiscoveryAgent.Error)
    def deviceScanError(self, error: QtBt.QBluetoothDeviceDiscoveryAgent.Error):
        # print('Thread = {}          Function = deviceScanError()'.format(threading.currentThread().getName()))
        print(error)

    @pyqtSlot()
    def deviceScanDone(self):
        # print('Thread = {}          Function = deviceScanDone()'.format(threading.currentThread().getName()))
        print("Device scan done.")
        for obj in self.agent.discoveredDevices():
            try:
                uuids, completeness = obj.serviceUuids()
                for uuid in uuids:
                    # print(uuid)
                    if SERVICE_UUID.lower() in uuid.toString():
                        print("FOUND", uuid.toString(), ' in ', obj.name())
                        self.BLE_device = obj
                        self.BLE_UUID_service = uuid
            except Exception as e:
                print(e)
        if self.BLE_device is not None:
            print('Attempt to connect to device: ', self.BLE_device.name())
            self.controller = QtBt.QLowEnergyController.createCentral(self.BLE_device)
            self.controller.connected.connect(self.deviceConnected)
            self.controller.disconnected.connect(self.deviceDisconnected)
            self.controller.error.connect(self.errorReceived)
            self.controller.serviceDiscovered.connect(self.addLEservice)
            self.controller.discoveryFinished.connect(self.serviceScanDone)
            self.controller.setRemoteAddressType(QtBt.QLowEnergyController.PublicAddress)
            self.controller.connectToDevice()
        else:
            print("Service not found.")
        self.scanning = False

    @pyqtSlot()
    def scan_for_devices(self):
        # print('Thread = {}          Function = scan_for_devices()'.format(threading.currentThread().getName()))
        self.BLE_scan_complete = False

        self.scanning = True
        self.agent.start()

    @pyqtSlot()
    def deviceConnected(self):
        print("Device connected.")  # debug
        self.controller.discoverServices()

    # @pyqtSlot()
    def addLEservice(self, servUid):  # debugging purpose function, can delete later
        # print("Found service {0}.".format(servUid.toString()))
        pass

    # @pyqtSlot()
    def errorReceived(self, error):
        print('BLE controller error: ', error)

    # @pyqtSlot()
    def deviceDisconnected(self):
        print("Device disconnected")
        self.BLE_device = None
        self.BLE_service = None
        self.BLE_characteristic = None

    @pyqtSlot()
    def serviceScanDone(self):
        print("Service scan done.")

        for servicesUids in self.controller.services():
            self.ble_service_uuid = QtBt.QBluetoothUuid(servicesUids)
            print(self.ble_service_uuid.toString())
            self.foundService = self.controller.createServiceObject(self.ble_service_uuid)
            if self.foundService == None:
                print("Not created", self.ble_service_uuid.toString())
            self.itemService.append(self.ble_service_uuid)

        # print(self.itemService)
        self.BLE_scan_complete = True

        # for serv in self.controller.services():
        #     print(serv)
        #     if UART_SERVICE_UUID.lower() in serv.toString():
        #         service = serv
        # # service = self.controller.services()[0]
        # print(service)
        #
        # # self.BLE_service = self.controller.createServiceObject(QtBt.QBluetoothUuid(self.BLE_UUID_service)) #
        # # self.BLE_service = self.controller.createServiceObject(QtBt.QBluetoothUuid(UART_SERVICE_UUID.lower())) #
        # self.BLE_service = self.controller.createServiceObject(service)  #
        # print(self.BLE_service)
        # print(self.BLE_service.serviceUuid())
        # # print(self.BLE_UUID_service)  # print(self.openedService.serviceName() + '\n')
        # print('State: ', self.BLE_service.state(), 'Name: ', self.BLE_service.serviceName())
        #
        # if self.BLE_service.state() == QtBt.QLowEnergyService.ServiceDiscovered:
        #     print('Service Discovered')
        #     self.handleServiceOpened()
        #
        # elif self.BLE_service.state() == QtBt.QLowEnergyService.DiscoveryRequired:
        #     print('Discovery Required')
        #     self.BLE_service.stateChanged.connect(self.handleServiceOpened)
        #     self.BLE_service.error.connect(self.handleServiceError)
        #     self.BLE_service.discoverDetails()

        # print(self.controller)
        # QtBt.QLowEnergyController.services()
        # self.servicesFound.emit()
        # self.controllerOutputMessage.emit(">>Services scan done\n")

    # @pyqtSlot()
    # def readService(self, ble_service_UID):
    #     self.openedService = self.controller.createServiceObject(ble_service_UID)
    #     if self.openedService == None:
    #         print("ERR: Cannot open service\n")
    #     print(self.openedService.serviceName() + '\n')
    #
    #     if (self.openedService.state() == QtBt.QLowEnergyService.ServiceDiscovered):
    #         self.handleServiceOpened()
    #
    #     elif (self.openedService.state() == QtBt.QLowEnergyService.DiscoveryRequired):
    #         self.openedService.stateChanged.connect(self.handleServiceOpened)
    #         self.openedService.discoverDetails()
    #     else:
    #         print("Cannot discover service\n")

    # @pyqtSlot()
    def handleServiceOpened(self, state):
        # if (self.openedService.state() == QtBt.QLowEnergyService.ServiceDiscovered):
        #     self.serviceOpened.emit()
        print('Service state: ', self.BLE_service.state())
        if self.BLE_service.state() == QtBt.QLowEnergyService.ServiceDiscovered:
            print('Characteristics:')
            for characteristic in self.BLE_service.characteristics():
                print(characteristic)
                print(characteristic.uuid().toString())
                if CHAR_UUID.lower() in characteristic.uuid().toString():
                    self.BLE_characteristic = characteristic

            print(self.BLE_characteristic)

            self.BLE_characteristic_ready.emit()

    @pyqtSlot()
    def characteristic_ready(self):
        # Notify
        self.type = QtBt.QBluetoothUuid(QtBt.QBluetoothUuid.ClientCharacteristicConfiguration)
        self.descriptor = self.BLE_characteristic.descriptor(self.type)
        # self.descriptor = self.BLE_characteristic.descriptors()[0]
        self.array = QByteArray(b'\x01\x00')  # turn on NOTIFY for characteristic
        self.BLE_service.characteristicChanged.connect(self.ble_callback)
        self.BLE_service.writeDescriptor(self.descriptor, self.array)  # turn on NOTIFY

    def ble_callback(self, characteristic, ble_data_byte_array):
        # print('BLE callback')
        # print(characteristic)
        # print(ble_data_byte_array)
        print(struct.unpack('f', ble_data_byte_array.data()))

        # array = QByteArray(b'\x01\x00')
        # print(array.data().decode(float))

    # @pyqtSlot()
    # def disconnect(self):
    #     self.controller.disconnectFromDevice()

    # @pyqtSlot()
    def handleServiceError(self, error):
        # if (self.openedService.state() == QtBt.QLowEnergyService.ServiceDiscovered):
        #     self.serviceOpened.emit()
        print('Service error: ', error)

    @pyqtSlot()
    def update_graph(self):
        # print('Thread = {}          Function = update_graph()'.format(threading.currentThread().getName()))
        self.data_line.setData(self.x, self.y)  # Update the data.
        # self.fft_line.setData(self.xf, 2.0 / self.N * np.abs(self.yf[0:self.N // 2]))
        self.fft_line.setData(self.xf[0:self.N // 10 + 1],
                              1.0 / self.N * np.abs(self.yf[0:self.N // 2])[0:self.N // 10 + 1])

    # @pyqtSlot()
    # def update_plot_data(self):
    #     # print('Thread = {}          Function = update_plot_data()'.format(threading.currentThread().getName()))
    #     self.maxX = (self.sliderX.value() + 1) * 6
    #     # print(self.sliderX.value())
    #     while len(self.x) > self.maxX:
    #         self.x = self.x[1:]  # Remove the first y element.
    #         self.y = self.y[1:]  # Remove the first
    #
    #     if len(self.x) == 0:
    #         self.x.append(0)
    #     else:
    #         self.x.append(self.x[-1] + 1)  # Add a new value 1 higher than the last.
    #     value = random() * 5
    #     self.y.append(value)  # Add a new random value.
    #
    #     datapoint = {'timestamp': round(time.time() * 1000),
    #                  'time': self.timeCounter,
    #                  'flow_voltage': random(),
    #                  'temp_voltage': random(),
    #                  'temperature': random()}
    #     self.data = self.data.append(datapoint, ignore_index=True)
    #     self.timeCounter += Decimal('0.1')
    #     self.graphWidget.setYRange(-10, 10)
    #
    #     # FFT
    #     # print(len(self.x))
    #     if len(self.x) > self.N:
    #         # print("here")
    #         y = self.x[-self.N:]
    #         self.yf = fft(y)
    #         self.xf = fftfreq(self.N, self.T)[:self.N // 2]
    #         self.fft_line.setData(self.xf, 2.0 / self.N * np.abs(self.yf[0:self.N // 2]))
    #
    #     self.signalComm.request_graph_update.emit()

    def add_data_point(self, flow_voltage, temp_voltage=None):
        if len(self.x) == 0:
            self.x.append(0)
        else:
            self.x.append(self.x[-1] + 1)  # Add a new value 1 higher than the last.

        # self.y = self.y[1:]  # Remove the first
        self.y.append(flow_voltage)  # Add a new random value.

        if not self.b2.isChecked():
            self.maxX = (self.sliderX.value() + 1) * 6
            while len(self.x) > self.maxX:
                self.x = self.x[1:]  # Remove the first y element.
                self.y = self.y[1:]  # Remove the first

        # self.signalComm.request_graph_update.emit() # in the end
        # self.data_line.setData(self.x, self.y)  # Update the data.

        # Improve the scale of the graph
        maxy = max(self.y)
        miny = min(self.y)
        nn = 1.5
        maxy *= nn
        miny *= nn
        maxabs = max([abs(maxy), abs(miny)])
        # self.graphWidget.setYRange(-maxabs, maxabs)

        # calculate the temperature
        beta = 3760
        resistance = 9990 / ((5 / temp_voltage) - 1)
        temperature = beta / log(resistance / (12000 * exp(- beta / 298.15))) - 273.15

        datapoint = {'timestamp': round(time.time() * 1000),
                     'time': self.timeCounter,
                     'flow_voltage': flow_voltage,
                     'temp_voltage': temp_voltage,
                     'temperature': temperature}
        self.data = self.data.append(datapoint, ignore_index=True)
        self.timeCounter += Decimal('0.1')

        # FFT
        if len(self.x) > self.N:
            y = self.y[-self.N:]
            y = y - np.average(y)
            self.yf = fft(y)
            self.xf = fftfreq(self.N, self.T)[:self.N // 2]
            # self.fft_line.setData(self.xf, 2.0 / self.N * np.abs(self.yf[0:self.N // 2]))
            r = max(1.0 / self.N * np.abs(self.yf[0:self.N // 2])[0:self.N // 10 + 1])
            if r < 0.02:
                self.fftWidget.setYRange(0, 0.02)
            else:
                self.fftWidget.setYRange(0, r)

    def daq_callback(self, task_handle, every_n_samples_event_type,
                     number_of_samples, callback_data):
        # print('Thread = {}          Function = daq_callback()'.format(threading.currentThread().getName()))

        try:
            sample = self.task.read(number_of_samples_per_channel=10)
            flow_voltage = 1000 * sum(sample[0]) / len(sample[0])
            temp_voltage = sum(sample[1]) / len(sample[1])
        except Exception as err:
            print("Error" + err)
            # self.task = None
            return 0

        # datapoint = {'timestamp':, 'time', 'voltage'}

        # self.x = self.x[1:]  # Remove the first y element.

        # Tensorflow
        # if len(self.x) > 1024:
        #     if len(self.x) % 5 == 0:
        #         chunk = np.array(self.y[-1024:])
        #         value = float(self.model.predict(chunk.reshape((1, 1024))))
        #         self.values_deque.append(value)
        #
        #         if len(self.values_deque) > 20: self.values_deque.popleft()
        #
        #         values = list(self.values_deque)
        #         values.sort()
        #         values = values[3:17]
        #
        #         value = np.mean(values)
        #         if (value < 0): value = 0
        #         value = int(value)
        #         self.mainLabel.display(value)

        self.signalComm.request_graph_update.emit()

        # calibration on voltage delta
        # if self.calibrated:
        #     lastData = np.average(self.y[-20:])
        #     # print(lastData)
        #     delta = int(abs(lastData - self.calibration))
        #
        #     # show in the panel
        #     self.mainLabel.display(delta)

        return 0

    @pyqtSlot()
    def start_button_click(self) -> None:

        self.deviceText = self.combo.currentText()
        if self.deviceText == "":
            return

        print(self.combo.currentData())
        if self.combo.currentData() == 'BLE':
            combo_ble = True
            combo_daq = False
        elif self.combo.currentData() == 'DAQ':
            combo_daq = True
            combo_ble = False
        else:
            combo_ble = False
            combo_daq = False

        if not combo_ble and not combo_daq:
            return

        if self.activeDAQ:
            print("Stop DAQ")
            self.activeDAQ = False
            self.task.stop()
            self.task.close()

            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog
            now = datetime.now()
            filename, _ = QFileDialog.getSaveFileName(self, "Save CSV File",
                                                      now.strftime("%Y-%m-%d %H-%M-%S") + ' data.csv',
                                                      "All Files (*);;CSV Files (*.csv)", options=options)
            if filename:
                print(filename)

                self.data.to_csv(filename, index=False)
            self.startButton.setText("Start")
            self.combo.setEnabled(True)
        elif combo_daq:
            print("Start DAQ")
            self.combo.setEnabled(False)
            self.x = []
            self.y = []
            self.data = pd.DataFrame(columns=['timestamp', 'time', 'flow_voltage', 'temp_voltage', 'temperature'])
            self.timeCounter = Decimal('0.0')

            self.task = nidaqmx.Task()
            self.activeDAQ = True
            self.daq_device = self.system.devices[self.combo.currentIndex()].name
            channel = self.daq_device + "/ai2"
            # self.device = "Dev1/ai2"
            print('Channel: ', channel)
            self.main_channel = self.task.ai_channels.add_ai_voltage_chan(channel)

            channel = self.daq_device + "/ai0"
            self.temp_channel = self.task.ai_channels.add_ai_voltage_chan(channel,
                                                                          terminal_config=TerminalConfiguration.RSE)

            self.task.timing.cfg_samp_clk_timing(100, sample_mode=AcquisitionType.CONTINUOUS)
            self.task.register_every_n_samples_acquired_into_buffer_event(10, self.daq_callback)
            self.task.start()
            self.startButton.setText("Stop")

        if self.activeBLE:
            # save data from BLE
            print("Stop BLE")
        elif combo_ble:
            print("Start BLE")
            # start receiving data from BLE
            self.BLE_service = self.controller.createServiceObject(self.BLE_UUID_service)
            self.BLE_service.error.connect(self.handleServiceError)
            if self.BLE_service == None:
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

    @pyqtSlot()
    def updateCombo(self):
        # print('Thread = {}          Function = updateCombo()'.format(threading.currentThread().getName()))
        combo_ble = False
        combo_daq = False
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == "BLE":
                combo_ble = True
            if self.combo.itemData(i) == "DAQ":
                combo_daq = True
        # self.deviceText = self.combo.currentText()
        if len(self.system.devices) > 0 and not combo_daq:

            # self.combo.clear()
            self.timerCombo.setInterval(60000)
            for device in self.system.devices:
                # print(device)
                # print('Device Name: {0}, Product Category: {1}, Product Type: {2}'.format(
                #     device.name, device.product_category, device.product_type))
                self.combo.addItem('Name: {0}, Model: {1}'.format(device.name, device.product_type), "DAQ")

        # self.deviceText = self.combo.currentText()
        if len(self.system.devices) == 0:
            self.startButton.setEnabled(False)
            self.timerCombo.setInterval(500)

        # BLE
        if not self.scanning:
            if self.BLE_device is not None:
                pass

        if not self.scanning and self.BLE_device is None:
            print("combo, launch device_scan")
            self.scan_for_devices()

        if self.BLE_scan_complete and not combo_ble:
            self.combo.addItem('BLE: {0}'.format(self.controller.remoteName()), "BLE")
            pass

        if combo_ble or combo_daq:
            self.startButton.setEnabled(True)

        if combo_ble and combo_daq:
            self.timerCombo.stop()

    def calibrateButtonClick(self):
        if len(self.x) < 200:
            print("Need more data.")
            return

        self.calibrateData = self.y[-200:]
        self.calibration = np.average(self.calibrateData)
        self.calibrated = True


app = QtWidgets.QApplication(sys.argv)
app.setStyle("Fusion")

# Now use a palette to switch to dark colors:
palette = QPalette()
palette.setColor(QPalette.Window, QColor(53, 53, 53))
palette.setColor(QPalette.WindowText, QtCore.Qt.white)
palette.setColor(QPalette.Base, QColor(25, 25, 25))
palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
palette.setColor(QPalette.ToolTipBase, QtCore.Qt.black)
palette.setColor(QPalette.ToolTipText, QtCore.Qt.white)
palette.setColor(QPalette.Text, QtCore.Qt.white)
palette.setColor(QPalette.Button, QColor(53, 53, 53))
palette.setColor(QPalette.ButtonText, QtCore.Qt.white)
palette.setColor(QPalette.BrightText, QtCore.Qt.red)
palette.setColor(QPalette.Link, QColor(42, 130, 218))
palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
palette.setColor(QPalette.HighlightedText, QtCore.Qt.black)
app.setPalette(palette)
w = MainWindow()
w.show()
sys.exit(app.exec_())
