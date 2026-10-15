import json
import math
import os
import re

import zhinst.toolkit as tk
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from ziconnect.settings import CONFIG_BASE_PATH


def flatten(tree: dict, prefix: str=""):
    for key, val in tree.items():
        key = key[2:] if re.fullmatch(r"ch\d+", key) else key
        if isinstance(val, dict):
            yield from flatten(val, f"{prefix}/{key}")
        else:
            yield f"{prefix}/{key}", val

def to_number(s):
    try:
        return int(s)
    except ValueError:
        return float(s)

def load_settings(path: os.PathLike|str, session: tk.Session, serial: str, no_confirmation: bool=False):
    """
    load_settings Loads settings from a normalized setting.json file (raw version is exportable form ZI directly). The settings are put directly onto the ZI machine
    Example usage:
    ```
    failed = load_settings("settings.json", "data-server-host", "dev3917")
    ```

    Args:
        path (str): The path to the settings JSON file. (normalized)
        session (zhinst.toolkit.Session): The session object representing the connection to the LabOne server.
        serial (str): The serial number of the device.
        no_confirmation (bool): If True, no confirmation will be requested before applying the settings.

    Returns:
        failed (list): A list of settings that failed to be applied.
    """
    path = os.path.join(CONFIG_BASE_PATH, path)

    with open(path) as f:
        dev = json.load(f)["settings"]["deviceSettings"][0]

    items = [(f"/{serial}{p}", to_number(v)) for p, v in flatten(dev["nodes"])]
    # heuristic: apply enables/outputs last so everything is configured first
    items.sort(key=lambda kv: kv[0].rsplit("/", 1)[-1] in ("enable", "on", "enables"))

    failed = []

    if not no_confirmation:
        # caculate settings diff
        changed = []
        old = []
        for p, v in (pbar := tqdm(items, desc="Calculating settings diff", unit="setting", ncols=80)):
            try:
                got = session.daq_server.getDouble(p)
                if not math.isclose(got, v, rel_tol=1e-6, abs_tol=1e-12):
                    changed.append((p, v))
                    old.append((p, got))
            except Exception:
                changed.append((p, v))

        console = Console()
        changed_table = Table(title="Settings to apply", show_lines=True)
        changed_table.add_column("Path", style="cyan", no_wrap=True)
        changed_table.add_column("Old Value", style="red")
        changed_table.add_column("New Value", style="green")
        for p, v in changed:
            changed_table.add_row(p,  str(old[changed.index((p, v))][1]), str(v))
        console.print(changed_table)
            
        if input("Apply settings? (y/n): ").lower() != "y":
            print("Aborting settings application.")
            return [], []
    

    for p, v in (pbar := tqdm(changed, desc="Applying settings", unit="setting", ncols=80)):
        pbar.set_postfix_str(f"{p} = {v}")
        try:
            session.daq_server.set(p, v)
        except Exception as e:
            failed.append((p, v, str(e)))

    return failed



def normalize(src: os.PathLike, dst: os.PathLike):
    """
    Normalizes the settings JSON file by removing certain fields and writing the result to a new file. This helps with version control and comparison of settings files.

    Args:
        src (str): The path to the source settings JSON file.
        dst (str): The path to the destination settings JSON file.
    """
    with open(os.path.join(CONFIG_BASE_PATH, src)) as f:
        data = json.load(f)
    s = data["settings"]
    s.pop("uiSettings", None)
    s["head"].pop("modified", None)
    with open(os.path.join(CONFIG_BASE_PATH, dst), "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")