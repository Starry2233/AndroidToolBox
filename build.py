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

# 初始化 colorama
colorama.init(autoreset=True)
Fore, Style, Back = (colorama.Fore, colorama.Style, colorama.Back)

class AtbBuild(object):
    def __init__(self, lang: str, verbose: int = 0, is_dev: bool = False, is_release: bool = False):
        self.is_running = True
        self.current_step = 0
        self.current_desc = ""
        self.success = True
        self.errs = 0
        self.warns = 0
        self.lang = lang
        
        # 模式标志
        self.verbose = verbose  # 0: 动画，1: -v (文本日志), 2: -vv (Cargo 详细日志)
        self.is_dev = is_dev
        self.is_release = is_release

        # 确定构建类型标签 (用于显示或逻辑)
        if self.is_release:
            self.build_type = "release"
        elif self.is_dev:
            self.build_type = "dev"
        else:
            self.build_type = "default"

        if lang == "zh_CN":
            self.steps = ["正在确定需要还原的项目", "正在还原所需项目", "开始生成代码"]
            self.error_msg = "生成失败。"
            self.start_msg = "生成开始于"
            self.success_msg = "生成已成功完成。"
            self.build_started_msg = "生成已开始"
        else:
            self.steps = ["Determining projects", "Restoring packages", "Building project"]
            self.error_msg = "Build FAILED."
            self.start_msg = "Build started at"
            self.success_msg = "Build succeeded."
            self.build_started_msg = "Build started"

    def update_step_desc(self, desc: str):
        self.current_desc = desc

    def _log_verbose(self, message: str, level: int = 0):
        """
        处理详细模式下的日志输出。
        level 0: 普通输出 (-v)
        level 1: 详细输出 (-vv 特有，或者所有在 -vv 下才显示的)
        """
        if self.verbose == 0:
            return
        
        # 在 -v 模式下，只显示普通信息；在 -vv 模式下显示所有信息
        if self.verbose >= 1 or (self.verbose == 2 and level <= 1):
            print(f"{message}{Style.RESET_ALL}")
            sys.stdout.flush()

    def _render_frame(self, idx):
        # 如果开启了详细模式 (-v 或 -vv)，不渲染动画帧，直接返回
        # 具体的步骤日志会在 run_command 或状态变更时通过 _log_verbose 打印
        if self.verbose > 0:
            return

        chars = ['\\', '|', '/', '-']
        # 移动光标到步骤列表的起始位置
        sys.stdout.write(f"\033[{len(self.steps)}F")
        
        for i in range(len(self.steps)):
            if i < self.current_step:
                if not self.success:
                   print(f"{Fore.LIGHTRED_EX}  ! {self.steps[i]}{Style.RESET_ALL}\033[K") 
                   # 注意：原逻辑这里有点奇怪，打印下一步然后返回，这里保持原逻辑结构
                   if i + 1 < len(self.steps):
                       print(f"{Fore.LIGHTBLACK_EX}    {self.steps[i+1]}{Style.RESET_ALL}\033[K\n")
                   sys.stdout.flush()
                   return
                else:
                    print(f"{Fore.GREEN}  ✓ {self.steps[i]}{Style.RESET_ALL}\033[K")
            elif i == self.current_step:
                char = chars[idx % len(chars)]
                desc_str = f": {self.current_desc}" if self.current_desc else ""
                print(f"{Fore.CYAN}  {char} {self.steps[i]}{desc_str}...{Style.RESET_ALL}\033[K")
            else:
                print(f"{Fore.LIGHTBLACK_EX}    {self.steps[i]}{Style.RESET_ALL}\033[K")
        sys.stdout.flush()

    def _ui_thread(self):
        idx = 0
        # 只有在非详细模式下才预留空行用于动画
        if self.verbose == 0:
            print("\n" * len(self.steps), end="")
        
        while self.is_running:
            self._render_frame(idx)
            idx += 1
            time.sleep(0.25)
        
        # 最后一次渲染以确保状态正确
        if self.verbose == 0:
            self._render_frame(idx)
            print("") # 换行，避免覆盖最后的输出

    def run_command(self, cmd_list):
        """
        执行命令。
        cmd_list: 列表形式的命令，例如 ['cargo', 'build']
        """
        # 处理 -vv 模式下的 Cargo 特殊参数
        final_cmd_list = list(cmd_list)
        is_cargo_cmd = False
        
        if self.verbose == 2 and len(final_cmd_list) > 0:
            if final_cmd_list[0] == "cargo":
                is_cargo_cmd = True
                # 如果是 cargo 命令且不是 help/version 等，插入 -vv
                # 简单的启发式判断：如果后面没有 -vv 且不是元命令
                if "-vv" not in final_cmd_list and "fetch" in final_cmd_list or "build" in final_cmd_list:
                    # 找到子命令位置插入 -vv，通常 cargo <subcommand> -vv
                    # 简单处理：直接在末尾添加，cargo 通常能识别
                    # 更严谨的做法是插在 subcommand 之后，但为了通用性，这里假设放在末尾或特定位置
                    # cargo build -vv 是合法的
                    final_cmd_list.append("-vv")
                    self._log_verbose(f"[VERBOSE] Enabling cargo -vv for: {' '.join(cmd_list)}", level=1)

        # 构造用于显示的命令字符串
        cmd_str = " ".join(final_cmd_list)
        
        # 在 -v 模式下打印正在执行的命令
        if self.verbose >= 1:
            step_name = self.steps[self.current_step] if self.current_step < len(self.steps) else "Unknown Step"
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} - {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{cmd_str}{Style.RESET_ALL}")

        process = subprocess.Popen(
            final_cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False, # 使用列表时建议关闭 shell，更安全且避免转义问题
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                clean_line = line.strip()
                
                # 详细模式：直接输出每一行
                if self.verbose >= 1:
                    if clean_line:
                        # 简单区分一下错误流（虽然合并到了 stdout，但可以根据内容高亮）
                        if "error" in clean_line.lower():
                            self._log_verbose(f"{Fore.RED}{clean_line}{Style.RESET_ALL}")
                        elif "warning" in clean_line.lower():
                            self._log_verbose(f"{Fore.YELLOW}{clean_line}{Style.RESET_ALL}")
                        else:
                            self._log_verbose(clean_line)
                else:
                    # 动画模式：更新描述
                    if clean_line:
                        short_desc = (clean_line[:37] + '..') if len(clean_line) > 40 else clean_line
                        self.update_step_desc(short_desc)
                        # 稍微休眠让动画流畅，但在详细模式下不需要这个延迟阻塞输出
                        time.sleep(0.05) 

        if process.returncode != 0:
            self.errs += 1
            if self.verbose >= 1:
                self._log_verbose(f"{Fore.RED}Command failed with exit code {process.returncode}{Style.RESET_ALL}")
        
        return process.returncode

    def run_build_logic(self):
        # 初始延迟仅在动画模式下有意义，详细模式下立即开始
        if self.verbose == 0:
            time.sleep(2)

        # 步骤 0: 检查环境
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
            return # 终止构建

        self.current_desc = None
        if self.verbose == 0: time.sleep(0.2)
        
        self.current_step += 1
        
        # 步骤 1: 还原包
        if self.verbose >= 1:
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} * {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{self.steps[1]}{Style.RESET_ALL}")

        self.run_command(["cargo", "fetch"])
        
        # 注意：原代码中 pip install 是在 cargo fetch 之后立即调用，没有检查返回值是否致命
        # 这里保持原逻辑顺序
        self.run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        
        if self.verbose == 0: time.sleep(0.2)
        self.current_step += 1
        
        # 步骤 2: 构建
        if self.verbose >= 1:
            self._log_verbose(f"\n{Fore.WHITE}{Back.LIGHTBLUE_EX} * {Style.RESET_ALL}{Fore.BLACK}{Back.WHITE}{self.steps[2]}{Style.RESET_ALL}")
            self._log_verbose(f"Mode: {self.build_type.upper()}")

        self.current_desc = self.build_started_msg
        if self.verbose == 0: time.sleep(0.5)

        # C++ 编译
        self.run_command(["cl.exe", "/MT", "/EHsc", "/Fobuild/launch.obj", "src\\launch.cpp", 
                          "/source-charset:utf-8", "/execution-charset:gbk", 
                          "/Fe:build\\main\\launcher.exe", "/O2", 
                          "/link", "/MACHINE:x64", "advapi32.lib", "user32.lib", "shell32.lib"])
        
        # Python 编译 (Nuitka)
        nuitka_base = [sys.executable, "-m", "nuitka", "--onefile"]
        # 根据 --dev 或 --release 添加 nuitka 优化选项 (示例)
        # --dev 通常对应 --debug 或不优化，--release 对应 --optimize=2
        if self.is_dev:
            nuitka_flags = ["--debug"] # 示例标志
        elif self.is_release:
            nuitka_flags = ["--lto=yes"] # 示例标志
        else:
            nuitka_flags = []

        files_to_compile = [
            ("src/start.py", "main.exe"),
            ("src/menu.py", "menu.exe"),
            ("src/repair.py", "repair.exe"),
            ("src/run_cmd.py", "run_cmd.exe")
        ]

        for src, out_name in files_to_compile:
            cmd = nuitka_base + [src, "--output-dir=./build/py/"]
            if out_name:
                cmd.extend([f"--output-filename={out_name}"])
            cmd.extend(["--msvc=latest"] + nuitka_flags)
            self.run_command(cmd)

        # Rust 编译
        cargo_cmd = ["cargo", "build"]
        if self.is_release:
            cargo_cmd.append("--release")
        elif self.is_dev:
            # dev 是默认行为，但可以显式添加 --profile dev 如果需要，或者不加
            pass
        
        self.run_command(cargo_cmd)

        if self.errs > 0:
            self.success = False
            return
        
        # 文件复制
        try:
            os.makedirs("./build/main/bin", exist_ok=True)
            shutil.copy2("./build/py/main.exe", "./build/main/bin/main.exe")
            shutil.copy2("./build/py/menu.exe", "./build/main/bin/menu.exe")
            shutil.copy2("./build/py/repair.exe", "./build/main/bin/repair.exe")
            shutil.copy2("./build/py/run_cmd.exe", "./build/main/bin/run_cmd.exe")
            src = "./src/bats/"
            dst = "./build/main/bin"
            for root, _, files in os.walk(src):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel = os.path.relpath(src_path, src)
                    dst_path = os.path.join(dst, rel)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy2(src_path, dst_path)
            with py7zr.SevenZipFile('bin.7z', mode='r') as z:
                z.extractall(path='./build/main/bin')
            if self.verbose >= 1:
                self._log_verbose("Files copied successfully.")
            
        except Exception as e:
            if self.verbose >= 1:
                self._log_verbose(f"{Fore.RED}Copy failed: {str(e)}{Style.RESET_ALL}")
            self.errs += 1
            self.success = False
            return

        if self.verbose == 0:
            time.sleep(0.2)
        self.current_step += 1
        if self.verbose == 0:
            time.sleep(0.1)

    def start(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 在详细模式下打印头部信息
        if self.verbose >= 1:
            print(f"{Fore.YELLOW}{self.start_msg} {now}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Configuration: Lang={self.lang}, Verbose={self.verbose}, Dev={self.is_dev}, Release={self.is_release}{Style.RESET_ALL}\n")
        else:
            print(f"{Fore.YELLOW}{self.start_msg} {now}...{Style.RESET_ALL}\n")

        _thread.start_new_thread(self._ui_thread, ())
        self.run_build_logic()
        
        # 停止 UI 线程
        self.is_running = False
        time.sleep(0.3) # 等待 UI 线程最后一次刷新

        if self.verbose == 0:
            print("\n") # 确保在动画结束后换行

        print(f"  {str(self.warns)} 个警告" if self.lang == "zh_CN" else f"  {str(self.warns)} warnings")
        print(f"  {str(self.errs)} 个错误" if self.lang == "zh_CN" else f"  {str(self.errs)} errors")
        
        if self.success:
            print(f"\n{Fore.YELLOW}{self.success_msg}{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}{self.error_msg}{Style.RESET_ALL}")
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATB Build System")
    
    # 详细程度参数
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='-v: Show step names and logs (no progress bar). -vv: Enable cargo -vv and detailed logs.')
    
    # 构建模式参数 (按要求不注释，并实际传入逻辑)
    parser.add_argument('--dev', action='store_true',
                        help='Build in development mode (debug symbols, no optimization).')
    parser.add_argument('--release', action='store_true',
                        help='Build in release mode (optimized).')

    args = parser.parse_args()

    # 互斥检查 (可选，但推荐)
    if args.dev and args.release:
        print("Error: Cannot specify both --dev and --release.")
        sys.exit(1)

    # 获取语言环境
    lang = locale.getdefaultlocale()[0]
    if not lang:
        lang = "en_US"

    # 实例化并运行
    # verbose: 0=normal, 1=-v, 2=-vv
    build = AtbBuild(
        lang=lang, 
        verbose=args.verbose, 
        is_dev=args.dev, 
        is_release=args.release
    )
    build.start()