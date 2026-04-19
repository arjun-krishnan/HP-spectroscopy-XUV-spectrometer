# core/epics_client.py
import logging

try:
    import epics
    EPICS_AVAILABLE = True
except ImportError:
    logging.warning("PyEPICS module not found. EPICS communication will be disabled.")
    EPICS_AVAILABLE = False

class EpicsClient:
    """Hardware abstraction for reading and writing EPICS Process Variables (PVs)."""

    def __init__(self, enable_dummy_mode: bool = False):
        # Dummy mode allows testing the GUI off-network without crashing
        self.is_active = EPICS_AVAILABLE and not enable_dummy_mode
        
        if not self.is_active:
            logging.info("EPICS Client running in Dummy Mode (No network calls will be made).")

    # --- Write Commands ---
    
    def write_xuv_data(self, projection_array, roi_average: float):
        """Pushes camera calculated data to the lab network."""
        if not self.is_active:
            return
            
        try:
            epics.caput('fel-xuv-mcp-row', projection_array)
            epics.caput('fel-lab-signal', roi_average)
            epics.caput('fel-lab-signal2', roi_average)
        except Exception as e:
            logging.error(f"Failed to write XUV data to EPICS: {str(e)}")

    def write_wavelength(self, wavelength_nm: float):
        """Updates the network with the current grating wavelength."""
        if not self.is_active:
            return
            
        try:
            epics.caput('fel-xuv-grating-wavelength', wavelength_nm)
        except Exception as e:
            logging.error(f"Failed to write wavelength to EPICS: {str(e)}")

    def reset_signals(self):
        """Zeroes out the lab signals. Useful on shutdown/stop."""
        if not self.is_active:
            return
            
        try:
            epics.caput('fel-lab-signal', 0.0)
            epics.caput('fel-lab-signal2', 0.0)
        except Exception as e:
            logging.error(f"Failed to reset EPICS signals: {str(e)}")

    # --- Read Commands ---

    def get_current_wavelength(self) -> float:
        """Fetches the baseline wavelength from the network."""
        if not self.is_active:
            return 0.0  # Fallback for dummy mode
            
        try:
            wl = epics.caget('fel-xuv-grating-wavelength')
            return wl if wl is not None else 0.0
        except Exception as e:
            logging.error(f"Failed to read wavelength: {str(e)}")
            return 0.0

    def get_machine_parameters(self) -> dict:
        """
        Polls the accelerator and beamline states. 
        Used primarily for saving parameters during a data run.
        """
        if not self.is_active:
            return {"status": "Dummy mode active - No EPICS data recorded"}

        try:
            return {
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
                
                # Fetching the array directly; tolist() is called when saving to JSON
                "XUV_spectra": epics.caget('fel-xuv-mcp-row'), 
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
            logging.error(f"Error reading EPICS parameters: {e}")
            return {"error": "EPICS read failure"}