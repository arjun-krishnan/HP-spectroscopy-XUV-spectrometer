# core/camera.py
from pypylon import pylon
import numpy as np
import logging

class BaslerCamera:
    """Hardware abstraction for Basler Pylon cameras."""
    
    def __init__(self, camera_name: str):
        self.camera_name = camera_name
        self.camera = None
        self.is_connected = False

    def connect(self) -> bool:
        """Finds and connects to the specified camera. Returns True if successful."""
        try:
            tlf = pylon.TlFactory.GetInstance()
            devices = tlf.EnumerateDevices()
            
            for device in devices:
                if device.GetFriendlyName() == self.camera_name:
                    self.camera = pylon.InstantCamera(tlf.CreateDevice(device))
                    self.is_connected = True
                    logging.info(f"Connected to camera: {self.camera_name}")
                    return True
            
            logging.warning(f"Camera '{self.camera_name}' not found.")
            return False
            
        except Exception as e:
            self.is_connected = False
            raise ConnectionError(f"Failed to initialize camera: {str(e)}")

    def disconnect(self):
        """Safely shuts down the camera connection."""
        if self.camera is not None:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            if self.camera.IsOpen():
                self.camera.Close()
            self.is_connected = False

    def grab_single_frame(self, timeout_ms: int = 5000, skip_frames: int = 0) -> np.ndarray:
        """
        Grabs a single frame. Useful for background capture or ROI selection.
        If skip_frames > 0, it dumps initial frames to clear the buffer.
        """
        if not self.is_connected:
            raise RuntimeError("Camera is not connected.")

        try:
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            
            # Dump old frames if requested (useful for ROI selection in your original code)
            for _ in range(skip_frames):
                grab_result = self.camera.RetrieveResult(1000, pylon.TimeoutHandling_ThrowException)
                grab_result.Release()

            grab_result = self.camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
            
            if grab_result.GrabSucceeded():
                image = grab_result.Array.copy()
            else:
                raise RuntimeError("Failed to grab single frame.")
                
            grab_result.Release()
            return image
            
        finally:
            self.camera.StopGrabbing()
            self.camera.Close()

    def start_continuous(self):
        """Starts the camera for live viewing or recording."""
        if not self.is_connected:
            raise RuntimeError("Camera is not connected.")
        self.camera.Open()
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    def retrieve_frame(self, timeout_ms: int = 10000) -> np.ndarray:
        """Retrieves the next frame during continuous grabbing."""
        if not self.camera.IsGrabbing():
            return None
            
        grab_result = self.camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
        if grab_result.GrabSucceeded():
            image = grab_result.Array
            grab_result.Release()
            return image
        else:
            grab_result.Release()
            raise RuntimeError("Frame dropped or failed during continuous grab.")

    def stop_continuous(self):
        """Stops continuous grabbing."""
        if self.camera and self.camera.IsGrabbing():
            self.camera.StopGrabbing()
            self.camera.Close()