import os
import time
from typing import List
import urllib
import urllib.request


def interrupt_queue(server_address):
    req = urllib.request.Request(f"http://{server_address}/interrupt", method='POST')
    try:
        urllib.request.urlopen(req)
        print("Queue interrupted successfully.")
    except Exception as e:
        print(f"Failed to interrupt queue: {e}")


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
            print(nums)
            if not nums:
                continue
            avg = sum(nums) / len(nums)
            print(f"Line {idx} average: {avg}")
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

if __name__ == "__main__":
    # server_address = "127.0.0.1:8188"  # Update this if your server address is different
    # i = 0
    # while i < 350:
    #     interrupt_queue(server_address)
    #     time.sleep(0.2)
    #     i+=1
    print(find_line_with_max_avg("/home/kn-bit/comfy/ComfyUI/temp/file.txt"))