import time
from pathlib import Path

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
    session: tk.Session,
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
                session=session,
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
    session: tk.Session,
    serial: str,
    channel: int = 0,
    frequency_span: float = 20000,
    frequency_res: float = 50,
    no_samples: int = 10,
    plot: bool = True,
    reference_data_path: str | Path | None = None,
):
    """
    get_phase_noise_direct _summary_

    Args:
        host (str): _description_
        port (int): _description_
        serial (str): _description_
        channel (int, optional): _description_. Defaults to 0.
        frequency_span (float, optional): The frequency span of the spectrum. The usable bandwidth will be half of that to make sure we don't have aliasing. Defaults to 20000.
        frequency_res (float, optional): _description_. Defaults to 50.
        no_samples (int, optional): _description_. Defaults to 10.
        plot (bool, optional): _description_. Defaults to True.
        reference_data_path (str | Path | None, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    # session = init_session(host, port)
    daq_module = session.modules.daq
    daq_module.grid.mode(4) # 0 off, 1 nearest, 2, linear, 3 exact, 4 magic????
    daq_module.type(0)
    daq_module.preview(1)
    daq_module.grid.rows(1)
    daq_module.grid.repetitions(10)
    daq_module.grid.rowrepetition(1)
    daq_module.grid.waterfall(1)
    daq_module.grid.overwrite(1)
    daq_module.device(serial)
    daq_module.historylength(1)
    daq_module.delay(0)
    daq_module.spectrum.enable(1)

    sample_points = round_to_nearest_order_of_two(2 * frequency_span / frequency_res)
    adjusted_frequency_span = sample_points * frequency_res / 2
    rate = 2 * adjusted_frequency_span * np.pi *2

    filter_margin_factor =4 # how much tighter should the filter be compared to the bandwidth of daq
    session.devices[serial].demods[channel].timeconstant(1.0 / (2*np.pi *2*adjusted_frequency_span/filter_margin_factor)) # adjust filter time constant to match the aquisition bandwidth f_3db = (1/(2*pi * tau))
    daq_module.spectrum.frequencyspan(2*adjusted_frequency_span)
    # session.devices[serial].demods[channel].rate(rate)
    print(f"requested rate: {rate}")



    daq_module.grid.cols(sample_points)
    daq_module.endless(0)

    subscriptions = [
        f'/{serial}/demods/{channel}/sample.Theta.fft.abs.pwr.avg'
        # f'/{serial}/demods/{channel}/sample.xiy.fft.abs.pwr.avg'
        # f'/{serial}/demods/{channel}/sample.X.fft.abs.avg'
        # f'/{serial}/demods/{channel}/sample.Theta.fft.abs.avg'
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
            freq_delta = headers['gridcoldelta'][0] # frequency resolution

            freq_num = headers['gridcols'][0] # number of bins


            values = d.value.T # for theta, that value is in rad^2/Hz
            values = values *2 # both sided spectrum? (TODO: check if this is correct)
            values = values * (180 / np.pi) ** 2 # convert to deg^2, as in LabOne
            values = values/ (normalized_equivalent_noise_bandwidth[0] * freq_delta)  # convert to deg^2/Hz, as in LabOne
            # values = values/normalized_equivalent_noise_bandwidth[0]  Not sure if this is correct.
            mean_values = np.mean(values, axis=1)
            frequencies = d.frequency
            freq_range = [
                frequencies[0],    
                frequencies[-1],
            ]
            freq_delta = frequencies[1] - frequencies[0]

            ref_data = np.loadtxt('data/tmp/dev13087_demods_2_sample_theta_fft_abs_pwr_avg_00001.csv', delimiter=";", skiprows=1)
            # ref_freqs = ref_data[:, 1]
            ref_values = ref_data[:, 2] * (180 / np.pi) ** 2  # Convert to deg^2, as in LabOne
            ref_values = ref_values / (normalized_equivalent_noise_bandwidth[0] * freq_delta)  # convert to deg^2/Hz, as in LabOne
            ref_freqs = np.linspace(freq_range[0], freq_range[1], len(ref_values))  # Create a frequency array for the reference data

            #resample the reference data to match the frequencies of the acquired data
            from scipy.interpolate import interp1d
            interp_func = interp1d(ref_freqs, ref_values, kind='linear', fill_value="extrapolate")
            ref_values = interp_func(frequencies) 
            # Resample the real data to match the reference frequencies
            # interp_func = interp1d(frequencies, values, kind='linear', fill_value="extrapolate")
            # values = interp_func(ref_freqs)  # Interpolate reference values to match the acquired frequencies
            # frequencies = ref_freqs  # Update frequencies to match the reference frequencies

            # print average ratio
            print(f"Average ratio of measured to reference: {np.mean(mean_values[100:] / ref_values[100:])}")


            print("SET")
            print(f"frequency span: {adjusted_frequency_span} Hz, frequency res: {frequency_res} Hz") 
            print("ACTUAL")
            print(f"frequency span: {freq_range[1] - freq_range[0]} Hz, frequency res: {freq_delta} Hz - Bins {freq_num}") 
            if plot:
                plt.figure(figsize=(10, 5))
                plt.plot(frequencies, values, alpha=0.4) # not sure if this is correct. But this qualitatively matches the web ui. For more info see: https://www.zhinst.com/ch/en/blogs/how-control-spectral-leakage-window-functions-labone/ 
                plt.plot(frequencies, mean_values, color='black', linewidth=2, label='Mean')
                plt.plot(frequencies, ref_values, color='red', linewidth=2, label='Reference')
                #plt.plot(frequencies, np.nan_to_num(mean_values/ref_values), color='black', linewidth=2, label='Measured')
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
