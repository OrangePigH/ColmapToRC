#!/usr/bin/env python
# coding=utf-8
import os
import shutil
import sys
import zipfile
import threading
from tqdm import tqdm
import subprocess
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, scrolledtext


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def convert_colmap(rc_exe,
                   folder_path,
                   log_func,
                   headless=True,
                   extra_args=None):
    folder_path = str(folder_path).replace("\\", "/")
    scene_name = os.path.basename(folder_path)
    project_file = f"{folder_path}/{scene_name}.rsproj"

    zip_file_path = f"{folder_path}/rc_colmap.zip"
    # 修改目标：直接解压为名为 "colmap" 的文件夹并永久保留
    extracted_folder = f"{folder_path}/colmap"

    log_func(f"[{now()}] Extracting {zip_file_path} -> {extracted_folder}...")
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            # 如果压缩包内已经自带了一层 "colmap" 文件夹，解压到 folder_path 即可
            # 如果压缩包内直接是 sparse 和 images，解压到 extracted_folder
            # 这里先解压到一个临时区进行结构判定，确保最后文件夹名字一定是 "colmap"
            temp_extract = f"{folder_path}/_extract_tmp"
            zip_ref.extractall(temp_extract)

            if os.path.exists(f"{temp_extract}/colmap"):
                # 说明自带壳，把里面的东西移出来
                if os.path.exists(extracted_folder):
                    shutil.rmtree(extracted_folder, ignore_errors=True)
                shutil.move(f"{temp_extract}/colmap", extracted_folder)
                shutil.rmtree(temp_extract, ignore_errors=True)
            else:
                if os.path.exists(extracted_folder):
                    shutil.rmtree(extracted_folder, ignore_errors=True)
                shutil.move(temp_extract, extracted_folder)
    except Exception as e:
        log_func(f"[{now()}] Error extracting zip file {zip_file_path}: {e}")
        return "failed"

    # 正确对应解压后（已规范命名为 colmap）的内部路径
    colmap_folder = f"{extracted_folder}/sparse/0/"
    image_folder = f"{extracted_folder}/images"

    # 沿用你原本聪明的 tmp 平铺障眼法，让图片和 txt 变成平级，RC 绝不弹窗
    tmp_folder = f"{folder_path}/tmp/"
    os.makedirs(tmp_folder, exist_ok=True)

    try:
        shutil.copytree(colmap_folder, tmp_folder, dirs_exist_ok=True)
        shutil.copytree(image_folder, tmp_folder, dirs_exist_ok=True)
    except Exception as e:
        log_func(f"[{now()}] Error structuring tmp folder: {e}")
        shutil.rmtree(tmp_folder, ignore_errors=True)
        return "failed"

    if extra_args is None:
        extra_args = []
    args = [rc_exe]

    if headless:
        args.append("-headless")
    args.append(f"-loadColmap")
    args.append(f"{tmp_folder}/points3D.txt")
    args.append("-save")
    args.append(project_file)
    args.extend(extra_args)
    args.append("-quit")

    log_func(f"[{now()}] Running RealityCapture CLI for: {scene_name}...")
    try:
        proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    except subprocess.CalledProcessError as e:
        log_func(f"[{now()}] Error calling RealityCapture CLI: {e}")
        shutil.rmtree(tmp_folder, ignore_errors=True)
        return "failed"

    # 过河拆桥：只删除临时的平铺 tmp 文件夹，【保留】上面解压出来的 colmap 文件夹
    shutil.rmtree(tmp_folder, ignore_errors=True)
    return "done"


# =========================
# RC 批处理核心类
# =========================
class BatchProcessor:
    def __init__(self, rc_exe, root_folder, log_func):
        self.rc_exe = rc_exe
        self.root_folder = str(root_folder).replace("\\", "/")
        self.log = log_func

    def run_batch(self):
        try:
            sub_folders = os.listdir(self.root_folder)
        except Exception as e:
            self.log(f"[ERROR] Cannot read root folder: {e}")
            return

        sub_folders.sort()
        failed_list = []
        skip_list = []
        done_list = []

        # 针对 GUI 包装的循环
        for sub_folder in sub_folders:
            current_scene_dir = f"{self.root_folder}/{sub_folder}"

            if not os.path.isdir(current_scene_dir):
                continue

            self.log(f"\n[Post Processing RC]: Processing folder: {sub_folder}")

            # 优先检查是否存在解压后的文件夹（如果已经解压过）或者存在压缩包
            has_zip = os.path.isfile(f"{current_scene_dir}/rc_colmap.zip")
            has_dir = os.path.isdir(f"{current_scene_dir}/colmap")

            if not (has_zip or has_dir):
                failed_list.append(sub_folder)
                self.log(f"-> [FAILED] {sub_folder} has no rc_colmap.zip or colmap folder!")
                continue

            if os.path.isfile(f"{current_scene_dir}/{sub_folder}.rsproj"):
                skip_list.append(sub_folder)
                self.log(f"-> [SKIP] {sub_folder}.rsproj exists.")
                continue

            # 执行转换（内部会自动处理解压并保留文件夹）
            res = convert_colmap(self.rc_exe, current_scene_dir, self.log, headless=False)

            if res == "done":
                done_list.append(sub_folder)
                self.log(f"-> [SUCCESS] {sub_folder} processing completed.")
            else:
                failed_list.append(sub_folder)
                self.log(f"-> [FAILED] {sub_folder} broken during execution.")

        self.log("\n================ SUMMARY ================")
        self.log(f"Skipped   : {skip_list}")
        self.log(f"Failed    : {failed_list}")
        self.log(f"Successed : {done_list}\n")


# =========================
# Tkinter 可视化界面
# =========================
class App:
    def __init__(self, root):
        self.root = root
        root.title("COLMAP to RealityCapture Pipeline")
        root.geometry("900x650")

        self.rc_var = tk.StringVar(value=r"G:\RC\RealityScan_2.1\RealityScan.exe")
        self.folder_var = tk.StringVar()

        # RC路径选择
        tk.Label(root, text="RealityCapture / RealityScan.exe Path:", font=("Arial", 10, "bold")).pack(anchor="w",
                                                                                                       padx=10, pady=5)
        f1 = tk.Frame(root)
        f1.pack(fill="x", padx=10)
        tk.Entry(f1, textvariable=self.rc_var).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(f1, text="Browse...", command=self.select_rc).pack(side="right", padx=5)

        # 大文件夹路径选择
        tk.Label(root, text="Root Dataset Folder (包含子场景的大文件夹):", font=("Arial", 10, "bold")).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=5)
        f2 = tk.Frame(root)
        f2.pack(fill="x", padx=10)
        tk.Entry(f2, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(f2, text="Browse...", command=self.select_folder).pack(side="right", padx=5)

        # 开始按钮
        tk.Button(root, text="START BATCH PROCESSING", font=("Arial", 11, "bold"), bg="#107C41", fg="white",
                  command=self.start).pack(pady=15, ipadx=20, ipady=5)

        # 日志框
        tk.Label(root, text="Execution Logs:", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.log_box = scrolledtext.ScrolledText(root, bg="#1E1E1E", fg="#F1F1F1", insertbackground="white",
                                                 font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)

    def log(self, msg):
        # 确保在 GUI 线程中安全打印日志
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)

    def select_rc(self):
        path = filedialog.askopenfilename(filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")])
        if path:
            self.rc_var.set(path)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_var.set(path)

    def start(self):
        rc = self.rc_var.get()
        folder = self.folder_var.get()

        if not os.path.isfile(rc):
            self.log("[GUI ERROR] 无效的 RealityCapture 程序路径！")
            return

        if not os.path.isdir(folder):
            self.log("[GUI ERROR] 无效的大文件夹路径！")
            return

        self.log("[GUI INFO] 正在启动后台批处理线程...\n")

        # 使用多线程，防止批处理运行时卡死 Tkinter 窗口界面
        processor = BatchProcessor(rc, folder, self.log)
        thread = threading.Thread(target=processor.run_batch, daemon=True)
        thread.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()