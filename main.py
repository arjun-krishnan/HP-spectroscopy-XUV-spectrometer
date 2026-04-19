# main.py
import tkinter as tk
from gui.main_window import CombinedXUVGUI

def main():
    root = tk.Tk()
    
    # Initialize the main application window
    app = CombinedXUVGUI(root)
    
    # Handle safe shutdown when the user clicks the 'X'
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()

if __name__ == "__main__":
    main()