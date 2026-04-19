# XUV Spectrometer Control Dashboard



A modular Python GUI for the HP Spectroscopy XUV system. It integrates live Basler camera feeds, real-time spectral projection processing, and automated Xeryon grating control via a unified dashboard.



## Project Structure

```text

xuv\_project/

├── main.py                # Application entry point

├── README.md              # This file

├── core/                  # Hardware abstraction layer

│   ├── \_\_init\_\_.py

│   ├── camera.py          # Basler camera interface

│   ├── grating.py         # Xeryon motor controller

│   └── epics\_client.py    # EPICS network communications

└── gui/                   # User interface layer

    ├── \_\_init\_\_.py

    └── main\_window.py     # Main Tkinter application

```



## Requirements

Ensure your hardware is connected (Basler camera via network/USB, Xeryon controller on COM4), and the proprietary Xeryon Python SDK is accessible to your environment.



Install the standard Python dependencies:



```Bash

pip install opencv-python pypylon numpy matplotlib pyepics

```

## Usage

To launch the application, navigate to the root directory and run:



```Bash

python main.py

```

