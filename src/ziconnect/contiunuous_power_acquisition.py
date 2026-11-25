"""
Continuous power acquisition from the scope (raw, non-demodulated signal).

The scope is read out in consecutive records ("samples"). Each record is long enough
to give a frequency resolution of at least `freq_res` (df = fs / N <= freq_res).
Records are acquired until the summed length of all records reaches `duration`,
and every record is stored as its own file.

Output layout (one folder per acquisition):

    <out_dir>/<serial>_<YYYYmmdd_HHMMSS>/
        meta.json                 # acquisition-wide parameters
        sample_00000.npz          # wave, dt, fs, t_start, index, ...
        sample_00001.npz
        ...
"""

import json
import math
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import zhinst.toolkit as tk

SCOPE_INDEX = 0
MIN_SCOPE_LENGTH = 4096  # smallest record length we ask the scope for


def _next_pow2(n: int) -> int:
    return 1 << max(0, math.ceil(math.log2(n)))


def _scope_time_setting(clockbase: float, requested_fs: float) -> tuple[int, float]:
    """
    The scope sampling rate is clockbase / 2**time. Pick the integer `time` whose rate is
    closest to (but not above) the requested rate, and return (time, actual_fs).
    """
    t = max(0, math.ceil(math.log2(clockbase / requested_fs)))
    return t, clockbase / 2**t


def acquire_power(
    session: tk.Session,
    serial: str,
    duration: float,
    freq_res: float,
    sample_rate: float,
    input_channel: int = 0,
    out_dir: str | Path = "data/power",
    timeout_per_record: float = 10.0,
) -> Path:
    """
    Acquire raw scope records until the total recorded time equals `duration`.

    Args:
        session: Connected LabOne session.
        serial: Device serial, e.g. "dev13087".
        duration: Total recorded time over all samples (s).
        freq_res: Required frequency resolution (Hz). Each record has N >= fs / freq_res points.
        sample_rate: Requested scope sampling rate (Sa/s). Snapped to clockbase / 2**n.
        input_channel: Scope input channel (0 = channel 1).
        out_dir: Base folder for the output.
        timeout_per_record: Max wait (s) beyond the expected record time before giving up.

    Returns:
        Path of the folder containing the saved samples.
    """

    #print available devices
    print("Available devices:")
    for dev in session.devices:
        print(dev)

    device = session.devices[serial]
    scope_node = device.scopes[SCOPE_INDEX]

    # --- timing / record length -------------------------------------------------------
    clockbase = session.daq_server.getDouble(f"/{serial}/clockbase")
    time_setting, fs = _scope_time_setting(clockbase, sample_rate)
    dt = 1.0 / fs

    n_points = max(_next_pow2(math.ceil(fs / freq_res)), MIN_SCOPE_LENGTH)
    record_time = n_points * dt
    actual_df = fs / n_points
    n_records = math.ceil(duration / record_time)  # last record may overshoot slightly

    print(
        f"fs = {fs:.4g} Sa/s | N = {n_points} | df = {actual_df:.4g} Hz (requested <= {freq_res} Hz) | "
        f"record = {record_time:.4g} s | records = {n_records} | total = {n_records * record_time:.4g} s"
    )

    # --- output folder ----------------------------------------------------------------
    run_dir = Path(out_dir) / f"{serial}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = dict(
        serial=serial,
        fs=fs,
        dt=dt,
        n_points=n_points,
        freq_res_requested=freq_res,
        freq_res_actual=actual_df,
        duration_requested=duration,
        n_records=n_records,
        input_channel=input_channel,
        clockbase=clockbase,
    )
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    # --- scope configuration ----------------------------------------------------------
    with device.set_transaction():
        scope_node.enable(0)
        scope_node.single(0)  # continuous re-arming, the scope module collects the records
        scope_node.channel(1 << input_channel)  # bit mask of enabled channels
        scope_node.channels[input_channel].inputselect(0)  # signal input 1; adapt if needed
        scope_node.time(time_setting)
        scope_node.length(n_points)
        scope_node.trigenable(0)  # free-running, no trigger
        scope_node.segments.enable(0)

    # Make sure the device accepted the settings
    actual_length = int(scope_node.length())
    if actual_length != n_points:
        raise RuntimeError(f"Scope length {n_points} not accepted by device (got {actual_length}).")

    scope = session.modules.scope
    scope.mode(1)  # time domain
    # scope.averager.weight(1)  # 1 = no averaging, every record is kept
    scope.historylength(max(10, min(n_records, 100)))
    scope.clearhistory(1)

    wave_path = f"/{serial}/scopes/{SCOPE_INDEX}/wave"
    scope.subscribe(wave_path)

    # --- acquisition ------------------------------------------------------------------
    seen = set()  # created-timestamps of records we already saved
    saved = 0
    t0 = time.time()

    scope.execute()
    scope_node.enable(1)
    try:
        last_progress = time.time()
        while saved < n_records:
            records = scope.read().get(wave_path, [])
            new_data = False
            for rec in records:
                ts = int(rec[0]["header"]["createdtimestamp"][0])
                if ts in seen:
                    continue
                seen.add(ts)
                new_data = True

                wave = np.asarray(rec[0]["wave"])  # (channels, samples)
                wave = wave[0] if wave.ndim > 1 else wave

                np.savez(
                    run_dir / f"sample_{saved:05d}.npz",
                    wave=wave.astype(np.float64),
                    index=saved,
                    fs=fs,
                    dt=dt,
                    n_points=len(wave),
                    freq_res=fs / len(wave),
                    timestamp_device=ts,  # device clock ticks (clockbase)
                    timestamp_host=time.time(),
                )
                saved += 1
                print(f"Saved record {saved}/{n_records}", end="\r")
                if saved >= n_records:
                    break

            if new_data:
                last_progress = time.time()
            elif time.time() - last_progress > record_time + timeout_per_record:
                raise TimeoutError(f"No new scope record for {time.time() - last_progress:.1f} s.")
            else:
                time.sleep(min(0.05, record_time / 4))
    finally:
        scope_node.enable(0)
        scope.finish()
        scope.unsubscribe("*")

    print(f"\nDone. {saved} records ({saved * record_time:.4g} s) in {time.time() - t0:.1f} s -> {run_dir}")
    return run_dir


def load_samples(run_dir: str | Path, num_samples: int | None = None) -> tuple[dict, list[np.ndarray]]:
    """Load all saved samples of one acquisition. Returns (meta, list_of_waves)."""
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "meta.json").read_text())
    waves = []
    for f in sorted(run_dir.glob("sample_*.npz")):
        if num_samples is not None and len(waves) >= num_samples:
            break
        waves.append(np.load(f)["wave"])
    return meta, waves

def downsample(run_dir: str | Path, factor: int, verbose: bool = False) -> None:
    """Downsample all saved samples of one acquisition by the given factor."""
    run_dir = Path(run_dir)
    (run_dir / "ds").mkdir(parents=True, exist_ok=True)
    for f in sorted(run_dir.glob("sample_*.npz")):
        if verbose:
            print(f"Downsampling {f} by factor {factor}...")
        data = np.load(f)
        wave = data["wave"]
        wave_ds = wave[::factor]
        np.savez(
            # run_dir + "/ds/" + f.with_suffix("").name+".npz",
            os.path.join(run_dir, "ds", f.with_suffix("").name + ".npz"),
            wave=wave_ds.astype(np.float64),
            index=data["index"],
            fs=data["fs"] / factor,
            dt=data["dt"] * factor,
            n_points=len(wave_ds),
            freq_res=data["freq_res"] * factor,
            timestamp_device=data["timestamp_device"],
            timestamp_host=data["timestamp_host"],
        )
def collect_downsampled(run_dir: str | Path, factor: int, verbose: bool = False) -> None:
    """Collect all downsampled samples of one acquisition into a single file."""
    run_dir = Path(run_dir)
    ds_dir = run_dir / "ds"
    if not ds_dir.exists():
        raise FileNotFoundError(f"Downsampled directory {ds_dir} does not exist.")
    waves = []
    times = []
    t0 = 0
    td0 = 0

    host_timestamps = []
    for f in sorted(ds_dir.glob("sample_*.npz")):
        if verbose:
            print(f"Loading {f}...")
        data = np.load(f)
        if t0 == 0:
            t0 = data["timestamp_host"]
        if td0 == 0:
            td0 = data["timestamp_device"]
        waves.append(data["wave"])
        timesteps = np.arange(len(data["wave"])) * data["dt"] + data["timestamp_host"] - t0
        host_timestamps.append(data["timestamp_host"])
        times.append(timesteps)
    waves = np.concatenate(waves)
    times = np.concatenate(times)
    
    np.savez(
        run_dir / f"downsampled_{factor}.npz",
        wave=waves.astype(np.float64),
        times=times.astype(np.float64),
        host_timestamps=np.array(host_timestamps, dtype=np.float64),
        fs=data["fs"],
        dt=data["dt"],
        n_points=len(waves),
        freq_res=data["freq_res"],
        timestamp_device=td0,
        timestamp_host=t0,
    )


if __name__ == "__main__":

    # session = ZICustomConnection.init_session("exp-pc-torus.ethz.ch", 8004)
    from ziconnect import ZICustomConnection
    session = ZICustomConnection.init_session("10.147.2.20", 8004)
    acquire_power(
        session,
        serial="dev3917",
        duration=3600,   # s total over all samples
        freq_res=100.0,  # Hz
        sample_rate=10e6,  # Sa/s (snapped to clockbase / 2**n)
    )

    # samples = load_samples("data/power/dev3917_20261123_111038")
    # samples = load_samples("data/power_remote/dev3917_20261123_111737")
    # samples = load_samples("data/power_remote/dev3917_20261123_174831")

    # samples = load_samples("data/power_remote/dev3917_20261123_111737", num_samples=10)
    # print("downsampling")
    # # downsample("data/power_remote/dev3917_20261123_111737", factor=100, verbose=True)
    # collect_downsampled("data/power_remote/dev3917_20261123_111737", factor=100, verbose=True)
    
    # print("downsampling")
    # #downsample("data/power_remote/dev3917_20261123_174831", factor=100, verbose=True)
    # collect_downsampled("data/power_remote/dev3917_20261123_174831", factor=100, verbose=True)





    # plt.plot(samples[1][0])
    # plt.show()

