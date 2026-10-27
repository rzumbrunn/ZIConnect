import time

import matplotlib.pyplot as plt
import numpy as np
import zhinst.toolkit as tk


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
    session = init_session(host, port)
    daq_module = session.modules.daq
    daq_module.grid.mode(4) # 0 off, 1 nearest, 2, linear, 3 exact, 4 magic????
    daq_module.type(0)
    daq_module.preview(1)
    daq_module.grid.rows(10)
    daq_module.grid.rowrepetition(1)
    daq_module.grid.waterfall(1)
    daq_module.grid.overwrite(1)
    daq_module.device(serial)
    daq_module.historylength(1)
    daq_module.delay(0)
    daq_module.spectrum.enable(1)
    daq_module.spectrum.frequencyspan(frequency_span *(2/np.pi)*2) # works well for X,Y and xiy, but not for theta
    daq_module.spectrum.autobandwidth(1)
    session.devices[serial].demods[channel].timeconstant(1.0 / (2 * np.pi * 2 * frequency_span)) # adjust filter time constant to match the aquisition bandwidth f_3db = (1/(2*pi * tau))
    daq_module.grid.cols(round_to_nearest_order_of_two(2*frequency_span / frequency_res))
    daq_module.save.directory('/root/Zurich Instruments/LabOne/WebServer')
    daq_module.endless(0)

    subscriptions = [
        f'/{serial}/demods/{channel}/sample.Theta.fft.abs.pwr.avg'
        # f'/{serial}/demods/{channel}/sample.xiy.fft.abs.pwr.avg'
        # f'/{serial}/demods/{channel}/sample.Y.fft.abs.pwr.avg'
    ] 
    for sub in subscriptions:
        daq_module.subscribe(sub)
    
    daq_module.execute()
    result = 0
    while daq_module.progress() < 1.0 and not daq_module.finished():
        time.sleep(1)
        result = daq_module.read()
        print(f"Progress {float(daq_module.progress()) * 100:.2f} %\r")
    daq_module.finish()
    daq_module.unsubscribe('*')
    print("Data acquisition finished.")


    sub_results = {}
    for sub in subscriptions:
    
        try:  
            # VHFLI also has triggered data so we first need to remove it for now
            if "/triggered" in sub:
                continue
            sub_results[sub] = result[sub.lower()]
        except KeyError:
            print(f"Failed to retrieve data for subscription: {sub}")

    # print(sub_results)
    for sub, data in sub_results.items():
        for i, d in enumerate(data): # for every datapoint (row)

            #TODO: only works on sample.theta.fft.abs.pwr.avg

            headers = d.header

            bandwidth = headers['bandwidth']
            normalized_equivalent_noise_bandwidth = headers['nenbw']   
            print(f"Bandwidth: {bandwidth[0]} Hz, Normalized Equivalent Noise Bandwidth: {normalized_equivalent_noise_bandwidth[0]} Hz")
            center_frequency = headers['center'] # pre demodulation

            freq_num = headers['gridcols'][0] # number of bins


            values = d.value.T # for theta, that value is in rad^2/Hz
            values = values * (180 / np.pi) ** 2 # convert to deg^2/Hz, as in LabOne
            mean_values = np.mean(values, axis=1)
            frequencies = d.frequency
            freq_range = [
                frequencies[0],    
                frequencies[-1],
            ]
            freq_delta = frequencies[1] - frequencies[0]


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
