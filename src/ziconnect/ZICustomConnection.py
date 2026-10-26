import time

import matplotlib.pyplot as plt
import numpy as np
import zhinst.core as zi
import zhinst.toolkit as tk

from ziconnect.settings import API_LEVEL


class LabOneConnectionError(ConnectionError):
    """Raised when the LabOne server cannot be reached on the requested port."""


def init_session(host: str="mfli-torus.ethz.ch", port: int=8004) -> tk.Session:
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
    try:   
        session = tk.Session(host, port)
    except Exception as e:
        # ping the host to check if it's reachable
        import subprocess
        success = False
        try:
            subprocess.check_call(["ping", "-c", "1", host])
            success = True
        except subprocess.CalledProcessError:
            raise ConnectionError(f"Cannot reach host {host}. Please check the hostname and your network connection.") from e
        if success:
            raise LabOneConnectionError(
                f"The host {host} is reachable, but the LabOne server could not be connected to "
                f"on port {port}. Please check that the LabOne server is running."
            ) from e
    # dev1 = session.connect_device("DEV1234")
    return session

def round_to_nearest_order_of_two(value: float) -> float:
    if value <= 0:
        raise ValueError("Value must be positive.")
    order_of_two = 2 ** round(np.log2(value))
    return order_of_two

def get_phase_noise_direct_retry(
    host: str,
    port: int,
    serial: str,
    retries: int = 10,
    channel: int = 0,
    frequency_span: float = 20000,
    frequency_res: float = 10,
    no_samples: int = 10,
    plot: bool = True,
):
    """
    get_phase_noise_direct_retry Gets the phase noise from the PLL. If none data is returned, tries again until it works, or until backoff is reached

    Args:
        host (str): LabOne server host.
        port (int): LabOne server port.
        serial (str): Device serial number.
        channel (int, optional): Channel number. Defaults to 0.
        frequency_span (float, optional): Frequency span. Defaults to 20000.
        frequency_res (float, optional): Frequency resolution. Defaults to 10.
        plot (bool, optional): Whether to plot the results. Defaults to True.
    """
    for attempt in range(retries):
        try:
            pn, freqs =  get_phase_noise_direct(
                host=host,
                port=port,
                serial=serial,
                channel=channel,
                frequency_span=frequency_span,
                frequency_res=frequency_res,
                no_samples=no_samples,
                plot=plot, 
            )
            if np.isnan(np.sum(pn)):
                raise ValueError("Received NaN values in phase noise data.")
            return pn, freqs

        except ValueError as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                print("Retrying...")
            else:
                print("All attempts failed.")
                raise



def get_phase_noise_direct(
    host: str,
    port: int,
    serial: str,
    channel: int = 0,
    frequency_span: float = 20000,
    frequency_res: float = 50,
    no_samples: int = 10,
    plot: bool = True,
):
    daq = zi.ziDAQServer(host, port, api_level=API_LEVEL)
    daq_module = daq.dataAcquisitionModule()

    subscriptions = [
        f'/{serial}/demods/{channel}/sample.Theta.fft.abs.pwr.avg'

    ]

    # sampling_rate = daq.get(f"/{serial}/demods/{channel}/rate")
    sampling_rate = daq.get(f"/{serial}/demods/{channel}/rate")[serial]['demods'][str(channel)]['rate']['value'][0]
    
    # print(sampling_rate)


    # Debug
    # set_bins= 4000 # doubling -> doubles frequency resolution
    #set_duration =4 #doubling -> literally nothing
    # set_span = 40000 # doubling -> doubles both resolution and span

    set_bins = round_to_nearest_order_of_two(frequency_span / frequency_res)
    set_span = frequency_span
    # print(f"Set bins {set_bins}, Set span {set_span}, Set duration {4}")
    # print(f"Frequency resolution: {set_span / set_bins} Hz")



    # print(f"Set bins {set_bins}, Set span {set_span}, Set duration {set_duration}")

    # daq_module.set('preview', 1)
    daq_module.set('type', 0)
    daq_module.set('grid/rows', 5)
    daq_module.set('device', serial)
    daq_module.set('delay', 0)
    daq_module.set('spectrum/enable', 1)

    daq_module.set('save/directory', '/data/LabOne/WebServer/phase_noise_data')

    daq_module.set('grid/cols', set_bins)
    daq_module.set('spectrum/frequencyspan', set_span)

    daq.set(f"/{serial}/demods/{channel}/enable", 1)


    daq_module.set('clearhistory', 1)
    daq_module.set('endless', 0)
    for sub in subscriptions:
        daq_module.subscribe(sub)
    daq_module.execute()
    result = 0
    print("Waiting for data...")
    while daq_module.progress()[0] < 1.0 and not daq_module.finished():
        time.sleep(0.1)
        result = daq_module.read()
        print(f"Progress: {daq_module.progress()[0] * 100:.2f}%", end="\r")
    daq_module.finish()
    daq_module.unsubscribe('*')

    print("Data acquisition finished.")
    sub_results = {}
    for sub in subscriptions:
        try:  
            current_head = result
            for path_part in sub.lower().strip('/').split('/'):
                current_head = current_head[path_part]
            sub_results[sub] = current_head
        except KeyError:
            print(f"Failed to retrieve data for subscription: {sub}")

    # print(sub_results)
    for sub, data in sub_results.items():
        for i, d in enumerate(data): # for every datapoint (row)

            #TODO: only works on sample.theta.fft.abs.pwr.avg

            headers = d['header']

            bandwidth = headers['bandwidth']
            normalized_equivalent_noise_bandwidth = headers['nenbw']   
            center_frequency = headers['center'] # pre demodulation

            freq_delta = headers['gridcoldelta'][0] # spacing between bins
            freq_num = headers['gridcols'][0] # number of bins
            freq_offset = headers['gridcoloffset'][0] #offset of first bin

            freq_range = [
                freq_offset,    
                freq_delta * (freq_num-1) + freq_offset,
            ]

            values = d['value'].T
            mean_values = np.mean(values, axis=1)
            frequencies = np.linspace(freq_range[0], freq_range[1], freq_num)


            print("SET")
            print(f"frequency span: {frequency_span} Hz, frequency res: {frequency_res} Hz") 
            print("ACTUAL")
            print(f"frequency span: {freq_range[1] - freq_range[0]} Hz, frequency res: {freq_delta} Hz - Bins {freq_num}") 
            if plot:
                plt.figure(figsize=(10, 5))
                plt.plot(frequencies, values, alpha=0.4) # not sure if this is correct. But this qualitatively matches the web ui. For more info see: https://www.zhinst.com/ch/en/blogs/how-control-spectral-leakage-window-functions-labone/ 
                plt.plot(frequencies, mean_values, color='black', linewidth=2, label='Mean')
                plt.title(rf"Subscription: {sub} - Data Point {i}: Frequency Resolution: {freq_delta:.2f} Hz - BW: {bandwidth[0]:.2f} Hz ")
                plt.xlabel("Frequency (Hz)")
                plt.ylabel("Value")
                plt.yscale("log")
                plt.xscale("log")
                plt.grid()  
    if plot:
        plt.show() 
    # return sub_results  
    return mean_values, frequencies
