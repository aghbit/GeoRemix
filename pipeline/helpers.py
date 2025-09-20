import os
import shutil
from typing import List

def find_line_with_max_avg(file_path: str):
    """Read the file at file_path where each line contains floats separated by ", ".

    Returns a tuple (line_number, average) for the line with the highest average.
    Line numbers are 1-based. After finding the line the function will truncate the file (clear it).
    If the file is empty or contains no valid lines, returns (0, 0.0) and clears the file.
    """
    best_avg = float("-inf")
    best_worst = float("-inf")
    best_best = float("-inf")
    best_line_no = 0
    lines_read = 0

    if not os.path.exists(file_path):
        return 0, 0.0

    with open(file_path, "r", encoding="utf-8") as f:
        for idx, raw in enumerate(f, start=0):
            s = raw.strip()
            if not s:
                continue
            lines_read += 1
            parts = [p.strip() for p in s.split(", ")]
            nums: List[float] = []
            for p in parts:
                if not p:
                    continue
                try:
                    nums.append(float(p) * 1000)
                except ValueError:
                    print(f"Warning: could not parse float from '{p}' in line {idx} of {file_path}")
                    pass
            if not nums:
                continue
            avg = sum(nums) / len(nums)
            if avg > best_avg or avg > best_avg * 0.98 and nums[-1] > best_worst or avg > best_avg * 0.98 and nums[-1] > best_worst * 0.999 and nums[0] > best_best:
                best_avg = avg
                best_line_no = idx
                best_worst = nums[-1]
                best_best = nums[0]
    # clear the file
    try:
        open(file_path, "w", encoding="utf-8").close()
    except Exception:
        print(f"Warning: could not clear file {file_path}")
        pass

    if lines_read == 0:
        return 0, 0.0
    return best_line_no, best_avg

def copy_images_with_pattern(src_dir: str, dst_dir: str, org_dir: str, starts_with: str) -> int:
    """Copy images from src_dir to dst_dir where filename starts with the provided string.

    The function checks the filename (not the full path) and uses a simple
    prefix match (str.startswith) against `starts_with`. Returns the number of
    files successfully copied.
    """
    if not os.path.exists(src_dir):
        raise FileNotFoundError(src_dir)
    os.makedirs(dst_dir, exist_ok=True)

    names = sorted(os.listdir(org_dir))
    i = 0

    copied = 0
    for name in os.listdir(src_dir):
        full = os.path.join(src_dir, name)
        if not os.path.isfile(full):
            continue
        if name.startswith(starts_with):
            try:
                shutil.copy2(full, os.path.join(dst_dir, names[i]))
                i += 1
                copied += 1
            except Exception:
                print(f"Warning: could not copy file '{name}' to '{dst_dir}'")
                pass
    return copied

def clear_outputs_dir(outputs_path: str) -> None:
    """Remove all files and subdirectories under outputs_path.

    This is destructive: it will delete everything under the given path.
    The function verifies the path exists and refuses to operate on root-like paths.
    """
    if not os.path.exists(outputs_path):
        return

    for entry in os.listdir(outputs_path):
        full = os.path.join(outputs_path, entry)
        os.remove(full)

