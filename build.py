import subprocess
import colorama
import datetime
import _thread
import time
import sys
import os
import locale
import shutil
import argparse
import py7zr
import filehash

# Initialize colorama
colorama.init(autoreset=True)
Fore, Style, Back = (colorama.Fore, colorama.Style, colorama.Back)

class AtbBuild(object):
    def __init__(self, lang: str, verbose: int = 0, is_dev: bool = False, is_release: bool = False, batch: bool = False):
        self.is_running = True
        self.current_step = 0
        self.current_desc = ""
        self.success = True
        self.errs = 0
        self.warns = 0
        self.lang = lang
        
        # 0: Animation, 1: -v (Log), 2: -vv (Detailed)
        self.verbose = verbose
        self.is_dev = is_dev
        self.is_release = is_release

        self.batch = batch

        if self.is_release:
            self.build_type = "release"
        elif self.is_dev:
            self.build_type = "dev"
        else:
            self.build_type = "default"

        if lang == "zh_CN":
            self.steps = ["正在确定需要还原的项目", "正在还原所需项目", "开始生成代码"]
            self.error_msg = "生成失败。"
            self.interrupt_msg = "用户取消了操作"
            self.start_msg = "生成开始于"
            self.success_msg = "生成已成功完成。"
            self.build_started_msg = "生成已开始"
        else:
            self.steps = ["Determining projects", "Restoring packages", "Building project"]
            self.error_msg = "Build FAILED."
            self.interrupt_msg = "Operation cancelled by user"
            self.start_msg = "Build started at"
            self.success_msg = "Build succeeded."
            self.build_started_msg = "Build started"

    def update_step_desc(self, desc: str):
        self.current_desc = desc

    def _log_verbose(self, message: str, level: int = 0):
        if self.verbose == 0:
            return
        
        if self.verbose >= 1 or (self.verbose == 2 and level <= 1):
            print(f"{message}{Style.RESET_ALL}")
            sys.stdout.flush()

    def _render_frame(self, idx):
        if self.verbose > 0:
            return

        chars = ['\\', '|', '/', '-']
        progress = [".", "..", "..."]
        # Move cursor up
        sys.stdout.write(f"\033[{len(self.steps)}F")
        
        for i in range(len(self.steps)):
            if i < self.current_step:
                # Completed
                print(f"{Fore.GREEN}  ✓ {Style.RESET_ALL}{self.steps[i]}\033[K")
            elif i == self.current_step:
                if not self.success:
                    # Failed
                    print(f"{Fore.RED}  ! {Style.RESET_ALL}{self.steps[i]}\033[K")
                else:
                    # Spinning
                    char = chars[idx % len(chars)]
                    dots = progress[idx % len(progress)]
                    desc = f": {self.current_desc}" if self.current_desc else ""
                    print(f"{Fore.CYAN}  {char} {Style.RESET_ALL}{self.steps[i]}{desc or dots}\033[K")
            else:
                # Pending
                print(f"{Fore.LIGHTBLACK_EX}    {self.steps[i]}{Style.RESET_ALL}\033[K")
                
        sys.stdout.flush()

    def _ui_thread(self):
        idx = 0
        if self.verbose == 0:
            # Hide cursor
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            print("\n" * len(self.steps), end="")
        
        while self.is_running:
            self._render_frame(idx)
            idx += 1
            time.sleep(0.25)
        
        if self.verbose == 0:
            self._render_frame(idx)
            # Show cursor
            sys.stdout.write('\033[?25h')
            sys.stdout.flush()
            print("") 

    def run_command(self, cmd_list):
        final_cmd_list = list(cmd_list)
        
        if self.verbose == 2 and len(final_cmd_list) > 0:
            if final_cmd_list[0] == "cargo":
                if "-vv" not in final_cmd_list and ("fetch" in final_cmd_list or "build" in final_cmd_list):
                    final_cmd_list.append("-vv")

        cmd_str = " ".join(final_cmd_list)
        if self.verbose >= 1 and not self.batch:    
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} - {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{cmd_str}{Style.RESET_ALL}")
            process = subprocess.Popen(
                final_cmd_list,
                shell=False,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            process.wait()

        else:
            process = subprocess.Popen(
                final_cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

        while True:
            if self.verbose >= 1 and not self.batch:
                line = None
            else:
                line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                clean_line = line.strip()
                if self.verbose >= 1:
                    if "error" in clean_line.lower():
                        self._log_verbose(f"{Fore.RED}{clean_line}{Style.RESET_ALL}")
                    elif "warn" in clean_line.lower():
                        self._log_verbose(f"{Fore.YELLOW}{clean_line}{Style.RESET_ALL}")
                    else:
                        self._log_verbose(clean_line)
                else:
                    if clean_line:
                        # Limit description length
                        short_desc = (clean_line[:37] + '..') if len(clean_line) > 40 else clean_line
                        self.update_step_desc(short_desc)
                        time.sleep(0.05) 

        if process.returncode != 0:
            self.errs += 1
            self.success = False
        return process.returncode

    def run_build_logic(self):
        if self.verbose == 0:
            time.sleep(2)

        # Step 0: Check
        if self.verbose >= 1:
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} * {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{self.steps[0]}{Style.RESET_ALL}")
            
        if not os.path.exists("Cargo.toml") or not os.path.exists("requirements.txt"):
            err_msg = "Missing Cargo.toml or requirements.txt"
            if self.verbose >= 1:
                self._log_verbose(f"{Fore.RED}ERROR: {err_msg}{Style.RESET_ALL}")
            else:
                self.update_step_desc(err_msg)
            self.errs += 1
            self.success = False
            return 

        self.current_desc = None
        if self.verbose == 0:
            time.sleep(0.2)
        self.current_step += 1
        
        os.makedirs("./build", exist_ok=True)
        for directory in ["main", "py", "rust", "FileDialog"]:
            os.makedirs(f"./build/{directory}", exist_ok=True)
        
        # Step 1: Restore
        if self.verbose >= 1:
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} * {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{self.steps[1]}{Style.RESET_ALL}")

        self.run_command(["cargo", "fetch"])
        self.run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        
        if self.verbose == 0:
            time.sleep(0.2)
        self.current_step += 1
        
        # Step 2: Build
        if self.verbose >= 1:
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} * {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{self.steps[2]}{Style.RESET_ALL}")

        self.current_desc = self.build_started_msg
        
        # MSVC Build
        self.run_command(["cl.exe", "/MT", "/EHsc", "/Fobuild/launch.obj", "src\\launch.cpp", 
                          "/source-charset:utf-8", "/execution-charset:gbk", 
                          "/Fe:build\\main\\launcher.exe", "/O2", 
                          "/link", "/MACHINE:x64", "advapi32.lib", "user32.lib", "shell32.lib"])
        
        # Nuitka flags
        self.py_fresh = []
        try:
            md5: function = filehash.FileHash("md5").hash_file
            main_last = md5("./build/py/main.py")
            menu_last = md5("./build/py/menu.py")
            repair_last = md5("./build/py/repair.py")
            run_cmd_last = md5("./build/py/run_cmd.py")

            main_now = md5("src/start.py")
            menu_now = md5("src/menu.py")
            repair_now = md5("src/repair.py")
            run_cmd_now = md5("src/run_cmd.py")

            if main_last == main_now: self.py_fresh.append("src/start.py")
            if menu_last == menu_now: self.py_fresh.append("src/menu.py")
            if repair_last == repair_now: self.py_fresh.append("src/repair.py")
            if run_cmd_last == run_cmd_now: self.py_fresh.append("src/run_cmd.py")
        except Exception:
            pass



        if self.is_dev:
            nuitka_flags = ["--debug"]
        elif self.is_release:
            nuitka_flags = ["--lto=yes"]
        else:
            nuitka_flags = []

        files = [("src/start.py", "main.exe"), ("src/menu.py", "menu.exe"), 
                 ("src/repair.py", "repair.exe"), ("src/run_cmd.py", "run_cmd.exe")]
        
        for src, out in files:
            if src in self.py_fresh:
                continue
            cmd = [sys.executable, "-m", "nuitka", "--onefile", src, "--output-dir=./build/py/", f"--output-filename={out}", "--msvc=latest"] + nuitka_flags
            if self.run_command(cmd):
                shutil.copy2(src, f"./build/py/{out[:-4]}.py")

        # Cargo Build
        cargo_cmd = ["cargo", "build"]
        if self.is_release:
            cargo_cmd.append("--release")
        self.run_command(cargo_cmd)

        # Dotnet Build
        dotnet_cmd = ["dotnet.exe", "build", "./src/FileDialog/FileDialog.csproj", "-c", "Debug" if not self.is_release else "Release",
                        "-o", "./build/FileDialog/", "-p:BaseIntermediateOutputPath=../../build/FileDialog/obj/"]
        if self.verbose >= 2: dotnet_cmd += ["-v", "n"]
        self.run_command(dotnet_cmd)

        if self.errs > 0:
            self.success = False
            return
        
        # Finalization
        try:
            os.makedirs("./build/main", exist_ok=True)
            for exe in ["main.exe", "menu.exe", "repair.exe", "run_cmd.exe"]:
                shutil.copy2(f"./build/py/{exe}", f"./build/main/{exe}")
            for exe in ["lolcat.exe", "jsonutil.exe"]:
                shutil.copy2(f"./build/rust/{"debug" if not self.is_release else "release"}/{exe}", f"./build/main/{exe}")
            shutil.copy2("./build/FileDialog/FileDialog.exe", "./build/main/FileDialog.exe")

            with py7zr.SevenZipFile('bin.7z', mode='r') as z:
                z.extractall(path='./build/main')
        except Exception as e:
            self.errs += 1
            self.success = False
            return

        if self.verbose == 0:
            time.sleep(0.2)
        self.current_step += 1

    def start(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        if self.verbose >= 1:
            print(f"{Fore.YELLOW}{self.start_msg} {now}{Style.RESET_ALL}\n")
        else:
            print(f"{Fore.YELLOW}{self.start_msg} {now}...{Style.RESET_ALL}\n")

        _thread.start_new_thread(self._ui_thread, ())
        try:
            self.run_build_logic()
        except KeyboardInterrupt:
            self.errs = 1
            self.interrupt = True
            self.success = False
        
        self.is_running = False
        time.sleep(0.3)

        if self.verbose == 0:
            sys.stdout.write('\n')

        if self.lang != "zh_CN":
            print(f"  {self.warns} warning{'s' if self.warns != 1 else ''}")
            print(f"  {self.errs} error{'s' if self.errs != 1 else ''}")
        else:
            print(f"  {self.warns} 个警告")
            print(f"  {self.errs} 个错误")
        
        if self.success and self.errs == 0:
            print(f"\n{Fore.YELLOW}{self.success_msg}{Style.RESET_ALL}")
        else:
            if hasattr(self, "interrupt"):
                msg = f"{self.error_msg} ({self.interrupt_msg})"
            else:
                msg = self.error_msg
            print(f"\n{Fore.RED}{msg}{Style.RESET_ALL}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATB Build System")
    parser.add_argument('-v', '--verbose', action='count', default=0)
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--release', action='store_true')
    parser.add_argument("--batch", action="store_true")
    args = parser.parse_args()

    if args.dev and args.release:
        print("Error: Cannot specify both --dev and --release.", file=sys.stderr)
        sys.exit(1)

    if args.verbose == 0 and args.batch:
        print("Error: Cannot enable batch mode when verbose is disabled.")

    lang = locale.getdefaultlocale()[0] or "en_US"
    build = AtbBuild(lang=lang, verbose=args.verbose, is_dev=args.dev, is_release=args.release, batch=args.batch)
    build.start()