import os
import time
from typing import List
import urllib
import urllib.request

def interrupt_queue(server_address):
    req = urllib.request.Request(f"http://{server_address}/interrupt", method='POST')
    try:
        urllib.request.urlopen(req)
        print("Queue interrupted successfully.")
    except Exception as e:
        print(f"Failed to interrupt queue: {e}")

if __name__ == "__main__":
    server_address = "127.0.0.1:8188"  # Update this if your server address is different
    i = 0
    while i < 350:
        interrupt_queue(server_address)
        time.sleep(0.2)
        i+=1