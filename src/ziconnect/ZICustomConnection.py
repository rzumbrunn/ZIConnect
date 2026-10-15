import time

import matplotlib.pyplot as plt
import zhinst.toolkit as tk


def init_session(host: str="mfli-torus.ethz.ch"):
    """
    Initializes a session to the Zurich Instruments LabOne server.

    Parameters
    ----------
    host : str, optional
        The hostname of the Zurich Instruments LabOne server. Default is "mfli-torus.ethz.ch".

    Returns
    -------
    session : zhinst.toolkit.Session
        An instance of the Session class representing the connection to the LabOne server.
    """
    session = tk.Session(host)
    return session



def get_raw_phase(session: tk.Session, serial: str, channel: int = 0):
    """
    Retrieves the raw phase of a specified channel from a Zurich Instruments device.

    Parameters
    ----------
    session : zhinst.toolkit.Session
        An instance of the Session class representing the connection to the LabOne server.
    serial : str
        The serial number of the Zurich Instruments device.
    channel : int
        The channel number for which to retrieve the raw phase.

    Returns
    -------
    float
        The raw phase value of the specified channel.
    """
    # daq_module.subscribe('/dev3917/demods/1/sample.Theta.fft.abs.pwr.avg')

def get_phase_noise(session: tk.Session, serial: str, channel: int = 0):
    """
    Retrieves the phase noise of a specified channel from a Zurich Instruments device.

    Parameters
    ----------
    session : zhinst.toolkit.Session
        An instance of the Session class representing the connection to the LabOne server.
    serial : str
        The serial number of the Zurich Instruments device.
    channel : int
        The channel number for which to retrieve the phase noise.

    Returns
    -------
    float
        The phase noise value of the specified channel.
    """
    device = session.connect_device(serial)

    daq_module = session.modules.daq

    import numpy as np
    frequency_span = 20000  # Frequency span in Hz
    # frequency_res = 0.1   # Frequency resolution bins/Hz
    frequency_res = 10   # Frequency resolution bins/Hz

    number_of_bins = int(np.pi * frequency_span / frequency_res)
    duration = 1 / frequency_res  # Duration of the measurement in seconds

    print(f"Number of bins: {number_of_bins}, Duration: {duration} seconds")

    

    with session.set_transaction():  
        daq_module.device(device)
        daq_module.type(0) # continuous acquisition
        daq_module.spectrum.enable(1)
        daq_module.grid.mode(2)
        daq_module.grid.repetitions(1)

        daq_module.grid.cols(number_of_bins)  # Number of frequency bins
        daq_module.duration(duration)  # Duration of the measurement in seconds
        # for options see: https://docs.zhinst.com/labone_api_user_manual/modules/daq/index.html#spectrum
        

    daq_module.unsubscribe("*") 
    device.demods[channel].enable(True)
    # device.demods[channel].rate(sampling_rate)


    
    sample_nodes = [
        # device.demods[channel].sample.x,
        # device.demods[channel].sample.y,
        device.demods[channel].sample.phase.fft.abs.pwr.avg,
    ]

    for sample_node in sample_nodes:
        daq_module.subscribe(sample_node)


    daq_module.execute()

    while daq_module.progress() < 1.0 and not daq_module.finished():
        print(f"Progress: {daq_module.progress() * 100:.2f}%", end="\r")
        time.sleep(0.1)
        result = daq_module.read(raw=False)

    # print(result)

    # successfull_nodes = [node for node in sample_nodes if node in result]
    successfull_nodes = []
    failed_nodes = []
    for node in sample_nodes:
        if node in result:
            successfull_nodes.append(node)
        else:
            failed_nodes.append(node)

    for node in failed_nodes:
        print(f"Failed to retrieve data for node: {node}")

    fig, ax = plt.subplots(1, len(successfull_nodes), figsize=(10, 5))
    for i, node in enumerate(successfull_nodes):
        data = result[node]

        timeplot = False
        freqplot = False
        if data[0].time is not None:
            timeplot = True
            x_value = data[0].time
        elif data[0].frequency is not None:
            freqplot = True
            x_value = data[0].frequency

        values = data[0].value

        if len(successfull_nodes) == 1:
            ax = [ax]  # Ensure ax is iterable when there's only one subplot
        ax[i].plot(x_value, values[0])
        ax[i].set_title(f"Node: {node}")
        ax[i].set_ylabel("Value")
        if freqplot:
            ax[i].set_xlabel("Frequency (Hz)")
            ax[i].set_yscale("log")\
            



    print(f"bin spacing: {np.mean(np.diff(x_value))}")
    fig.tight_layout()
    plt.figure()
    plt.plot(x_value, np.fft.fftshift(np.fft.fft(values[0])))
    
    plt.show()