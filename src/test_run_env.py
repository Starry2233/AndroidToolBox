from start import run

# 第一次设置变量
run("set qqft=1")
# 检查变量是否继承
result1 = run("echo %qqft%", capture_output=True)
print("第一次输出:", result1.stdout.strip())

# 修改变量
run("set qqft=2")
result2 = run("echo %qqft%", capture_output=True)
print("第二次输出:", result2.stdout.strip())

# 清理变量
run("set qqft=")
result3 = run("echo %qqft%", capture_output=True)
print("清理后输出:", result3.stdout.strip())
