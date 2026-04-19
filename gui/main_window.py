# -*- coding: utf-8 -*-
"""
Combined XUV Spectrometer Monitor GUI
"""

import cv2
import numpy as np
import time
import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# Import Hardware Modules
from core.camera import BaslerCamera
from core.grating import GratingController
from core.epics_client import EpicsClient


class CombinedXUVGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("XUV Spectrometer Monitor with Grating Control")
        self.root.geometry("1400x900")
        
        # Initialize hardware modules (No connection is made yet)
        # Change enable_dummy_mode=True if you want to test off the lab network
        self.camera_module = BaslerCamera(camera_name="XUV Spectrometer (23840960)")
        self.grating_module = GratingController(port="COM4", baudrate=115200)
        self.epics_client = EpicsClient(enable_dummy_mode=False)
        
        # Initialize processing variables
        self.wl_calibration_slope = 1 / 23.0315  # ~ 23 pixels per nm
        self.background_image = None
        self.bg_correction = False
        
        # State variables
        self.is_recording = False
        self.is_viewing = False
        self.roi_limits = None
        self.proj_limits = None
        self.count = 0
        
        self.recording_thread = None
        self.viewing_thread = None
        
        # Create GUI elements
        self.create_widgets()
        
        # Connect to hardware on startup
        self.connect_hardware()

    def connect_hardware(self):
        """Attempts to connect to camera and grating motor on startup."""
        if self.camera_module.connect():
            self.camera_label.config(text=f"Connected: {self.camera_module.camera_name}", foreground="green")
            self.status_label.config(text="Camera connected")
        else:
            self.camera_label.config(text="Camera not found", foreground="red")
            self.status_label.config(text="Camera not found")

        # Start grating connection in a background thread so UI doesn't freeze
        def connect_grating():
            if self.grating_module.connect():
                self.root.after(0, lambda: self.grating_label.config(text="Connected", foreground="green"))
                self.root.after(0, self.update_grating_labels)
            else:
                self.root.after(0, lambda: self.grating_label.config(text="Connection failed", foreground="red"))

        threading.Thread(target=connect_grating, daemon=True).start()

    def create_widgets(self):
        # --- Main Layout ---
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
    
        # Left = Controls | Right = Display
        left_frame = ttk.Frame(main_frame, width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)  # Maintain fixed width
    
        display_frame = ttk.LabelFrame(main_frame, text="Display", padding=10)
        display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    
        # --- Display Setup ---
        self.fig = Figure(figsize=(10, 8))
        gs = self.fig.add_gridspec(2, 1, height_ratios=[4, 1])
        self.ax = [self.fig.add_subplot(gs[0]), self.fig.add_subplot(gs[1])]
    
        self.canvas = FigureCanvasTkAgg(self.fig, display_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
        self.ax[0].set_title('Camera View')
        self.ax[1].set_title('Horizontal Projection')
        self.canvas.draw()
    
        # --- Controls (Stacked Vertically) ---
    
        # Camera Info
        info_frame = ttk.Frame(left_frame)
        info_frame.pack(fill=tk.X, pady=2)
        ttk.Label(info_frame, text="Camera:").pack(side=tk.LEFT)
        self.camera_label = ttk.Label(info_frame, text="Connecting...", foreground="orange")
        self.camera_label.pack(side=tk.LEFT, padx=(5, 0))

        # Background Correction
        bg_frame = ttk.LabelFrame(left_frame, text="Background Correction", padding=5)
        bg_frame.pack(fill=tk.X, pady=5)
    
        self.bg_var = tk.BooleanVar()
        ttk.Checkbutton(bg_frame, text="Enable background correction", variable=self.bg_var).pack(anchor=tk.W)
        ttk.Button(bg_frame, text="Capture Background", command=self.capture_background).pack(fill=tk.X, pady=2)
        ttk.Button(bg_frame, text="Load Background", command=self.load_background).pack(fill=tk.X, pady=2)
        ttk.Button(bg_frame, text="Save Background", command=self.save_background).pack(fill=tk.X, pady=2)
    
        # ROI & Projection
        roi_frame = ttk.LabelFrame(left_frame, text="ROI & Projection", padding=5)
        roi_frame.pack(fill=tk.X, pady=5)
    
        ttk.Button(roi_frame, text="Select ROI", command=self.select_roi).pack(fill=tk.X, pady=2)
        ttk.Button(roi_frame, text="Select Projection Limits", command=self.select_projection_limits).pack(fill=tk.X, pady=2)
        self.roi_label = ttk.Label(roi_frame, text="ROI: Not set", wraplength=300)
        self.roi_label.pack(pady=2)
        self.proj_label = ttk.Label(roi_frame, text="Projection: Not set", wraplength=300)
        self.proj_label.pack(pady=2)
    
        # Recording Controls
        record_frame = ttk.LabelFrame(left_frame, text="Recording", padding=5)
        record_frame.pack(fill=tk.X, pady=5)
    
        ttk.Label(record_frame, text="Run name:").pack(anchor=tk.W)
        self.run_name_var = tk.StringVar(value="test_run")
        ttk.Entry(record_frame, textvariable=self.run_name_var, width=25).pack(fill=tk.X, pady=2)
    
        self.record_button = ttk.Button(record_frame, text="Start Recording", command=self.toggle_recording)
        self.record_button.pack(fill=tk.X, pady=2)
    
        self.view_button = ttk.Button(record_frame, text="Start Live View", command=self.toggle_viewing)
        self.view_button.pack(fill=tk.X, pady=2)
    
        # Status
        status_frame = ttk.LabelFrame(left_frame, text="Status", padding=5)
        status_frame.pack(fill=tk.X, pady=5)
    
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT, padx=(5, 10))
    
        ttk.Label(status_frame, text="Frame count:").pack(side=tk.LEFT)
        self.count_label = ttk.Label(status_frame, text="0")
        self.count_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Grating Controller Info
        grating_info_frame = ttk.Frame(left_frame)
        grating_info_frame.pack(fill=tk.X, pady=2)
        ttk.Label(grating_info_frame, text="Grating:").pack(side=tk.LEFT)
        self.grating_label = ttk.Label(grating_info_frame, text="Connecting...", foreground="orange")
        self.grating_label.pack(side=tk.LEFT, padx=(5, 0))

        # Grating Control
        grating_frame = ttk.LabelFrame(left_frame, text="Grating Control", padding=5)
        grating_frame.pack(fill=tk.X, pady=5)

        ttk.Label(grating_frame, text="Desired Wavelength (nm):", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.wavelength_var = tk.StringVar()
        wavelength_entry = ttk.Entry(grating_frame, textvariable=self.wavelength_var, width=15, font=("Arial", 12))
        wavelength_entry.pack(fill=tk.X, pady=2)
        wavelength_entry.bind('<Return>', self.move_stage)

        ttk.Button(grating_frame, text="Move to Wavelength", command=self.move_stage).pack(fill=tk.X, pady=2)

        self.current_angle_label = ttk.Label(grating_frame, text="Current Angle: --", font=("Arial", 9))
        self.current_angle_label.pack(pady=1)
        
        self.current_wavelength_label = ttk.Label(grating_frame, text="Wavelength: -- nm", font=("Arial", 11, "bold"))
        self.current_wavelength_label.pack(pady=1)

        # Step controls
        step_frame = ttk.Frame(grating_frame)
        step_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(step_frame, text="Step Size (deg):").pack(side=tk.LEFT)
        self.step_size_var = tk.StringVar(value="0.1")
        step_entry = ttk.Entry(step_frame, textvariable=self.step_size_var, width=8)
        step_entry.pack(side=tk.RIGHT)

        button_frame = ttk.Frame(grating_frame)
        button_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(button_frame, text="-", width=5, command=self.decrement_angle).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="+", width=5, command=self.increment_angle).pack(side=tk.RIGHT, padx=2)


    # ==========================================
    # GRATING CONTROL METHODS
    # ==========================================

    def move_stage(self, event=None):
        try:
            desired_wl = float(self.wavelength_var.get())
            
            # Callback ensures UI updates smoothly after the motor stops
            def on_complete():
                self.root.after(0, self.update_grating_labels)
                
            self.grating_module.move_to_wavelength_async(desired_wl, callback=on_complete)
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid wavelength value")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def increment_angle(self):
        try:
            step_size = float(self.step_size_var.get())
            self.grating_module.step(step_size)
            self.update_grating_labels()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def decrement_angle(self):
        try:
            step_size = float(self.step_size_var.get())
            self.grating_module.step(-step_size)
            self.update_grating_labels()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_grating_labels(self):
        if self.grating_module.is_connected:
            angle, wl = self.grating_module.get_position()
            self.epics_client.write_wavelength(wl)
            self.current_angle_label.config(text=f"Current Angle: {angle:.3f} degrees")
            self.current_wavelength_label.config(text=f"Wavelength: {wl:.2f} nm")


    # ==========================================
    # CAMERA & BACKGROUND METHODS
    # ==========================================

    def capture_background(self):
        try:
            self.background_image = self.camera_module.grab_single_frame()
            self.bg_var.set(True)
            messagebox.showinfo("Success", "Background captured successfully")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            
    def load_background(self):
        try:
            filename = filedialog.askopenfilename(
                title="Load Background Image",
                filetypes=[("NumPy files", "*.npy"), ("All files", "*.*")]
            )
            if filename:
                self.background_image = np.load(filename)
                self.bg_var.set(True)
                messagebox.showinfo("Success", "Background loaded successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load background: {str(e)}")
            
    def save_background(self):
        if self.background_image is None:
            messagebox.showerror("Error", "No background image to save")
            return
        try:
            filename = filedialog.asksaveasfilename(
                title="Save Background Image",
                defaultextension=".npy",
                filetypes=[("NumPy files", "*.npy"), ("All files", "*.*")]
            )
            if filename:
                np.save(filename, self.background_image)
                messagebox.showinfo("Success", "Background saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save background: {str(e)}")


    # ==========================================
    # REGION OF INTEREST (ROI) METHODS
    # ==========================================

    def select_roi(self):
        try:
            # Grab a frame, skipping 3 to clear the buffer
            image = self.camera_module.grab_single_frame(skip_frames=3)
            limits = self.ask_roi(image)
            if limits:
                self.roi_limits = limits
                self.roi_label.config(text=f"ROI: {self.roi_limits}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select ROI: {str(e)}")
            
    def select_projection_limits(self):
        try:
            image = self.camera_module.grab_single_frame(skip_frames=3)
            limits = self.ask_proj_lims(image)
            if limits:
                self.proj_limits = limits
                self.proj_label.config(text=f"Projection: {self.proj_limits}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select projection limits: {str(e)}")

    def ask_roi(self, image):
        image_norm = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        clone = cv2.cvtColor(image_norm, cv2.COLOR_GRAY2BGR)
        ref_points = []
        
        def select_roi_callback(event, x, y, flags, param):
            nonlocal ref_points
            if event == cv2.EVENT_LBUTTONDOWN:
                ref_points = [(x, y)]
            elif event == cv2.EVENT_LBUTTONUP:
                ref_points.append((x, y))
                cv2.rectangle(clone, ref_points[0], ref_points[1], (0, 0, 255), 2)
                cv2.imshow("Select ROI (Press y to save, r to reset, q to cancel)", clone)
        
        window_name = "Select ROI (Press y to save, r to reset, q to cancel)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 800, 600)
        cv2.setMouseCallback(window_name, select_roi_callback)
        
        while True:
            cv2.imshow(window_name, clone)
            key = cv2.waitKey(100) & 0xFF
            if key == ord("r"):
                clone = cv2.cvtColor(image_norm, cv2.COLOR_GRAY2BGR)
                ref_points = []
            elif key == ord("y") and len(ref_points) == 2:
                cv2.destroyAllWindows()
                return ref_points
            elif key == ord("q"):
                cv2.destroyAllWindows()
                return None
                
    def ask_proj_lims(self, image):
        image_norm = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        clone = cv2.cvtColor(image_norm, cv2.COLOR_GRAY2BGR)
        proj_lims = []
        xlim = clone.shape[1]
        
        def select_proj_callback(event, x, y, flags, param):
            nonlocal proj_lims
            if event == cv2.EVENT_LBUTTONDOWN:
                proj_lims = [y]
            elif event == cv2.EVENT_LBUTTONUP:
                proj_lims.append(y)
                proj_lims = sorted(proj_lims)
                cv2.line(clone, (0, proj_lims[0]), (xlim, proj_lims[0]), (0, 0, 255), 2)
                cv2.line(clone, (0, proj_lims[1]), (xlim, proj_lims[1]), (0, 0, 255), 2)
                cv2.imshow("Select limits (y=save, r=reset, q=cancel)", clone)
        
        window_name = "Select limits (y=save, r=reset, q=cancel)"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 800, 600)
        cv2.setMouseCallback(window_name, select_proj_callback)
        
        while True:
            cv2.imshow(window_name, clone)
            key = cv2.waitKey(100) & 0xFF
            if key == ord("r"):
                clone = cv2.cvtColor(image_norm, cv2.COLOR_GRAY2BGR)
                proj_lims = []
            elif key == ord("y") and len(proj_lims) == 2:
                cv2.destroyAllWindows()
                return proj_lims
            elif key == ord("q"):
                cv2.destroyAllWindows()
                return None


    # ==========================================
    # RECORDING & VIEWING LOOPS
    # ==========================================

    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()
            
    def toggle_viewing(self):
        if self.is_viewing:
            self.stop_viewing()
        else:
            self.start_viewing()

    def start_recording(self):
        if not self.camera_module.is_connected:
            messagebox.showerror("Error", "Camera not connected")
            return
        if not self.roi_limits or not self.proj_limits:
            messagebox.showerror("Error", "Please set ROI and projection limits first")
            return
        if not self.run_name_var.get().strip():
            messagebox.showerror("Error", "Please enter a run name")
            return
            
        self.is_recording = True
        self.count = 0
        self.record_button.config(text="Stop Recording")
        self.view_button.config(state="disabled")
        self.status_label.config(text="Recording...")
        
        self.recording_thread = threading.Thread(target=self.recording_loop, daemon=True)
        self.recording_thread.start()
        
    def stop_recording(self):
        self.is_recording = False
        self.record_button.config(text="Start Recording")
        self.view_button.config(state="normal")
        self.status_label.config(text="Recording stopped")
        
    def start_viewing(self):
        if not self.camera_module.is_connected:
            messagebox.showerror("Error", "Camera not connected")
            return
        if not self.roi_limits or not self.proj_limits:
            messagebox.showerror("Error", "Please set ROI and projection limits first")
            return
            
        self.is_viewing = True
        self.view_button.config(text="Stop Live View")
        self.record_button.config(state="disabled")
        self.status_label.config(text="Live viewing...")
        
        self.viewing_thread = threading.Thread(target=self.viewing_loop, daemon=True)
        self.viewing_thread.start()
        
    def stop_viewing(self):
        self.is_viewing = False
        self.view_button.config(text="Start Live View")
        self.record_button.config(state="normal")
        self.status_label.config(text="Live view stopped")

    def recording_loop(self):
        try:
            timestamp = time.time()
            datetime_string = time.strftime("_%Y-%m-%d_%H-%M-%S", time.localtime(timestamp))
            dirname = self.run_name_var.get() + datetime_string
            os.makedirs(f"{dirname}/images", exist_ok=True)
            os.makedirs(f"{dirname}/parameters", exist_ok=True)
            
            self.camera_module.start_continuous()
            
            while self.is_recording:
                image = self.camera_module.retrieve_frame()
                if image is not None:
                    if self.bg_var.get() and self.background_image is not None:
                        image = image - self.background_image
                    self.process_and_display_image(image, save_data=True, dirname=dirname)
                time.sleep(0.1)
                
        except Exception as e:
            messagebox.showerror("Recording Error", str(e))
        finally:
            self.camera_module.stop_continuous()
            self.is_recording = False
            self.root.after(0, self.stop_recording)
            
    def viewing_loop(self):
        try:
            self.camera_module.start_continuous()
            
            while self.is_viewing:
                image = self.camera_module.retrieve_frame()
                if image is not None:
                    if self.bg_var.get() and self.background_image is not None:
                        image = image - self.background_image
                    self.process_and_display_image(image, save_data=False)
                time.sleep(0.1)
                
        except Exception as e:
            messagebox.showerror("Viewing Error", str(e))
        finally:
            self.camera_module.stop_continuous()
            self.epics_client.reset_signals()
            self.is_viewing = False
            self.root.after(0, self.stop_viewing)


    # ==========================================
    # DATA PROCESSING & DISPLAY
    # ==========================================

    def process_and_display_image(self, image, save_data=False, dirname=None):
        # Math calculations
        projection = np.sum(image[self.proj_limits[0]:self.proj_limits[1]], axis=0)
        roi_avg = np.mean(image[self.roi_limits[0][1]:self.roi_limits[1][1], self.roi_limits[0][0]:self.roi_limits[1][0]])
        
        # Write to EPICS Network
        self.epics_client.write_xuv_data(projection, roi_avg)
        
        # X-Axis Wavelength calculation
        wl0 = self.epics_client.get_current_wavelength()
        xdata = np.linspace(0, len(projection), len(projection))
        wl_ax = self.wl_calibration_slope * (xdata - len(xdata)/2) + wl0
        
        # Schedule GUI update
        self.root.after(0, self.update_display, image, projection, wl_ax, roi_avg)
        
        # Data Saving logic
        if save_data and dirname:
            imgpath = f"{dirname}/images/{self.count}.tiff"
            cv2.imwrite(imgpath, image)
            
            parampath = f"{dirname}/parameters/{self.count}.json"
            parameters = self.epics_client.get_machine_parameters()
            
            with open(parampath, "w") as json_file:
                json.dump(parameters, json_file)
            
            self.count += 1
            self.root.after(0, lambda: self.count_label.config(text=str(self.count)))
            
    def update_display(self, image, projection, wl_ax, roi_avg):
        self.ax[0].clear()
        self.ax[1].clear()
        
        # Plot Image
        self.ax[0].imshow(image, cmap='gray', aspect="auto")
        self.ax[0].set_title(f"Camera View - ROI mean: {np.round(roi_avg, 2)}")
        
        # Draw ROI
        if self.roi_limits:
            x = self.roi_limits[0][0]
            y = self.roi_limits[0][1]
            w = self.roi_limits[1][0] - x
            h = self.roi_limits[1][1] - y
            rect = patches.Rectangle((x, y), w, h, linewidth=1, edgecolor='r', facecolor='none')
            self.ax[0].add_patch(rect)
        
        # Draw Projection Limits
        if self.proj_limits:
            self.ax[0].axhline(y=self.proj_limits[0], ls=':', color='r')
            self.ax[0].axhline(y=self.proj_limits[1], ls=':', color='r')
            
        self.ax[0].set_xticklabels([])
        
        # Plot Projection
        self.ax[1].plot(wl_ax, projection)
        self.ax[1].set_title('Horizontal Projection')
        self.ax[1].set_xlim(min(wl_ax), max(wl_ax))
        
        self.canvas.draw()
        
        # Sync grating labels smoothly during live view
        if self.grating_module.is_connected:
            self.root.after(100, self.update_grating_labels)

    def on_closing(self):
        """Safely clean up all hardware connections before destroying the window."""
        self.is_recording = False
        self.is_viewing = False
        
        self.camera_module.disconnect()
        self.grating_module.disconnect()
        self.epics_client.reset_signals()
        
        self.root.destroy()