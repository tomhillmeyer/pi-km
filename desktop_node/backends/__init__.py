import platform


def create_backend():
    sys_name = platform.system()
    if sys_name == "Darwin":
        from . import macos as backend_mod
        backend_mod.init()
        return backend_mod
    elif sys_name == "Windows":
        from . import windows as backend_mod
        backend_mod.init()
        return backend_mod
    else:
        from . import linux as backend_mod
        backend_mod.init()
        return backend_mod
