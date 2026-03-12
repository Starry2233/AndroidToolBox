import importlib.util, sys, os
spec = importlib.util.spec_from_file_location('mm', 'src/menu.py')
mm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mm)
print('_fetch_cloud_flag ->', mm._fetch_cloud_flag('https://atb.xgj.qzz.io/check.info'))
print('_is_main_present ->', mm._is_main_present())
print('_is_main_running ->', mm._is_main_running())
print('_increment_menufailed_count ->', mm._increment_menufailed_count())
print('menufailed file location ->', os.path.join(__import__('tempfile').gettempdir(), 'menufailed.txt'))
