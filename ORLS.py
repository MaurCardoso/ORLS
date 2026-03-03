# === Graphical User Interface (GUI) libraries ===
# PyQt6 is used to build the desktop application that controls the Arduino device
# and displays the optical scattering signal in real time.
import os, sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QThread, pyqtSignal
# === GUI layout generated from Qt Designer ===
# The file 'Ventana_principal.py' is automatically created from a .ui design file.
# It contains the graphical structure of the main control panel.
from Main_Window import Ui_Dialog
# === Scientific computing and visualization ===
# NumPy is used for numerical handling of the acquired kinetic data.
import numpy as np
# Matplotlib is used to plot scattering intensity vs time during silica gelation.
import matplotlib.pyplot as plt
# === Data export utilities ===
# CSV library allows saving experimental runs into spreadsheet-compatible files.
import csv
# === Serial communication with Arduino ===
# PySerial provides the communication layer between the PC software and the Arduino,
# enabling real-time acquisition and control through JSON-based messages.
import serial
import serial.tools.list_ports
# === JSON message handling ===
# The Arduino and PC exchange structured commands and measurement packets using JSON.
import json
# === Additional utilities ===
# Threading and timing modules support background acquisition tasks
# without freezing the graphical interface.
import threading
import time
# Path compatible con PyInstaller

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# === Global connection and system state variables ===
# These flags are used to track whether the Arduino device is currently connected
# and whether an acquisition session is running.
ConnectionWithArduino = False
m = 0
arduino = False

# === Photodiode channel data structure ===
# Each optical detector (TSL2561 channel) is represented as an object containing:
# - current measurement state (active/inactive)
# - channel number
# - sample/cell identifier
# - default directory for data storage
# - acquired kinetic data (time vs scattering intensity)
class Photodiodes(): 
    def __init__(self, statePh, number, sampleNamePh, savePathPh, dataPh):
        self.state = statePh  # Measurement status (True = active)
        self.n = number  # Channel index
        self.name = sampleNamePh # Sample or cell name
        self.save = savePathPh # Output directory for saved data
        self.data = dataPh # Data buffer for recorded measurements

# === Initialization of the four sensor channels ===
# The device supports up to four independent photodiode detectors,
# corresponding to four sample positions (cells).
Photodiode_1 = Photodiodes(False, 1, "cell 1", "./data/", [])
Photodiode_2 = Photodiodes(False, 2, "cell 2", "./data/", [])
Photodiode_3 = Photodiodes(False, 3, "cell 3", "./data/", [])
Photodiode_4 = Photodiodes(False, 4, "cell 4", "./data/", [])

# === Channel registry ===
# A list is created to manage all photodiode objects together.
# Each entry links the photodiode object with its corresponding channel number.
Photodiodes_List = [
    [Photodiode_1, 1],
    [Photodiode_2, 2],
    [Photodiode_3, 3],
    [Photodiode_4, 4],
]

# === Default acquisition parameters ===
# These arrays store the measurement configuration for each channel:
# - total cycle duration
# - sampling interval
# - sensor integration time
# Values can be updated dynamically through the GUI and transmitted to Arduino.
Cycle_Time = [10, 10, 10, 10]
Interval_Time = [500, 500, 500, 500]
Integration_Time = [20, 20, 20, 20]

# === User interface messages ===
# Startup text displayed in the GUI, including software version information.
message = "Welcome to Open-source Real-time Light Scattering system (ORLS)"
message2 = "Version 3.0 February 2026 \n ___________________________________________________________ \n "
message3 = None

# === Background communication thread (Arduino ↔ PC interface) ===
# This QThread runs independently from the main GUI in order to:
# - continuously listen to incoming serial messages from Arduino
# - decode the JSON-based communication protocol
# - update the graphical interface without blocking user interaction
# The thread handles multiple message types, including:
# - connection status
# - photodiode activation states
# - acquisition timing parameters
# - real-time measurement data (gelation kinetics)
class ArduinoThread(QThread):
     # === Qt signals emitted to the main GUI ===
    # These signals allow safe communication between the background thread
    # and the graphical interface.
    message_received = pyqtSignal(str)  # General monitor messages
    status_changed_Connection = pyqtSignal() # Arduino connection state updated
    message2_received = pyqtSignal(str) # Secondary status messages
    message3_received = pyqtSignal(str) # Additional timing/configuration messages
    status_changed_Photodiode = pyqtSignal() # Photodiode state updated

    def __init__(self, arduino_serial):
        super().__init__()
         # Serial object representing the active Arduino connection
        self.arduino_serial = arduino_serial
    
    def run(self):
        #Main execution loop of the communication thread.
        #While the Arduino connection remains active, the thread continuously:
        #- waits for incoming JSON messages from the microcontroller
        #- classifies them according to the 'label' field
        #- triggers the corresponding GUI updates
        global ConnectionWithArduino, m, message, message2, message3
        while ConnectionWithArduino == True:
            try:
                # Read one complete line from the serial buffer
                message_Arduino = self.arduino_serial.readline().decode().strip()
                if message_Arduino:
                    # Incoming messages are encoded as JSON objects
                    data = json.loads(message_Arduino)
                    # Extract message fields from the JSON protocol
                    label = data.get("label", "")
                    sublabel = data.get("sublabel", "")
                    value = data.get("value", "")
                    # === Message type 1: Arduino connection status ===
                    if label == "State":
                        # 'value' indicates whether Arduino is ready or disconnected
                        m = value
                        if value == 1:
                            message = "Arduino ready \n"
                        elif value == 0:
                            message = "Arduino disconnected \n"
                            ConnectionWithArduino = False
                        else:
                            message = "Connection error"
                        # Send status update to the GUI monitor
                        self.message_received.emit(message)
                        # Notify the interface that connection state has changed
                        self.status_changed_Connection.emit()
                    # === Message type 2: Photodiode measurement state ===    
                    elif label == "PhotodiodeStatus":
                       # Arduino reports whether a given photodiode channel is active
                       message2 = "The measurement in the photodiode " + str(sublabel + 1) + " is: " + str(value) + "\n"
                       # Emit message to the GUI
                       self.message2_received.emit(message2)
                       # Update internal photodiode registry (active/inactive)
                       self.Find_Modify_Ph(photodiode=sublabel + 1, state=value)
                       # Notify GUI elements that sensor state has changed
                       self.status_changed_Photodiode.emit()
                     # === Message type 3: Timing configuration feedback ===
                    elif label == "Times":
                        # Arduino confirms updated acquisition parameters
                        if sublabel == 0:
                            message = "The cycle time was establishhed at: " + str(value) + "\n"
                            self.message_received.emit(message)
                        elif sublabel == 1:
                            message2 = "The interval time was established: " + str(value) + "\n"
                            self.message2_received.emit(message2)
                        else:
                            message3 = "The integration time was established: " + str(value) + "\n"
                            self.message3_received.emit(message3)
                    # === Message type 4: Real-time measurement data ===        
                    elif label == "Data":
                       # Each data message contains:
                        # - elapsed time since measurement start
                        # - raw light scattering intensity (TSL2561 channel output)
                       message = "Data was received from photodiode " + str(sublabel + 1) + ": " + str(value) + "\n"
                       # Display acquisition feedback in the GUI
                       self.message_received.emit(message)

                       # Append the measurement point to the corresponding channel dataset
                       self.save_Data(photodiode=sublabel + 1, dat=value)
                else: pass
            except Exception as e:
                self.message_received.emit(f"Serial comunication error")
                # Communication errors are caught to avoid crashing the GUI thread
        
    # === Data storage helper ===
    # Appends new measurement points into the correct photodiode data buffer
    def save_Data(self, photodiode, dat):
        global Photodiodes_List
        for row in Photodiodes_List:
            if row[1] == photodiode:
                # Each channel stores kinetic data as a growing list
                row[0].data.append(dat)

    # === Sensor state update helper ===
    # Updates the internal activation state of a given photodiode channel
    def Find_Modify_Ph(self, photodiode, state):
        global Photodiodes_List, message
        for row in Photodiodes_List:
            if row[1] == photodiode:
                # Store whether the channel is currently acquiring data
                row[0].state = state
                        

# === Main application window (Graphical User Interface) ===
# This class defines the primary PyQt5 interface used to control the device.
# It integrates:
# - Arduino serial communication
# - Multi-channel photodiode control (5 independent cells)
# - Real-time acquisition parameter configuration
# - Data visualization and monitoring tools
class MiApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # === Load the GUI layout designed in Qt Designer ===
        # Ui_Dialog is the auto-generated class containing all widgets
        # (buttons, text fields, spin boxes, monitor panel, etc.) 
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)
        self.setWindowIcon(QIcon(resource_path("ORLS.ico")))
        # Display startup messages in the GUI monitor console
        self.ui.Monitor.append(message)
        self.ui.Monitor.append(message2)
        # === Arduino connection initialization ===
        # Automatically detect the correct serial port and establish communication
        port_name = self.detect_Arduino()
        self.arduino_serial = serial.Serial(port_name, 9600)
        # Initial state: connection marked as inactive until handshake is complete
        self.ui.ConnectionInactive.setChecked(True)
         # === General Arduino control buttons ===
        # These buttons allow the user to start or stop communication with the device
        self.ui.ConnectArduino.clicked.connect(lambda: self.connect_Arduino())
        self.ui.DisconnectArduino.clicked.connect(lambda: self.disconnect_Arduino())
        # === Photodiode acquisition control (5 independent channels) ===
        # Each cell can be started or stopped individually from the interface
        self.ui.StartPh1.clicked.connect(lambda: self.start_Measurement(photodiode_Start= 1))
        self.ui.StopPh1.clicked.connect(lambda: self.stop_Measurement(photodiode_Stop= 1))
        self.ui.StartPh2.clicked.connect(lambda: self.start_Measurement(photodiode_Start= 2))
        self.ui.StopPh2.clicked.connect(lambda: self.stop_Measurement(photodiode_Stop= 2))
        self.ui.StartPh3.clicked.connect(lambda: self.start_Measurement(photodiode_Start= 3))
        self.ui.StopPh3.clicked.connect(lambda: self.stop_Measurement(photodiode_Stop= 3))
        self.ui.StartPh4.clicked.connect(lambda: self.start_Measurement(photodiode_Start= 4))
        self.ui.StopPh4.clicked.connect(lambda: self.stop_Measurement(photodiode_Stop= 4))
         # === Real-time plotting windows ===
        # Each channel has an associated plotting button to visualize
        # gelation kinetics (scattering intensity vs time)
        self.ui.GraphsPh1.clicked.connect( lambda: self.openPlot_Window(n= 1))
        self.ui.GraphsPh2.clicked.connect( lambda: self.openPlot_Window(n= 2))
        self.ui.GraphsPh3.clicked.connect( lambda: self.openPlot_Window(n= 3))
        self.ui.GraphsPh4.clicked.connect( lambda: self.openPlot_Window(n= 4))
        # === Sample naming fields ===
        # The user can assign a custom identifier to each measurement cell.
        # These names are stored in the corresponding Fotodiodo object.
        widget_SampleName_map = {
            self.ui.SamplePh1: Photodiode_1,
            self.ui.SamplePh2: Photodiode_2,
            self.ui.SamplePh3: Photodiode_3,
            self.ui.SamplePh4: Photodiode_4,
        }
        for widget, photodiode in widget_SampleName_map.items():
            widget.textChanged.connect( lambda w=widget.text(), p=photodiode: self.Read_Name(w, p))
        # === Output directory fields ===
        # Each channel can be configured with an independent saving path,
        # enabling automatic export of kinetic datasets.
        widget_SavePhotodiode_map = {
            self.ui.SavePh1: Photodiode_1,
            self.ui.SavePh2: Photodiode_2,
            self.ui.SavePh3: Photodiode_3,
            self.ui.SavePh4: Photodiode_4,
        }
        for widget, photodiode in widget_SavePhotodiode_map.items():
            widget.textChanged.connect( lambda w=widget.text(), p=photodiode: self.read_Path(w,p))
        # === Acquisition cycle duration controls ===
        # Spin boxes allow the user to configure the total acquisition time
        # for each photodiode channel.
        widget_timeCycle_map = {
            self.ui.CycleTimePh1: 0,
            self.ui.CycleTimePh2: 1,
            self.ui.CycleTimePh3: 2,
            self.ui.CycleTimePh4: 3,
        }
        for widget, photodiode in widget_timeCycle_map.items():
            widget.valueChanged.connect( lambda time=widget.value(), p=photodiode: self.set_CycleTime(p, time))
        # === Sampling interval controls ===
        # Defines how frequently scattering intensity is recorded during gelation.
        widget_timeInterval_map = {
            self.ui.IntervalTimePh1: 0,
            self.ui.IntervalTimePh2: 1,
            self.ui.IntervalTimePh3: 2,
            self.ui.IntervalTimePh4: 3,
        }
        for widget, photodiode in widget_timeInterval_map.items():
            widget.valueChanged.connect( lambda time=widget.value(), p=photodiode: self.set_TimeInterval(p, time))
        # === Sensor integration time controls ===
        # Controls the photodiode exposure/integration time,
        # affecting sensitivity and noise level.
        widget_timeIntegration_map = {
            self.ui.IntegrationTimePh1: 0,
            self.ui.IntegrationTimePh2: 1,
            self.ui.IntegrationTimePh3: 2,
            self.ui.IntegrationTimePh4: 3,
        }
        for widget, photodiode in widget_timeIntegration_map.items():
            widget.valueChanged.connect( lambda time=widget.value(), p=photodiode: self.set_TimeIntegration(p, time))
    
    # === Acquisition parameter setters ===
    # These methods update the local configuration arrays for each channel.
    # Values are later transmitted to Arduino to control measurement timing.
    def set_TimeIntegration(self, p, time):
        #Update the sensor integration time for channel f.
        #Integration time affects the exposure duration of the photodiode sensor.
        Integration_Time[p] = time

    
    def set_TimeInterval(self, p, time):
        #Update the sampling interval for channel f.
        #This defines how frequently scattering intensity measurements are recorded.
        Interval_Time[p] = time

    
    def set_CycleTime(self, p, time):
        #Update the total acquisition cycle duration for channel f.
        #This sets the overall monitoring time for a gelation experiment.
        Cycle_Time[p] = time


    # === Start Arduino communication thread ===
    # This method creates and launches the background QThread responsible for:
    # - continuously reading incoming serial JSON messages
    # - updating GUI monitor panels
    # - synchronizing sensor states in real time
    def read_Arduino(self):
            global message2, message, message3
            # Instantiate the communication thread using the active serial connection
            self.arduino_thread = ArduinoThread(self.arduino_serial)
            # Connect thread signals to GUI update functions
            self.arduino_thread.message_received.connect(self.update_Monitor1)
            self.arduino_thread.message2_received.connect(self.update_Monitor2)
            self.arduino_thread.message3_received.connect(self.update_Monitor3)
            # Connection and sensor state feedback
            self.arduino_thread.status_changed_Connection.connect(self.ConnectionStatus)
            self.arduino_thread.status_changed_Photodiode.connect(self.update_Check)
            # Start asynchronous serial monitoring
            self.arduino_thread.start()

    # === GUI monitor update helpers ===
    # These methods append status messages to the monitor console inside the interface.
    def update_Monitor1(self):
        global message
        self.ui.Monitor.append(message)
    def update_Monitor2(self):
        global message2
        self.ui.Monitor.append(message2)
    def update_Monitor3(self):
        global message3
        self.ui.Monitor.append(message3)

    # === Automatic Arduino port detection ===
    # This function scans all available serial ports and identifies Arduino-compatible
    # devices based on common USB-to-serial descriptors
    # This improves usability by removing the need for manual port selection.
    def detect_Arduino(self):
        global message, arduino
        # List all serial ports available on the system
        ports = list(serial.tools.list_ports.comports())
        arduino_detected = False
        Port = None 
        for port in ports:
            # Convert port description to lowercase for robust matching
            descripcion = port.description.lower()
            # Check for typical Arduino/USB-serial identifiers
            if ("usb serial" in descripcion or
                "ch340" in descripcion or
                "arduino" in descripcion or
                "cp210" in descripcion or
                "ftdi" in descripcion 
                ):
                message = "Arduino was detected on " + str(port.device) + "\n"
                arduino_detected = True
                Port = port.device
                arduino = arduino_detected
                break
         # Display detection results in the GUI monitor
        if arduino_detected == True:
            self.ui.Monitor.append(message)
        else:
            message = "Arduino was not detected"
            self.ui.Monitor.append(message)
        return Port

    # === Plotting and visualization tools ===
    # These methods allow the user to open a real-time or post-acquisition plot
    # for any of the five photodiode channels.
    # The stored dataset corresponds to gelation kinetics:
    # scattering intensity signal as a function of elapsed time.
    def openPlot_Window(self, n):
        #Open the plotting window for photodiode channel n.
        #The method retrieves the stored kinetic dataset from the corresponding
        #Fotodiodo object and calls the plotting routine.
        global Photodiodes_List
        DATA = []
        # Search the internal registry to locate the selected photodiode
        for row in Photodiodes_List:
            if row[1] == n:
                 # Extract recorded measurements (time, intensity)
                DATOS = row[0].data
                break
        # Generate plots from the retrieved dataset
        self.updatePlots(DATOS = DATOS)

    def updatePlots(self, DATOS):
        global message
        #Generate kinetic plots for the selected dataset.
        #Two complementary visualizations are provided:
        #1) Scattering intensity vs time (gelation curve)
        #2) Smoothed first derivative (gelation rate)
        #A Savitzky–Golay filter is applied to reduce the step-like effect
        #caused by integer quantization of Arduino measurements.
        if not DATOS:
            return
        # === Extract time and signal values ===
        x = np.array([item[0] for item in DATOS])  # elapsed time (ms)
        y = np.array([item[1] for item in DATOS])  # scattering signal (raw units)
        # === Create a two-panel figure ===
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        # ------------------------------------------------------------
        # Plot 1: Scattering intensity vs time
        # ------------------------------------------------------------
        # Convert time from milliseconds to hours for readability
        x_hours = x / 3600000
        ax1.scatter(x_hours, y, color="black")
        ax1.set_xlabel("Time (h)")
        ax1.set_ylabel("Scattering Signal (a.u.)")
        ax1.set_title("Signal Evolution")
        # ------------------------------------------------------------
        # Plot 2: Smoothed first derivative (gelation rate)
        # ------------------------------------------------------------
        # Default derivative array (fallback)
        dy_dx = np.zeros_like(y)
        # Only compute derivative if enough points exist
        if len(y) >= 7:
            from scipy.signal import savgol_filter
            # === Dynamic window size selection ===
            # Window must be odd and smaller than dataset length
            window = min(len(y)//10, 70)
            if window % 2 == 0:
                window += 1
            # Ensure minimum valid size
            if window < 7:
                window = 7   
            # Compute average sampling step (ms)
            delta_t = np.mean(np.diff(x))
            # Savitzky–Golay derivative (1st order)
            dy_dx = savgol_filter(
                y,
                window_length=window,
                polyorder=2,
                deriv=1,
                delta=delta_t
            )
        else:
            message = "Not enough data points for derivative smoothing."
            self.ui.Monitor.append(message)
        # Plot derivative
        ax2.plot(x_hours, dy_dx)
        ax2.set_xlabel("Time (h)")
        ax2.set_ylabel("dS/dt (a.u. h⁻¹)")
        ax2.set_title("Smoothed 1st Derivative")
        # ------------------------------------------------------------
        # Final formatting
        # ------------------------------------------------------------
        plt.tight_layout()
        plt.show()

    # === Sample metadata update methods ===
    # These functions synchronize GUI input fields with the internal
    # photodiode objects (sample name and saving directory).
    def Read_Name(self, widget, photodiode):
        #Update the sample/cell name associated with a photodiode channel.
        photodiode.name = widget

    def read_Path(self, widget, photodiode):
        #Update the output directory where experimental data will be saved.
        photodiode.save = widget
    
        # === Arduino communication handshake ===
        # This method activates the serial communication protocol.
        # It sends a JSON command to Arduino indicating that the PC software
        # is ready to begin acquisition and monitoring.
   
    def connect_Arduino(self):
        global ConnectionWithArduino, arduino
        if ConnectionWithArduino == False and arduino == True:
            # Enable communication flag
            ConnectionWithArduino = True
             # Send initialization message through the JSON protocol
            StartComunication = {
                "label": "Comunication",
                "sublabel": 1,
                "value": 1
            }
            JsonComunication =  json.dumps(StartComunication) + "\n"
            self.arduino_serial.write(JsonComunication.encode())
            # Start the background serial reading thread
            self.read_Arduino()
        else: pass

    # === GUI connection status indicators ===
    # Updates the checkboxes showing whether Arduino is:
    # - connected and ready
    # - disconnected
    # - in an error state
    def ConnectionStatus(self):
        global m
        if m == 1:
            # Connection active
            self.ui.ConnectionInactive.setChecked(False)   
            self.ui.ConnectionActive.setChecked(True)
            self.ui.ConnectionError.setChecked (False)
        elif m == -1:
            # Connection error
            self.ui.ConnectionInactive.setChecked(False)   
            self.ui.ConnectionActive.setChecked(False)
            self.ui.ConnectionError.setChecked (True)
        else: 
            # Default: inactive
            self.ui.ConnectionInactive.setChecked(True)   
            self.ui.ConnectionActive.setChecked(False)
            self.ui.ConnectionError.setChecked (False)

    def start_Measurement(self, photodiode_Start):
    #Starts data acquisition for a selected photodiode sensor.
    #This function sends three configuration parameters to the Arduino:
    #    - Cycle duration
    #    - Measurement interval
    #    - Integration time
    #Finally, it sends the start command for the sensor.
        global Photodiodes_List
        for row in Photodiodes_List:
            # Check if sensor matches the requested ID and is currently inactive
            if row[1] == photodiode_Start and row[0].state == False:
                # --- Send cycle time ---
                timeCycle = {
                    "label": "Cycle",
                    "sublabel": photodiode_Start - 1,
                    "value": Cycle_Time[photodiode_Start - 1]
                }
                JsonCycle =  json.dumps(timeCycle) + "\n"
                self.arduino_serial.write(JsonCycle.encode())
                # --- Send interval time ---
                timeInterval = {
                    "label": "Interval",
                    "sublabel": photodiode_Start -1,
                    "value": Interval_Time[photodiode_Start - 1]
                }
                JsonInterval =  json.dumps(timeInterval) + "\n"
                self.arduino_serial.write(JsonInterval.encode())
                # --- Send integration time ---
                timeIntegration = {
                    "label": "Integration",
                    "sublabel": photodiode_Start -1,
                    "value": Integration_Time[photodiode_Start - 1]
                }
                JsonIntegration =  json.dumps(timeIntegration) + "\n"
                self.arduino_serial.write(JsonIntegration.encode())
                # --- Start sensor acquisition ---
                Start = {
                    "label": "Sensor",
                    "sublabel": photodiode_Start -1,
                    "value": 1
                }
                JsonStart =  json.dumps(Start) + "\n"
                self.arduino_serial.write(JsonStart.encode())        

    def update_Check(self):
            #Updates the GUI checkboxes according to the current state of each photodiode.
            self.ui.ActivedPh1.setChecked(Photodiode_1.state)
            self.ui.ActivedPh2.setChecked(Photodiode_2.state)
            self.ui.ActivedPh3.setChecked(Photodiode_3.state)
            self.ui.ActivedPh4.setChecked(Photodiode_4.state)

    def stop_Measurement(self, photodiode_Stop):
        #Stops the acquisition for a selected sensor.
        #The function sends the stop command to Arduino,
        #saves the collected dataset into a CSV file,
        #and clears the sensor buffer.
        global Photodiodes_List
        for row in Photodiodes_List:
            if row[1] == photodiode_Stop:
                 # --- Stop sensor on Arduino side ---
                Stop = {
                    "label": "Sensor",
                    "sublabel": photodiode_Stop -1,
                    "value": 0
                }
                JsonStop =  json.dumps(Stop) + "\n"
                self.arduino_serial.write(JsonStop.encode())
                # Save acquired data
                self.saveData_csv(photodiode_Save=row[0])
                row[0].data = []

    def saveData_csv(self, photodiode_Save):
        #Saves the acquired sensor data into a tab-separated CSV file.
        #Output format:
        #Time (ms) vs Signal
        global message
        name_archive = photodiode_Save.save + "/" + photodiode_Save.name + ".csv"
        with open(name_archive, 'w', newline='') as archive_csv:
            write_csv = csv.writer(archive_csv, delimiter= '\t')
            # Header row
            write_csv.writerow(['Time (ms)','Signal']) 
            # Data rows
            for row in photodiode_Save.data:
                write_csv.writerow(row)
        message = "Successful saved of " + photodiode_Save.name + ".csv"
        self.ui.Monitor.append(message)
        message = str(photodiode_Save.data) + "\n"
        self.ui.Monitor.append(message)

    def disconnect_Arduino(self):
        #Sends a stop communication command to Arduino.
        global ConnectionWithArduino
        if ConnectionWithArduino == True:
            Start_comunication = {
                "label": "Comunication",
                "sublabel": 1,
                "value": 0
            }
            JsonComunication =  json.dumps(Start_comunication) + "\n"
            self.arduino_serial.write(JsonComunication.encode())
        
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtCore import Qt
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("ORLS.ico")))
    # ================================
    # Force Fusion Style (Cross-platform)
    # ================================
    app.setStyle("Fusion")
    # ================================
    # Dark Palette (Fixed Dark Mode)
    # ================================
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(180, 30, 30))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    # Apply palette
    app.setPalette(dark_palette)
    # ================================
    # Launch Main Window
    # ================================
    Main_Window = MiApp()
    Main_Window.show()

    sys.exit(app.exec())
