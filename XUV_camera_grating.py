# -*- coding: utf-8 -*-
"""
Combined XUV Spectrometer Monitor with Grating Control
Created on Mon Mar 25 11:25:56 2024
Modified to include grating control functionality

@author: arjun
"""

import cv2
import epics
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pypylon import pylon
import numpy as np
import time
import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from PIL import Image, ImageTk
from matplotlib.figure import Figure
#from Xeryon import *


class CombinedXUVGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("XUV Spectrometer Monitor with Grating Control")
        self.root.geometry("1400x900")
        
        # Initialize variables
        self.camera = None
        self.camera_name = "XUV Spectrometer (23840960)"
#        self.camera_name = "Basler Emulation (0815-0000)" # Select this for testing
        self.wl_calibration_slope = 1/23.0315  # ~ 23 pixels per nm
        self.background_image = None
        self.bg_correction = False
        self.is_recording = False
        self.is_viewing = False
        self.roi_limits = None
        self.proj_limits = None
        self.count = 0
        self.recording_thread = None
        self.viewing_thread = None
        
        # Grating control variables
        self.controller = None
        self.axisR = None
        self.wl_angle = lambda wl: 0.0489502 * wl + -0.01708627
        self.grating_update_thread = None
        self.grating_active = False
        
        # Create GUI elements
        self.create_widgets()
        self.initialize_camera()
        self.initialize_grating_controller()
     
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
        from matplotlib.figure import Figure
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
        self.camera_label = ttk.Label(info_frame, text="Not connected", foreground="red")
        self.camera_label.pack(side=tk.LEFT, padx=(5, 0))

        # Background Correction
        bg_frame = ttk.LabelFrame(left_frame, text="Background Correction", padding=5)
        bg_frame.pack(fill=tk.X, pady=5)
    
        self.bg_var = tk.BooleanVar()
        ttk.Checkbutton(bg_frame, text="Enable background correction",
                        variable=self.bg_var).pack(anchor=tk.W)
        ttk.Button(bg_frame, text="Capture Background",
                   command=self.capture_background).pack(fill=tk.X, pady=2)
        ttk.Button(bg_frame, text="Load Background",
                   command=self.load_background).pack(fill=tk.X, pady=2)
        ttk.Button(bg_frame, text="Save Background",
                   command=self.save_background).pack(fill=tk.X, pady=2)
    
        # ROI & Projection
        roi_frame = ttk.LabelFrame(left_frame, text="ROI & Projection", padding=5)
        roi_frame.pack(fill=tk.X, pady=5)
    
        ttk.Button(roi_frame, text="Select ROI",
                   command=self.select_roi).pack(fill=tk.X, pady=2)
        ttk.Button(roi_frame, text="Select Projection Limits",
                   command=self.select_projection_limits).pack(fill=tk.X, pady=2)
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
    
        self.record_button = ttk.Button(record_frame, text="Start Recording",
                                         command=self.toggle_recording)
        self.record_button.pack(fill=tk.X, pady=2)
    
        self.view_button = ttk.Button(record_frame, text="Start Live View",
                                       command=self.toggle_viewing)
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
        self.grating_label = ttk.Label(grating_info_frame, text="Not connected", foreground="red")
        self.grating_label.pack(side=tk.LEFT, padx=(5, 0))

        # Grating Control
        grating_frame = ttk.LabelFrame(left_frame, text="Grating Control", padding=5)
        grating_frame.pack(fill=tk.X, pady=5)

        # Wavelength input
        ttk.Label(grating_frame, text="Desired Wavelength (nm):", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.wavelength_var = tk.StringVar()
        wavelength_entry = ttk.Entry(grating_frame, textvariable=self.wavelength_var, width=15, font=("Arial", 12))
        wavelength_entry.pack(fill=tk.X, pady=2)
        wavelength_entry.bind('<Return>', self.move_stage)

        ttk.Button(grating_frame, text="Move to Wavelength", 
                   command=self.move_stage).pack(fill=tk.X, pady=2)

        # Current status
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
        
        ttk.Button(button_frame, text="-", width=5,
                   command=self.decrement_angle).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="+", width=5,
                   command=self.increment_angle).pack(side=tk.RIGHT, padx=2)
        

    def initialize_grating_controller(self):
        """Initialize the grating controller"""
        try:
            self.controller = Xeryon("COM4", 115200)
            self.axisR = self.controller.addAxis(Stage.XRTU_30_109, "R")
            self.controller.start()
            self.axisR.findIndex()
            self.axisR.setUnits(Units.deg)
            
            print("Connecting the Grating Controller, Please wait...")
            time.sleep(1)
            while self.axisR.isScanning():
                time.sleep(0.1)
            
            self.grating_label.config(text="Connected", foreground="green")
            self.grating_active = True
            self.update_grating_labels()
            
        except Exception as e:
            print(f"Failed to initialize grating controller: {str(e)}")
            self.grating_label.config(text="Connection failed", foreground="red")
            messagebox.showerror("Grating Error", f"Failed to initialize grating controller: {str(e)}")

    def move_stage(self, event=None):
        """Move the grating to the desired wavelength"""
        if not self.grating_active or not self.axisR:
            messagebox.showerror("Error", "Grating controller not connected")
            return
            
        try:
            desired_wl = float(self.wavelength_var.get())
            desired_angle = self.wl_angle(desired_wl)
            self.axisR.setDPOS(desired_angle)
            
            def adjust_wavelength_precision():
                time.sleep(0.5)
                if not self.axisR.isPositionReached():
                    self.root.after(200, adjust_wavelength_precision)
                    return

                current_angle = self.axisR.getEPOS()
                current_wavelength = (current_angle + 0.01708627) / (0.0489502)

                # Calculate the difference between current and desired wavelength
                diff = desired_wl - current_wavelength

                if abs(diff) > 0.08:
                    d_angle = 0.0489502 * diff
                    self.axisR.step(d_angle)
                    self.root.after(200, adjust_wavelength_precision)
                else:
                    self.update_grating_labels()
                    print(f"Position Reached {current_wavelength} nm")

            adjust_wavelength_precision()
            
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid wavelength value")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to move stage: {str(e)}")

    def increment_angle(self):
        """Increment the grating angle by step size"""
        if not self.grating_active or not self.axisR:
            messagebox.showerror("Error", "Grating controller not connected")
            return
            
        try:
            step_size = float(self.step_size_var.get())
            self.axisR.step(step_size)
            self.update_grating_labels()
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid step size")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to increment angle: {str(e)}")

    def decrement_angle(self):
        """Decrement the grating angle by step size"""
        if not self.grating_active or not self.axisR:
            messagebox.showerror("Error", "Grating controller not connected")
            return
            
        try:
            step_size = float(self.step_size_var.get())
            self.axisR.step(-step_size)
            self.update_grating_labels()
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid step size")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to decrement angle: {str(e)}")

    def update_grating_labels(self):
        """Update the grating position labels"""
        if not self.grating_active or not self.axisR:
            return
            
        try:
            current_angle = self.axisR.getEPOS()
            current_wavelength = (current_angle + 0.01708627) / (0.0489502)
            epics.caput('fel-xuv-grating-wavelength', current_wavelength)
            
            self.current_angle_label.config(text=f"Current Angle: {current_angle:.3f} degrees")
            self.current_wavelength_label.config(text=f"Wavelength: {current_wavelength:.2f} nm")
        except Exception as e:
            print(f"Error updating grating labels: {str(e)}")
        
    def initialize_camera(self):
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            
            cam = None
            for device in devices:
                if device.GetFriendlyName() == self.camera_name:
                    cam = device
                    break
            
            if cam is not None:
                self.camera = pylon.InstantCamera(tlf.CreateDevice(cam))
                self.camera_label.config(text=f"Connected: {cam.GetFriendlyName()}", 
                                       foreground="green")
                self.status_label.config(text="Camera connected")
            else:
                self.camera_label.config(text="Camera not found", foreground="red")
                self.status_label.config(text="Camera not found")
                
        except Exception as e:
            messagebox.showerror("Camera Error", f"Failed to initialize camera: {str(e)}")
            
    def capture_background(self):
        if self.camera is None:
            messagebox.showerror("Error", "Camera not connected")
            return
            
        try:
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            # Capture a single frame for background
            grab_result = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grab_result.GrabSucceeded():
                self.background_image = grab_result.Array.copy()
                self.bg_var.set(True)
                messagebox.showinfo("Success", "Background captured successfully")
                grab_result.Release()
            
            self.camera.StopGrabbing()
            self.camera.Close()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture background: {str(e)}")
            
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
            
    def select_roi(self):
        if self.camera is None:
            messagebox.showerror("Error", "Camera not connected")
            return
            
        try:
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            for _ in range(3):
                grab_result = self.camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
                grab_result.Release()

            grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
            if grab_result.GrabSucceeded():
                image = grab_result.Array
                self.roi_limits = self.ask_roi(image)
                if self.roi_limits:
                    self.roi_label.config(text=f"ROI: {self.roi_limits}")
                grab_result.Release()
            
            self.camera.StopGrabbing()
            self.camera.Close()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select ROI: {str(e)}")
            
    def select_projection_limits(self):
        if self.camera is None:
            messagebox.showerror("Error", "Camera not connected")
            return
            
        try:
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            for _ in range(3):
                grab_result = self.camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
                grab_result.Release()
                
            grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
            if grab_result.GrabSucceeded():
                image = grab_result.Array
                self.proj_limits = self.ask_proj_lims(image)
                if self.proj_limits:
                    self.proj_label.config(text=f"Projection: {self.proj_limits}")
                grab_result.Release()
            
            self.camera.StopGrabbing()
            self.camera.Close()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select projection limits: {str(e)}")
            
    def ask_roi(self, image):
        # OpenCV ROI selection
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
        
        cv2.namedWindow("Select ROI (Press y to save, r to reset, q to cancel)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Select ROI (Press y to save, r to reset, q to cancel)", 800, 600)
        cv2.setMouseCallback("Select ROI (Press y to save, r to reset, q to cancel)", select_roi_callback)
        
        while True:
            cv2.imshow("Select ROI (Press y to save, r to reset, q to cancel)", clone)
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
        # OpenCV projection limits selection
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
                cv2.imshow("Select limits for projection (Press y to save, r to reset, q to cancel)", clone)
        
        cv2.namedWindow("Select limits for projection (Press y to save, r to reset, q to cancel)", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Select limits for projection (Press y to save, r to reset, q to cancel)", 800, 600)
        cv2.setMouseCallback("Select limits for projection (Press y to save, r to reset, q to cancel)", select_proj_callback)
        
        while True:
            cv2.imshow("Select limits for projection (Press y to save, r to reset, q to cancel)", clone)
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
        if self.camera is None:
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
        
        self.recording_thread = threading.Thread(target=self.recording_loop)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        
    def stop_recording(self):
        self.is_recording = False
        self.record_button.config(text="Start Recording")
        self.view_button.config(state="normal")
        self.status_label.config(text="Recording stopped")
        
    def start_viewing(self):
        if self.camera is None:
            messagebox.showerror("Error", "Camera not connected")
            return
            
        if not self.roi_limits or not self.proj_limits:
            messagebox.showerror("Error", "Please set ROI and projection limits first")
            return
            
        self.is_viewing = True
        self.view_button.config(text="Stop Live View")
        self.record_button.config(state="disabled")
        self.status_label.config(text="Live viewing...")
        
        self.viewing_thread = threading.Thread(target=self.viewing_loop)
        self.viewing_thread.daemon = True
        self.viewing_thread.start()
        
    def stop_viewing(self):
        self.is_viewing = False
        self.view_button.config(text="Start Live View")
        self.record_button.config(state="normal")
        self.status_label.config(text="Live view stopped")
        
    def recording_loop(self):
        try:
            # Create directory structure
            timestamp = time.time()
            datetime_string = time.strftime("_%Y-%m-%d_%H-%M-%S", time.localtime(timestamp))
            dirname = self.run_name_var.get() + datetime_string
            
            os.makedirs(dirname, exist_ok=True)
            os.makedirs(f"{dirname}/images", exist_ok=True)
            os.makedirs(f"{dirname}/parameters", exist_ok=True)
            
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            while self.is_recording and self.camera.IsGrabbing():
                grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
                
                if grab_result.GrabSucceeded():
                    image = grab_result.Array
                    
                    if self.bg_var.get() and self.background_image is not None:
                        image = image - self.background_image
                    
                    self.process_and_display_image(image, save_data=True, dirname=dirname)
                    
                grab_result.Release()
                time.sleep(0.1)  # Small delay to prevent overwhelming the system
                
        except Exception as e:
            messagebox.showerror("Recording Error", f"Error during recording: {str(e)}")
        finally:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            self.camera.Close()
            self.is_recording = False
            self.root.after(0, self.stop_recording)
            
    def viewing_loop(self):
        try:
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            while self.is_viewing and self.camera.IsGrabbing():
                grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
                
                if grab_result.GrabSucceeded():
                    image = grab_result.Array
                    
                    if self.bg_var.get() and self.background_image is not None:
                        image = image - self.background_image
                    
                    self.process_and_display_image(image, save_data=False)
                    
                grab_result.Release()
                time.sleep(0.1)  # Small delay for smooth viewing
                
        except Exception as e:
            messagebox.showerror("Viewing Error", f"Error during viewing: {str(e)}")
        finally:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            self.camera.Close()
            # Reset EPICS signals
            try:
                epics.caput('fel-lab-signal', 0.0)
                epics.caput('fel-lab-signal2', 0.0)
            except:
                pass
            self.is_viewing = False
            self.root.after(0, self.stop_viewing)
            
    def process_and_display_image(self, image, save_data=False, dirname=None):
        # Calculate projection
        projection = np.sum(image[self.proj_limits[0]:self.proj_limits[1]], axis=0)
        xdata = np.linspace(0, len(projection), len(projection))
        
        # Calculate ROI average
        roi = image[self.roi_limits[0][1]:self.roi_limits[1][1], 
                   self.roi_limits[0][0]:self.roi_limits[1][0]]
        roi_avg = np.mean(roi)
        
        # Update EPICS PVs
        try:
            epics.caput('fel-xuv-mcp-row', projection)
            epics.caput('fel-lab-signal', roi_avg)
            epics.caput('fel-lab-signal2', roi_avg)
            wl0 = epics.caget('fel-xuv-grating-wavelength')
        except:
            wl0 = 0  # Fallback if EPICS is not available
        
        wl_ax = self.wl_calibration_slope * (xdata - len(xdata)/2) + wl0
        
        # Update display
        self.root.after(0, self.update_display, image, projection, wl_ax, roi_avg)
        
        # Save data if recording
        if save_data and dirname:
            imgpath = f"{dirname}/images/{self.count}.tiff"
            cv2.imwrite(imgpath, image)
            
            parampath = f"{dirname}/parameters/{self.count}.json"
            parameters = self.get_params()
            
            with open(parampath, "w") as json_file:
                json.dump(parameters, json_file)
            
            self.count += 1
            self.root.after(0, lambda: self.count_label.config(text=str(self.count)))
            
    def update_display(self, image, projection, wl_ax, roi_avg):
        # Clear axes
        self.ax[0].clear()
        self.ax[1].clear()
        
        # Plot image
        self.ax[0].imshow(image, cmap='gray', aspect="auto")
        self.ax[0].set_title(f"Camera View - ROI mean: {np.round(roi_avg, 2)}")
        
        # Draw ROI rectangle
        if self.roi_limits:
            x = self.roi_limits[0][0]
            y = self.roi_limits[0][1]
            width = self.roi_limits[1][0] - x
            height = self.roi_limits[1][1] - y
            rect = patches.Rectangle((x, y), width, height, linewidth=1, 
                                   edgecolor='r', facecolor='none')
            self.ax[0].add_patch(rect)
        
        # Draw projection limits
        if self.proj_limits:
            self.ax[0].axhline(y=self.proj_limits[0], ls=':', color='r')
            self.ax[0].axhline(y=self.proj_limits[1], ls=':', color='r')
        
        self.ax[0].set_xticklabels([])
        
        # Plot projection
        self.ax[1].plot(wl_ax, projection)
        self.ax[1].set_title('Horizontal Projection')
        self.ax[1].set_xlim(min(wl_ax), max(wl_ax))
        
        # Update canvas
        self.canvas.draw()
        
        # Update grating labels if active
        if self.grating_active:
            self.root.after(100, self.update_grating_labels)
        
    def get_params(self):
        """Get parameters from EPICS"""
        try:
            params = {
                "modulator1": epics.caget('de-u250-modulator1-i:set.OVAL'),
                "modulator2": epics.caget('de-u250-modulator2-i:set.OVAL'),
                "radiator": epics.caget('de-u250-radiator-i:set.OVAL'),
                "chicane1": epics.caget('de-u250-schikane1-i:set.OVAL'),
                "chicane2": epics.caget('de-u250-schikane2-i:set.OVAL'),
                "delta1": epics.caget('de-u250-delta1-i:set.OVAL'),
                "delta2": epics.caget('de-u250-delta2-i:set.OVAL'),
                "delta3": epics.caget('de-u250-delta3-i:set.OVAL'),
                "delta4": epics.caget('de-u250-delta4-i:set.OVAL'),
                "THz1": epics.caget('fel-THz-signal'),
                "THz2": epics.caget('fel-THz-signal2'),
                "CHG": epics.caget('fel-lab-signal'),
                "XUV_spectra": epics.caget('fel-xuv-mcp-row').tolist(),
                "XUV_wavelength": epics.caget('fel-xuv-grating-wavelength'),
                "delaystage": epics.caget('fel-m1-meas-x'),
                "vectormod": epics.caget('fel-vm-readdelay'),
                "m1x": epics.caget('fel-seed-m1x_POSITION_MONITOR'),
                "m1y": epics.caget('fel-seed-m1y_POSITION_MONITOR'),
                "m2x": epics.caget('fel-seed-m2x_POSITION_MONITOR'),
                "m2y": epics.caget('fel-seed-m2y_POSITION_MONITOR'),
                "beamcurrent": epics.caget('share-de-beam-i'),
                "BPM14x": epics.caget('de-bpm14-x'),
                "BPM15x": epics.caget('de-bpm15-x'),
            }
        except Exception as e:
            print(f"Error reading EPICS parameters: {e}")
            params = {"error": "EPICS not available"}
        
        return params
        
    def on_closing(self):
        # Clean up when closing the application
        self.is_recording = False
        self.is_viewing = False
        self.grating_active = False
        
        if self.camera and self.camera.IsGrabbing():
            self.camera.StopGrabbing()
            self.camera.Close()
        
        # Stop grating controller
        if self.controller:
            try:
                self.controller.stop()
                print("Grating controller stopped")
            except:
                pass
            
        self.root.destroy()

def main():
    root = tk.Tk()
    app = CombinedXUVGUI(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()

if __name__ == "__main__":
    main()