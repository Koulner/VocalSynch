import os
import sys
import threading
import webbrowser
import time

if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

from app import demo

def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:7860")

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=False, share=False, show_api=False)
