#!/usr/bin/env python
# coding=utf-8
import os
import shutil
import sys
import zipfile
import threading
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
    extracted_folder = f"{folder_path}/rc_colmap"

    log_func(f"[{now()}] Extracting {zip_file_path} -> {extracted_folder}...")
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            temp_extract = f"{folder_path}/_extract_tmp"
            zip_ref.extractall(temp_extract)

            if os.path.exists(f"{temp_extract}/rc_colmap"):
                if os.path.exists(extracted_folder):
                    shutil.rmtree(extracted_folder, ignore_errors=True)
                shutil.move(f"{temp_extract}/rc_colmap", extracted_folder)
                shutil.rmtree(temp_extract, ignore_errors=True)
            elif os.path.exists(f"{temp_extract}/colmap"):
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

    # 定义路径
    colmap_txt_dir = f"{extracted_folder}/sparse/0"
    src_images_folder = f"{extracted_folder}/images"

    if not os.path.isdir(src_images_folder):
        log_func(f"[ERROR] Source images folder not found at: {src_images_folder}")
        return "failed"

    # 扫描真实的图片文件列表
    image_files = [f for f in os.listdir(src_images_folder) if os.path.isfile(os.path.join(src_images_folder, f))]

    # 【修正核心逻辑：把文件挪过去平铺】
    log_func(f"[{now()}] Flattening image files into sparse/0/ directory (0s I/O)...")
    try:
        for img in image_files:
            src_img_path = os.path.join(src_images_folder, img)
            dst_img_path = os.path.join(colmap_txt_dir, img)
            # 如果目标处原本就有同名文件，先删掉防止报错
            if os.path.exists(dst_img_path):
                os.remove(dst_img_path)
            shutil.move(src_img_path, colmap_txt_dir)
    except Exception as e:
        log_func(f"[ERROR] Failed to shift image files: {e}")
        return "failed"

    if extra_args is None:
        extra_args = []
    args = [rc_exe]

    if headless:
        args.append("-headless")
    args.append(f"-loadColmap")
    args.append(f"{colmap_txt_dir}/points3D.txt")
    args.append("-save")
    args.append(project_file)
    args.extend(extra_args)
    args.append("-quit")

    log_func(f"[{now()}] Running RealityCapture CLI for: {scene_name}...")

    success = False
    try:
        proc = subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        success = True
    except subprocess.CalledProcessError as e:
        log_func(f"[{now()}] Error calling RealityCapture CLI: {e}")
        success = False

    # 【还原：把照片文件再统一挪回原本的 images 文件夹】
    log_func(f"[{now()}] Restoring original rc_colmap folder structure...")
    try:
        # 确保原本的外部 images 文件夹存在
        os.makedirs(src_images_folder, exist_ok=True)
        for img in image_files:
            temp_img_path = os.path.join(colmap_txt_dir, img)
            if os.path.exists(temp_img_path):
                shutil.move(temp_img_path, src_images_folder)
    except Exception as e:
        log_func(f"[WARNING] Failed to restore image files location: {e}")

    return "done" if success else "failed"


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

        for sub_folder in sub_folders:
            current_scene_dir = f"{self.root_folder}/{sub_folder}"

            if not os.path.isdir(current_scene_dir):
                continue

            self.log(f"\n[Post Processing RC]: Processing folder: {sub_folder}")

            has_zip = os.path.isfile(f"{current_scene_dir}/rc_colmap.zip")
            has_dir = os.path.isdir(f"{current_scene_dir}/rc_colmap")

            if not (has_zip or has_dir):
                failed_list.append(sub_folder)
                self.log(f"-> [FAILED] {sub_folder} has no rc_colmap.zip or rc_colmap folder!")
                continue

            if os.path.isfile(f"{current_scene_dir}/{sub_folder}.rsproj"):
                skip_list.append(sub_folder)
                self.log(f"-> [SKIP] {sub_folder}.rsproj exists.")
                continue

            res = convert_colmap(self.rc_exe, current_scene_dir, self.log, headless=False)

            if res == "done":
                done_list.append(sub_folder)
                self.log(f"-> [SUCCESS] {sub_folder} completed smoothly.")
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
        root.title("COLMAP to RealityCapture Pipeline (Zero I/O Version)")
        root.geometry("900x650")

        self.rc_var = tk.StringVar(value=r"G:\RC\RealityScan_2.1\RealityScan.exe")
        self.folder_var = tk.StringVar()

        tk.Label(root, text="RealityCapture / RealityScan.exe Path:", font=("Arial", 10, "bold")).pack(anchor="w",
                                                                                                       padx=10, pady=5)
        f1 = tk.Frame(root)
        f1.pack(fill="x", padx=10)
        tk.Entry(f1, textvariable=self.rc_var).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(f1, text="Browse...", command=self.select_rc).pack(side="right", padx=5)

        tk.Label(root, text="Root Dataset Folder (包含子场景的大文件夹):", font=("Arial", 10, "bold")).pack(anchor="w",
                                                                                                            padx=10,
                                                                                                            pady=5)
        f2 = tk.Frame(root)
        f2.pack(fill="x", padx=10)
        tk.Entry(f2, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(f2, text="Browse...", command=self.select_folder).pack(side="right", padx=5)

        tk.Button(root, text="START BATCH PROCESSING", font=("Arial", 11, "bold"), bg="#107C41", fg="white",
                  command=self.start).pack(pady=15, ipadx=20, ipady=5)

        tk.Label(root, text="Execution Logs:", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.log_box = scrolledtext.ScrolledText(root, bg="#1E1E1E", fg="#F1F1F1", insertbackground="white",
                                                 font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)

    def log(self, msg):
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

        self.log("[GUI INFO] 正在启动后台无损批处理线程...\n")

        processor = BatchProcessor(rc, folder, self.log)
        thread = threading.Thread(target=processor.run_batch, daemon=True)
        thread.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()