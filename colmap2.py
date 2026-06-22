#!/usr/bin/env python
# coding=utf-8
import os
import shutil
import sys
import zipfile
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

    # 定义压缩包路径
    zip_file_path = f"{folder_path}/rc_colmap.zip"
    # 定义临时的解压释放目录
    extracted_folder = f"{folder_path}/colmap_extracted/"

    print(f"[{now()}] Extracting {zip_file_path}...")
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extracted_folder)
    except Exception as e:
        print(f"[{now()}] Error extracting zip file {zip_file_path}: {e}")
        return "failed"

    # 解压后，按照你原本的内部目录结构定位文本和图片
    # 假设压缩包解压后里面直接是 sparse 和 images 文件夹
    colmap_folder = f"{extracted_folder}/sparse/0/"
    image_folder = f"{extracted_folder}/images"

    # 如果解压出来发现套了一层叫 "colmap" 的壳，自动纠正路径
    if not os.path.exists(colmap_folder) and os.path.exists(f"{extracted_folder}/colmap/sparse/0/"):
        colmap_folder = f"{extracted_folder}/colmap/sparse/0/"
        image_folder = f"{extracted_folder}/colmap/images"

    # 沿用你原本聪明的 tmp 平铺障眼法，让图片和 txt 变成平级，RC 绝不弹窗
    tmp_folder = f"{folder_path}/tmp/"
    os.makedirs(tmp_folder, exist_ok=True)

    try:
        shutil.copytree(colmap_folder, tmp_folder, dirs_exist_ok=True)
        shutil.copytree(image_folder, tmp_folder, dirs_exist_ok=True)
    except Exception as e:
        print(f"[{now()}] Error structuring tmp folder: {e}")
        # 清理垃圾
        shutil.rmtree(tmp_folder, ignore_errors=True)
        shutil.rmtree(extracted_folder, ignore_errors=True)
        return "failed"

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

    try:
        proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        print(f"[{now()}] Error calling RealityCapture CLI:", e)
        # 即使失败也要清理，防止留下大文件垃圾
        shutil.rmtree(tmp_folder, ignore_errors=True)
        shutil.rmtree(extracted_folder, ignore_errors=True)
        return "failed"

    # 【过河拆桥】成功后把临时解压的文件夹和平铺的 tmp 文件夹全部删掉，省空间
    shutil.rmtree(tmp_folder, ignore_errors=True)
    shutil.rmtree(extracted_folder, ignore_errors=True)
    return "done"


if __name__ == "__main__":
    """
    1. 扫描有什么场景；
    2. 对每个场景，检测是否有rc工程文件，如果有，跳过；没有就执行；
    3. 【新修改】对每个场景，检测是否有 rc_colmap.zip 压缩包，如果有，就解压并转换成rc
    """
    if len(sys.argv) < 2:
        print("Error: Please provide the root folder path as an argument.")
        sys.exit(1)

    folder_path = sys.argv[1]
    folder_path = str(folder_path).replace("\\", "/")
    rc_exe = r"G:\RC\RealityScan_2.1\RealityScan.exe"

    if not os.path.isfile(rc_exe):
        print(f"Error: RealityCapture executable not found at: {rc_exe}")
        sys.exit(1)

    sub_folders = os.listdir(folder_path)
    sub_folders.sort()
    failed_list = []
    skip_list = []
    done_list = []

    for sub_folder in tqdm(sub_folders):
        current_scene_dir = f"{folder_path}/{sub_folder}"

        if not os.path.isdir(current_scene_dir):
            continue

        print(f"\n[Post Processing RC]: Processing folder: {sub_folder}")

        # 【核心修改】：检查的目标从文件夹变成了 rc_colmap.zip 压缩包文件
        if not os.path.isfile(f"{current_scene_dir}/rc_colmap.zip"):
            failed_list.append(sub_folder)
            print(f"{sub_folder} is failed, no rc_colmap.zip file found!", end='\n')
            continue

        if os.path.isfile(f"{current_scene_dir}/{sub_folder}.rsproj"):
            skip_list.append(sub_folder)
            print(f"{sub_folder}.rsproj exists, skipped!", end='\n')
            continue

        # 执行转换
        res = convert_colmap(rc_exe, current_scene_dir, headless=False)

        if res == "done":
            done_list.append(sub_folder)
            print(f"{sub_folder} is done!", end='\n')
        else:
            failed_list.append(sub_folder)
            print(f"{sub_folder} process failed during RC execution!", end='\n')

    print(f"\n[Post Processing RC]: "
          f"\n\tSkipped are {skip_list}, "
          f"\n\tFailed (require redo) are {failed_list}, "
          f"\n\tSuccessed are {done_list}, ")