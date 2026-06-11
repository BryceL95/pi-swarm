import socket
import time

#create an INET, STREAMing socket (IPv4, TCP/IP)
try:
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except socket.error:
    print('Failed to create socket')
    sys.exit()

print('Socket Created')

DECODER_IP= "192.168.20.217"
DECODER_PORT = 3601
#Connect the socket object using IP address (string) and port (int)
client.connect((DECODER_IP,DECODER_PORT))

print('Socket Connected to ' + DECODER_IP )

msg = client.recv(1024)
print(msg.decode("utf-8"))

# SETPUSHPASSINGS; 1; 0

#Disconnect and close the socket object
client.close()
print("closed")
sys.exit()