# core/grating.py
import time
import logging
import threading

# Assuming Xeryon is installed/available in your environment
try:
    from Xeryon import Xeryon, Stage, Units
except ImportError:
    logging.warning("Xeryon module not found. Hardware will not connect.")

class GratingController:
    """Hardware abstraction for the Xeryon Grating Motor."""
    
    # Calibration constants
    SLOPE = 0.0489502
    OFFSET = -0.01708627

    def __init__(self, port: str = "COM4", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.controller = None
        self.axis = None
        self.is_connected = False
        self._is_moving = False

    def connect(self) -> bool:
        """Initializes the Xeryon controller and finds the index."""
        try:
            self.controller = Xeryon(self.port, self.baudrate)
            self.axis = self.controller.addAxis(Stage.XRTU_30_109, "R")
            self.controller.start()
            self.axis.findIndex()
            self.axis.setUnits(Units.deg)
            
            logging.info("Connecting to Grating Controller, waiting for index...")
            time.sleep(1)
            
            # Wait for scanning to finish
            while self.axis.isScanning():
                time.sleep(0.1)
                
            self.is_connected = True
            logging.info("Grating Controller connected successfully.")
            return True
            
        except Exception as e:
            self.is_connected = False
            logging.error(f"Failed to initialize grating controller: {str(e)}")
            return False

    def disconnect(self):
        """Safely stops and disconnects the motor."""
        if self.controller and self.is_connected:
            try:
                self.controller.stop()
                self.is_connected = False
                logging.info("Grating controller stopped.")
            except Exception as e:
                logging.error(f"Error disconnecting grating: {str(e)}")

    # --- Conversion Helpers ---
    @classmethod
    def wavelength_to_angle(cls, wl: float) -> float:
        return cls.SLOPE * wl + cls.OFFSET

    @classmethod
    def angle_to_wavelength(cls, angle: float) -> float:
        return (angle - cls.OFFSET) / cls.SLOPE

    # --- Status ---
    def get_position(self) -> tuple[float, float]:
        """Returns the current (angle_degrees, wavelength_nm)."""
        if not self.is_connected:
            raise RuntimeError("Grating is not connected.")
        
        current_angle = self.axis.getEPOS()
        current_wl = self.angle_to_wavelength(current_angle)
        return current_angle, current_wl

    # --- Movement Commands ---
    def step(self, angle_step: float):
        """Steps the grating by a specific angle amount."""
        if not self.is_connected:
            raise RuntimeError("Grating is not connected.")
        self.axis.step(angle_step)

    def move_to_wavelength_blocking(self, desired_wl: float, tolerance: float = 0.08):
        """
        Moves to the desired wavelength and performs fine-adjustment.
        This is a blocking call (it will wait until the position is reached).
        """
        if not self.is_connected:
            raise RuntimeError("Grating is not connected.")

        self._is_moving = True
        try:
            desired_angle = self.wavelength_to_angle(desired_wl)
            self.axis.setDPOS(desired_angle)
            
            while self._is_moving:
                time.sleep(0.5)
                
                # Wait for initial coarse move to finish
                if not self.axis.isPositionReached():
                    continue

                # Fine tuning loop
                current_angle, current_wl = self.get_position()
                diff = desired_wl - current_wl

                if abs(diff) > tolerance:
                    d_angle = self.SLOPE * diff
                    self.axis.step(d_angle)
                else:
                    logging.info(f"Position Reached: {current_wl:.2f} nm")
                    break
        finally:
            self._is_moving = False

    def move_to_wavelength_async(self, desired_wl: float, callback=None):
        """
        Non-blocking wrapper for move_to_wavelength. 
        Executes the move in a background thread and fires a callback when done.
        """
        def worker():
            self.move_to_wavelength_blocking(desired_wl)
            if callback:
                callback()
                
        threading.Thread(target=worker, daemon=True).start()