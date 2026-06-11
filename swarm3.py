import socket
import datetime
import re
import _thread
import time
import fcntl
import struct
import operator
import sys
import subprocess
import serial
import I2C_LCD_driver
import pytz
from functools import reduce

now = datetime.datetime.now(pytz.timezone('UTC'))
LogFileName = "/home/pi/Logs/SwarmLog_" + now.strftime("%d-%m-%y_%H-%M-%S") + ".txt"

def SaveToLog(device, type, msg):
    time_now = str(datetime.datetime.now(pytz.timezone('UTC')))
    print(f"{time_now} {device} {type} {msg} ")
    LogFile = open(LogFileName, "a")
    LogFile.write(f"{time_now} {device} {type} {msg} \n")
    LogFile.close()

SaveToLog("Program", "Swarm-RR-2","")
SaveToLog("Program", 'ArgumentList', str(sys.argv))

# serial
# red > orange
# green > yellow
# https://www.circuitbasics.com/raspberry-pi-i2c-lcd-set-up-and-programming/

AppID = "9999"  # this is reset to the current decoder ID once decoder connects

TCP_IP = "192.168.20.211" # decoder IP address
#TCP_IP = "192.168.1.3" # decoder IP address
TCP_PORT = 3601
ADDR = (TCP_IP, TCP_PORT)
FORMAT = 'utf-8'

SaveToLog("Decoder", "Connecting", TCP_IP)
LocalIP = subprocess.getoutput('hostname -I').split()
SaveToLog("Program", "IP", LocalIP[0])

LCD = I2C_LCD_driver.lcd()
LCD.lcd_display_string("S" + TCP_IP, 1)
LCD.lcd_display_string("C" + LocalIP[0], 2)
time.sleep(2)

ser = serial.Serial(port="/dev/ttyAMA0", baudrate=115200, timeout=1, write_timeout=1)
if (ser.isOpen() == True):
    SerialMsg = "$RT 1*17\r\n"  # receive test every 1 second
    ser.write(SerialMsg.encode())
    SerialMsg = "$GS 5*01\r\n"  # GPS fix every 5 seconds
    ser.write(SerialMsg.encode())
    SerialMsg = "$GN 5*1C\r\n"  # Geospatial every 5 seconds
    ser.write(SerialMsg.encode())
    SerialMsg = "$PW 5*12\r\n"  # Power status every 5 seconds
    ser.write(SerialMsg.encode())
    SerialMsg = "$FV*10\r\n"  # Get current firmware
    ser.write(SerialMsg.encode())

if sys.argv[1] == '1' and ser.isOpen() == True:
    SaveToLog("Swarm", "Messages", "Deleted")
    SerialMsg = "$MT D=U*15\r\n"  # delete all messages if 1st argument equals 1
    ser.write(SerialMsg.encode())
    SerialMsg = "$MT C=U*12\r\n"
    ser.write(SerialMsg.encode())

def checksum(sentence):
    sentence = sentence.strip('\n')
    nmeadata, cksum = sentence.split('*', 1)
    calc_cksum = reduce(operator.xor, (ord(s) for s in nmeadata), 0)

    if len(hex(calc_cksum)) == 3:
        return '0' + hex(calc_cksum)[2:]
    else:
        return hex(calc_cksum)[2:]

def send(msg):
    message = msg.encode(FORMAT)
    client.send(message)

    msg = client.recv(1024).decode(FORMAT).strip()
    SaveToLog("Decoder", "Receive", msg)
    msgList = msg.strip().split(";")

    if msgList[0] == "GETSTATUS":
        global AppID
        AppID = str(msgList[6])
        SaveToLog("Decoder", "File", str(msgList[6]))

def GetSocket():
    SwarmMsg = ""
    global client
    global MsgLength, PassingCount
    MsgLength = 0
    PassingCount = 0

    while True:
        try:
            SaveToLog("Decoder", "Socket", "Start")
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(ADDR)
            SaveToLog("Decoder", "Socket", "Open")
            send("SETPROTOCOL;3.3\r\n")      
            send("SETPUSHPASSINGS;1;0\r\n")
            send("GETSTATUS\r\n")
        except socket.error as err:
            pass

        while True:
            try:
                send("PING\r\n")
                MsgDecode = client.recv(1024).decode(FORMAT)

                if len(MsgDecode) > 0:
                    msg = MsgDecode.split(';')
                    if MsgDecode[0] == '#':
                        SaveToLog("Decoder", "Receive", MsgDecode.strip())

                        temp = msg[4].replace('.', ':')
                        ChipTime = temp.split(':')

                        DecimalTime = (int(ChipTime[0])*3600) + \
                            (int(ChipTime[1])*60) + int(ChipTime[2])

                        TempMsg = msg[2] + ";" + str(DecimalTime) + "." + str(ChipTime[3])

                        if len(SwarmMsg) + len(TempMsg) < 192: # add to SwarmMsg if less then total bytes 192
                            if SwarmMsg != "":
                                SwarmMsg = SwarmMsg + "," + TempMsg
                            else:
                                SwarmMsg = SwarmMsg + TempMsg
                            
                            MsgLength = len(SwarmMsg)
                            PassingCount += 1
                            SaveToLog("Decoder", "SwarmMsg", SwarmMsg)
                            SaveToLog("Decoder", "Length", str(len(SwarmMsg)))
                        else: # Send SwarmMsg and reset to 0 bytes
                            SaveToLog("Decoder", "SENT", SwarmMsg)
                            SaveToLog("Decoder", "Length", str(len(SwarmMsg)))

                            SerialMsg = "TD AI=" + AppID + ",\"" + SwarmMsg + "\"" + "*"
                            msg = "$" + SerialMsg + checksum(SerialMsg) + "\n\r"
                            ser.write(msg.encode())
                            SaveToLog("Swarm", "Receive", msg.strip())

                            SwarmMsg = ""
                            SwarmMsg = SwarmMsg + TempMsg
                            MsgLength = len(SwarmMsg)
                            PassingCount = 1
                            SaveToLog("Decoder", "SwarmMsg", SwarmMsg)
                            SaveToLog("Decoder", "Length", str(len(SwarmMsg)))
            except socket.error as err:
                SaveToLog("Decoder", "Socket", f"Closed {err}")
                client.close()
                break

def GetSerial():
    serialString = ""  # Used to hold data coming over UART
    global UnsentMessages, ReceiveTest, GPS_Fix, PW_Info, RT_Info
    UnsentMessages = " "
    ReceiveTest = " "
    GPS_Fix = " "
    PW_Info = [0] * 5
    RT_Info = [0] * 5

    while True:
        if ser.in_waiting > 0:
            serialString = ser.readline()
            try:
                msg = serialString.decode("Ascii").strip()
                SaveToLog("Swarm", "Receive", msg)
                end = msg.index('*')

                if msg[0:3] == "$MT":
                    UnsentMessages = msg[4: end]
                elif msg[0:3] == "$RT":
                    if ',' in msg:
                        data = msg[4: end]
                        RT_Info = data.split(',')
                    else:
                        ReceiveTest = msg[9: end]
                elif msg[0:3] == "$GS":
                    data = msg[4: end]
                    data = data.split(',')
                    GPS_Fix = data[4]
                elif msg[0:3] == "$PW":
                    data = msg[4: end]
                    PW_Info = data.split(',')
            except:
                pass


def GetUnsent():
    while True:
        SerialMsg = "$MT C=U*12\r\n"
        ser.write(SerialMsg.encode())
        time.sleep(10)  # get unsent message count every 10 seconds


def UpdateLCD():
    LCD = I2C_LCD_driver.lcd()
    while True:
        LCD.lcd_clear()
        for x in range(14):  # loop for 5 seconds
            if PW_Info[0] != "OK":
                voltage = float(PW_Info[0])
                temp = float(PW_Info[4])
            else:
                voltage = 0.0
                temp = 0.0

            LCD.lcd_display_string(
                "U:" + str(UnsentMessages) + "GS:" + str(GPS_Fix) + "P:" + str(PassingCount)+ "-" + str(MsgLength), 1)
            LCD.lcd_display_string(
                "V:" + str(round(voltage, 2)) + " T:" + str(temp), 2)
            time.sleep(0.5)

        LCD.lcd_clear()
        for x in range(14):  # loop for 10 seconds
            LCD.lcd_display_string(str(RT_Info[0]) + " " + str(RT_Info[1]), 1)
            LCD.lcd_display_string("RSSI BG=" + str(ReceiveTest), 2)
            time.sleep(0.5)

        LCD.lcd_clear()
        LCD.lcd_display_string("S" + TCP_IP, 1)
        LCD.lcd_display_string("C" + LocalIP[0], 2)
        time.sleep(5)  # show for 5 seconds


try:
    _thread.start_new_thread(GetSerial, ())
    _thread.start_new_thread(GetSocket, ())
    _thread.start_new_thread(GetUnsent, ())
    _thread.start_new_thread(UpdateLCD, ())
except:
    SaveToLog("Program", "Thread", "FailedToStart")

while 1:
    pass
