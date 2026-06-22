#!/usr/bin/env python
# coding=utf-8
import os
import shutil
import sys
from tqdm import tqdm
import subprocess
from datetime import datetime
from pathlib import Path

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def path_parse(folder_path, depth=2):
    try:
        path = Path(folder_path).resolve()  # Resolves symlinks and normalizes
        parts = path.parts

        if len(parts) < depth:
            raise ValueError(f"Path too shallow. Expected at least {depth} components, got {len(parts)}")

        site_name = parts[-1]
        city_name = parts[-2]

        return city_name, site_name

    except Exception as e:
        raise ValueError(f"Error processing path '{folder_path}': {e}")


def convert_colmap(rc_exe,
                   folder_path,
                   headless=True,
                   extra_args=None):
    folder_path = str(folder_path).replace("\\", "/")
    scene_name = os.path.basename(folder_path)
    project_file = f"{folder_path}/{scene_name}.rsproj"
    colmap_folder = f"{folder_path}/colmap/sparse/0/"
    image_folder = f"{folder_path}/colmap/images"

    tmp_folder = f"{folder_path}/tmp/"
    os.makedirs(tmp_folder, exist_ok=True)
    shutil.copytree(colmap_folder, tmp_folder, dirs_exist_ok=True)
    shutil.copytree(image_folder, tmp_folder, dirs_exist_ok=True)

    if extra_args is None:
        extra_args = []
    args = [rc_exe]
    # headless mode
    if headless:
        args.append("-headless")
    args.append(f"-loadColmap")
    args.append(f"{tmp_folder}/points3D.txt")
    args.append("-save")
    args.append(project_file)
    args.extend(extra_args)
    args.append("-quit")

    msg = f"[{now()}] " + "Running Colmap to RC with arguments:\n"
    for a in args:
        if a.startswith("-"):
            msg += f"\n\t{a}"
        else:
            msg += f" {a}"
    # print(msg)

    try:
        proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(f"[{now()}] ", "Error calling RealityCapture CLI:", e)
        sys.exit(1)

    shutil.rmtree(tmp_folder, ignore_errors=True)
    return "done"


if __name__ == "__main__":
    """
    1. 扫描有什么场景；
    2. 对每个场景，检测是否有rc工程文件，如果有，跳过；没有就执行；
    3. 对每个场景，检测是否有colmap/sparse/0/points3D.txt，如果有，就把colmap转换成rc
    """
    folder_path = sys.argv[1]
    folder_path = str(folder_path).replace("\\", "/")
    rc_exe = "F:\software\RealityScan_2.1\RealityScan.exe"
    if not os.path.isfile(rc_exe):
        print(f"Error: RealityCapture executable not found at: {rc_exe}")
        sys.exit(1)

    sub_folders = os.listdir(folder_path)
    sub_folders.sort()
    failed_list = []
    skip_list = []
    done_list = []
    for sub_folder in tqdm(sub_folders):
        print(f"\n[Post Processing RC]: Processing folder: {sub_folder}")

        if not os.path.isfile(f"{folder_path}/{sub_folder}/colmap/sparse/0/points3D.txt"):
            failed_list.append(sub_folder)
            print(f"{sub_folder} is failed, no colmap!", end='\n')
            continue

        if os.path.isfile(f"{folder_path}/{sub_folder}/{sub_folder}.rsproj"):
            skip_list.append(sub_folder)
            print(f"{sub_folder}.rsproj exists, skipped!", end='\n')
            continue

        convert_colmap(rc_exe, f"{folder_path}/{sub_folder}", headless=False)
        done_list.append(sub_folder)
        print(f"{sub_folder} is done!", end='\n')

    print(f"\n[Post Processing RC]: "
          f"\n\tSkipped are {skip_list}, "
          f"\n\tFailed (require redo) are {failed_list}, "
          f"\n\tSuccessed are {done_list}, ")