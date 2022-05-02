from PyQt6.QtCore import pyqtSlot, QByteArray
from PyQt6 import QtBluetooth as QtBt

SERVICE_UUID = "A7EA14CF-1000-43BA-AB86-1D6E136A2E9E"
CHAR_UUID = "A7EA14CF-1100-43BA-AB86-1D6E136A2E9E"


def discovered_device(self, *args, **kwargs):
    pass


@pyqtSlot(QtBt.QBluetoothDeviceDiscoveryAgent.Error)
def deviceScanError(self, error: QtBt.QBluetoothDeviceDiscoveryAgent.Error):
    # print('Thread = {}          Function = deviceScanError()'.format(threading.currentThread().getName()))
    print('Device scan error: ', error)


@pyqtSlot()
def deviceScanDone(self):
    # print('Thread = {}          Function = deviceScanDone()'.format(threading.currentThread().getName()))
    print("Device scan done.")
    for obj in self.agent.discoveredDevices():
        try:
            #uuids, completeness = obj.serviceUuids()
            uuids = obj.serviceUuids()
            for uuid in uuids:
                #print(uuid)
                if SERVICE_UUID.lower() in uuid.toString():
                    print("FOUND", uuid.toString(), ' in ', obj.name())
                    self.BLE_device = obj
                    self.BLE_UUID_service = uuid
        except Exception as e:
            print(e)
    if self.BLE_device is not None:
        print('Attempt to connect to device: ', self.BLE_device.name())
        self.text_box.append(" > > >  Bluetooth device detected: {0} \n".format(str(self.BLE_device.name())))
        self.controller = QtBt.QLowEnergyController.createCentral(self.BLE_device)
        self.controller.connected.connect(self.deviceConnected)
        self.controller.disconnected.connect(self.deviceDisconnected)
        self.controller.errorOccurred.connect(self.errorReceived)
        self.controller.serviceDiscovered.connect(self.addLEservice)
        self.controller.discoveryFinished.connect(self.serviceScanDone)
        self.controller.setRemoteAddressType(QtBt.QLowEnergyController.RemoteAddressType.PublicAddress)
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


def addLEservice(self, servUid):  # debugging purpose function, can delete later
    # print("Found service {0}.".format(servUid.toString()))
    pass


def errorReceived(self, error):
    print('BLE controller error: ', error)


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
            print("Service not created", self.ble_service_uuid.toString())
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
    print('Service state: ', state)
    if self.BLE_service.state() == QtBt.QLowEnergyService.ServiceState.ServiceDiscovered:
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


def handleServiceError(self, error):
    # if (self.openedService.state() == QtBt.QLowEnergyService.ServiceDiscovered):
    #     self.serviceOpened.emit()
    print('Service error: ', error)