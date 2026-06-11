import socket, datetime, re, _thread, time, fcntl, struct, operator, sys, subprocess
import serial, I2C_LCD_driver, pytz
from functools import reduce

print("\r\n")
print("Swarm-RR")
print('Argument List:', str(sys.argv))

# serial
# red > orange
# green > yellow
# https://www.circuitbasics.com/raspberry-pi-i2c-lcd-set-up-and-programming/

now = datetime.datetime.now(pytz.timezone('UTC'))
LogFileName = "/home/pi/Logs/SwarmLog_" + now.strftime("%d-%m-%y_%H-%M-%S") + ".txt"
AppID = "9999" # this is reset to the current decoder ID once decoder connects

TCP_IP = "192.168.20.211"
TCP_PORT = 3601

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# s.connect((TCP_IP, TCP_PORT))

# moved TCP connection to the GetSocket function.
# The function will continue to loop the connection process until connected rather than the program hanging.
# Need to test this with a decoder

print("Connecting to " + TCP_IP)
LocalIP = subprocess.getoutput('hostname -I').split()
print("ETH0 IP " + LocalIP[0])

LCD = I2C_LCD_driver.lcd()
LCD.lcd_display_string("S" + TCP_IP, 1)
LCD.lcd_display_string("C" + LocalIP[0], 2)
time.sleep(2)

ser = serial.Serial(port="/dev/ttyAMA0", baudrate = 115200, timeout=1, write_timeout=1)
if(ser.isOpen() == True):
    SerialMsg = "$RT 1*17\r\n" # receive test every 1 second
    ser.write(SerialMsg.encode())
    SerialMsg = "$GS 5*01\r\n" # GPS fix every 5 seconds
    ser.write(SerialMsg.encode())
    SerialMsg = "$GN 5*1C\r\n" # Geospatial every 5 seconds
    ser.write(SerialMsg.encode())
    SerialMsg = "$PW 5*12\r\n" # Power status every 5 seconds
    ser.write(SerialMsg.encode())

if sys.argv[1] == '1' and ser.isOpen() == True:
    print("Messages Deleted")
    SerialMsg = "$MT D=U*15\r\n" # delete all messages if 1st argument equals 1
    ser.write(SerialMsg.encode())
    SerialMsg = "$MT C=U*12\r\n"
    ser.write(SerialMsg.encode())

def checksum(sentence):
    sentence = sentence.strip('\n')
    nmeadata,cksum = sentence.split('*', 1)
    calc_cksum = reduce(operator.xor, (ord(s) for s in nmeadata), 0)

    if len(hex(calc_cksum)) == 3:
        return '0' + hex(calc_cksum)[2:]
    else:
        return hex(calc_cksum)[2:]

def GetSocket():
    connected = False
    while not connected:
        try:
            s.connect((TCP_IP, TCP_PORT))
            connected = True
        except Exception as e:
            pass #Do nothing, just try again

    MESSAGE = "SETPUSHPASSINGS;1;0\r\n"
    s.send(MESSAGE.encode())
    msg = s.recv(1024)
    MsgDecode = msg.decode("utf-8")
    print(MsgDecode.strip())

    MESSAGE = "SETPROTOCOL;3.3\r\n"
    s.send(MESSAGE.encode())
    msg = s.recv(1024)
    MsgDecode = msg.decode("utf-8")
    print(MsgDecode.strip())

    MESSAGE = "GETSTATUS\r\n"
    s.send(MESSAGE.encode())
    msg = s.recv(1024)
    MsgDecode = msg.decode("utf-8")
    print(MsgDecode.strip())
    DecoderStatus = MsgDecode.split(';')
    AppID = str(DecoderStatus[6])
    print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder File" + str(DecoderStatus[6]))
    LogFile = open(LogFileName, "a")
    LogFile.write(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder File" + str(DecoderStatus[6]) + "\n")
    LogFile.close()

    SwarmMsg = ""
    while True:
        msg = s.recv(1024)
        MsgDecode = msg.decode("utf-8")

        msg = MsgDecode.split(';')
        if MsgDecode[0] == '#':
            LogFile = open(LogFileName, "a")
            LogFile.write(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder " + MsgDecode.strip() + "\n")
            LogFile.close()
            print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder " + MsgDecode.strip())

            temp = msg[4].replace('.', ':')
            ChipTime = temp.split(':')

            DecimalTime = (int(ChipTime[0])*3600) + (int(ChipTime[1])*60) + int(ChipTime[2]);

            TempMsg = msg[2] + ";" + str(DecimalTime) + "." + str(ChipTime[3]);

            if len(SwarmMsg) + len(TempMsg) <= 192:
                if SwarmMsg != "":
                    SwarmMsg = SwarmMsg + "," + TempMsg
                else:
                    SwarmMsg = SwarmMsg + TempMsg
                print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder SwarmMsg: " + SwarmMsg + " Length: " + str(len(SwarmMsg)))
            else:
                print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder MessageSENT " + SwarmMsg + " L: " + str(len(SwarmMsg)))
                LogFile = open(LogFileName, "a")
                LogFile.write(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder MessageSENT-" + SwarmMsg + "-L:" + str(len(SwarmMsg)) + "\n")
                LogFile.close()

                # $TD AI=40,HD=7200,"{"d":"Demo message","t":"2021-02-26 14:28:56","seq":"00015"}"*09
                SerialMsg = "TD AI=" + AppID + ",\"" + SwarmMsg + "\"" + "*"
                msg = "$" + SerialMsg + checksum(SerialMsg) + "\n\r"
                ser.write(msg.encode())
                print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " SwarmCommand " + msg.strip())
                LogFile = open(LogFileName, "a")
                LogFile.write(str(datetime.datetime.now(pytz.timezone('UTC'))) + " " + msg.strip() + "\n")
                LogFile.close()

                SwarmMsg = ""
                SwarmMsg = SwarmMsg + TempMsg
                print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Decoder SwarmMsg: " + SwarmMsg + " Length: " + str(len(SwarmMsg)))

def GetSerial():
    serialString = ""  # Used to hold data coming over UART
    global UnsentMessages, ReceiveTest, GPS_Fix, PW_Info, RT_Info
    UnsentMessages = ""
    ReceiveTest = ""
    GPS_Fix = ""
    PW_Info = [0] * 5
    RT_Info = [0] * 5

    while True:
        if ser.in_waiting > 0:
            serialString = ser.readline()
            try:
                msg = serialString.decode("Ascii").strip()
                print(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Swarm " + msg)
                LogFile = open(LogFileName, "a")
                LogFile.write(str(datetime.datetime.now(pytz.timezone('UTC'))) + " Swarm " + msg + "\n")
                LogFile.close()

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
        time.sleep(10) # get unsent message count every 10 seconds

def UpdateLCD():
    LCD = I2C_LCD_driver.lcd()
    while True:
        LCD.lcd_clear()
        for x in range(14): # loop for 5 seconds
            if PW_Info[0] != "OK":
                voltage = float(PW_Info[0])
                temp = float(PW_Info[4])
            else:
                voltage = 0.0
                temp = 0.0

            LCD.lcd_display_string("U:" + str(UnsentMessages) + " GS:" + str(GPS_Fix), 1)
            LCD.lcd_display_string("V:" + str(round(voltage,2)) + " T:" + str(temp), 2)
            time.sleep(0.5)

        LCD.lcd_clear()
        for x in range(14): # loop for 10 seconds
            LCD.lcd_display_string(str(RT_Info[0]) + " " + str(RT_Info[1]), 1)
            LCD.lcd_display_string("RSSI BG=" + str(ReceiveTest), 2)
            time.sleep(0.5)

        LCD.lcd_clear()
        LCD.lcd_display_string("S" + TCP_IP, 1)
        LCD.lcd_display_string("C" + LocalIP[0], 2)
        time.sleep(5) # show for 5 seconds

try:
   _thread.start_new_thread(GetSerial, ())
   _thread.start_new_thread(GetSocket, ())
   _thread.start_new_thread(GetUnsent, ())
   _thread.start_new_thread(UpdateLCD, ())
except:
   print ("Error: unable to start thread")

while 1:
    pass