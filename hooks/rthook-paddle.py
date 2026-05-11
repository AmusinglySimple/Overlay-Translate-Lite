"""
Runtime hook for PaddlePaddle and PaddleOCR in PyInstaller frozen apps.

PROBLEM: PaddlePaddle's libpaddle.pyd and PyTorch both use pybind11 and register
C++ types with IDENTICAL names (_gpuDeviceProperties, ProgramDescTracer, etc.).
On Windows, MSVC's RTTI uses name-based comparison, so pybind11 considers them
the same type. Whoever loads second gets "type already registered!" errors.

SOLUTION:
1. Let torch load normally (stanza requires it).
2. Pre-populate sys.modules with a LAZY PROXY for paddle.base.libpaddle.
3. When paddle finally needs to load (lazy proxy triggers), TEMPORARILY
   delete the pybind11 internals capsule from the interpreter state dict.
   This makes pybind11 think it's a fresh interpreter, so paddle's PyInit
   can register its types without conflicts.
4. Pre-set LoDTensor = Tensor alias on the module immediately after loading.
   This prevents failures from circular imports in paddle's initialization:
   paddle.base.core → paddle.base.dataset → paddle.utils → paddle.utils.dlpack
   → from ..base.core import LoDTensor (needs LoDTensor before core.py finishes)
5. The conflicting types (_gpuDeviceProperties, ProgramDescTracer) are
   GPU/JIT-related and not used during CPU inference, so this is safe.
"""
import sys
import os
import types

_RTHOOK_DEBUG = os.environ.get('RTHOOK_DEBUG', '0') == '1'

def _rthook_log(msg):
    if _RTHOOK_DEBUG:
        import io
        try:
            sys.stderr.write(f'[rthook-paddle] {msg}\n')
            sys.stderr.flush()
        except Exception:
            pass

if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS

    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    # Fix PaddleOCR implicit absolute imports (e.g. "from tools.infer import predict_system")
    # paddleocr/paddleocr.py uses _import_file() to dynamically load "tools", "ppocr",
    # "ppstructure" as top-level packages from files inside the paddleocr/ data directory.
    # PyInstaller's FrozenImporter never analyzed these as dependencies, so they're not in
    # the PYZ archive. The files DO exist in _internal/paddleocr/ as collected data.
    # Fix: Install a meta-path finder that resolves these names from the filesystem.
    import importlib
    import importlib.util as _ilu
    import importlib.abc
    import importlib.machinery

    _paddleocr_path = os.path.join(bundle_dir, 'paddleocr')

    class _PaddleOCRSubpackageFinder(importlib.abc.MetaPathFinder):
        """Resolve tools.*, ppocr.*, ppstructure.* from paddleocr data dir."""
        _ROOTS = ('tools', 'ppocr', 'ppstructure')

        def find_spec(self, fullname, path=None, target=None):
            parts = fullname.split('.')
            if parts[0] not in self._ROOTS:
                return None
            if not os.path.isdir(_paddleocr_path):
                return None

            # Build filesystem path
            rel = os.path.join(*parts)
            pkg_dir = os.path.join(_paddleocr_path, rel)
            # Check if it's a package (directory with or without __init__.py)
            if os.path.isdir(pkg_dir):
                init_file = os.path.join(pkg_dir, '__init__.py')
                if os.path.isfile(init_file):
                    return _ilu.spec_from_file_location(
                        fullname, init_file,
                        submodule_search_locations=[pkg_dir])
                else:
                    # Namespace-like package (no __init__.py, e.g. tools/infer/)
                    spec = importlib.machinery.ModuleSpec(
                        fullname, None, is_package=True)
                    spec.submodule_search_locations = [pkg_dir]
                    return spec
            # Check if it's a module (.py file)
            mod_file = os.path.join(_paddleocr_path, rel + '.py')
            if os.path.isfile(mod_file):
                return _ilu.spec_from_file_location(fullname, mod_file)
            return None

    sys.meta_path.insert(0, _PaddleOCRSubpackageFinder())

    if os.path.exists(_paddleocr_path) and _paddleocr_path not in sys.path:
        sys.path.insert(0, _paddleocr_path)

    _paddle_path = os.path.join(bundle_dir, 'paddle')

    if os.path.exists(_paddle_path):
        os.environ['PADDLE_BINARY_DIR'] = bundle_dir

        # ============================================================
        # Lazy proxy for paddle.base.libpaddle
        # ============================================================
        _libpaddle_pyd_path = os.path.join(_paddle_path, 'base', 'libpaddle.pyd')
        _paddle_libs_dir = os.path.join(_paddle_path, 'libs')
        _paddle_base_dir = os.path.join(_paddle_path, 'base')

        if os.path.exists(_libpaddle_pyd_path):
            _proxy = types.ModuleType('paddle.base.libpaddle')
            _proxy.__file__ = _libpaddle_pyd_path
            _proxy.__loader__ = None
            _proxy.__package__ = 'paddle.base'
            _proxy.__spec__ = None
            _proxy._real_module = None

            def _lazy_load_libpaddle(name):
                """Called on first attribute access on the proxy module.
                Loads the real libpaddle.pyd and copies ALL its attributes
                INTO the proxy. The proxy stays in sys.modules so all
                references (local variables, import *, setattr) work on
                the same object."""
                _rthook_log(f'_lazy_load_libpaddle called for: {name}')

                # Check if already loaded (re-entrant safety)
                if _proxy._real_module is not None:
                    val = getattr(_proxy._real_module, name, None)
                    if val is None:
                        val = _proxy.__dict__.get(name)
                    _rthook_log(f'  Already loaded, returning {name}={val is not None}')
                    return val

                # Add DLL directories for paddle's native dependencies
                dll_handles = []
                if sys.version_info >= (3, 8):
                    for d in [_paddle_libs_dir, _paddle_base_dir]:
                        if os.path.isdir(d):
                            try:
                                dll_handles.append(os.add_dll_directory(d))
                            except OSError:
                                pass

                # ---- CRITICAL: Clear pybind11 internals before loading ----
                # torch (loaded via stanza/argostranslate) has already registered
                # pybind11 types like _gpuDeviceProperties and ProgramDescTracer.
                # paddle's libpaddle.pyd tries to register types with the same
                # names, causing "already registered" errors.
                #
                # By deleting the pybind11 internals capsule, we force pybind11
                # to create fresh internals when paddle loads. torch's types
                # stay alive as Python objects in memory; they just lose their
                # pybind11 registry entries. For CPU inference (no GPU/JIT),
                # this is safe because the conflicting types are never used.
                _saved_capsule = None
                _internals_key = None
                try:
                    import ctypes as _ct
                    _PyInterpreterState_GetDict = _ct.pythonapi.PyInterpreterState_GetDict
                    _PyInterpreterState_GetDict.restype = _ct.py_object
                    _PyInterpreterState_GetDict.argtypes = [_ct.c_void_p]
                    _PyThreadState_GetInterpreter = _ct.pythonapi.PyThreadState_GetInterpreter
                    _PyThreadState_GetInterpreter.restype = _ct.c_void_p
                    _PyThreadState_GetInterpreter.argtypes = [_ct.c_void_p]
                    _PyThreadState_Get = _ct.pythonapi.PyThreadState_Get
                    _PyThreadState_Get.restype = _ct.c_void_p
                    _tstate = _PyThreadState_Get()
                    _interp = _PyThreadState_GetInterpreter(_tstate)
                    _interp_dict = _PyInterpreterState_GetDict(_interp)
                    for _k in list(_interp_dict.keys()):
                        if 'pybind11_internals' in str(_k):
                            _internals_key = _k
                            _saved_capsule = _interp_dict[_k]
                            del _interp_dict[_k]
                            break
                except Exception:
                    pass  # If we can't clear, loading will fail with the
                          # original error - no worse than before

                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(
                        'paddle.base.libpaddle', _libpaddle_pyd_path
                    )
                    real_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(real_module)
                    _rthook_log('  libpaddle.pyd loaded successfully')

                    # Save reference to the real module
                    _proxy._real_module = real_module

                    # Copy ALL attributes from the real module INTO the proxy.
                    _proxy.__dict__.update(real_module.__dict__)

                    # Pre-set LoDTensor alias (same as core.py line 279).
                    # This is needed because paddle has a circular import:
                    #   core.py → __init__.py → dataset → utils → dlpack
                    #   → from ..base.core import LoDTensor
                    # The circular import resolves BEFORE core.py line 279
                    # sets libpaddle.LoDTensor = libpaddle.Tensor, so we
                    # must set it here to ensure it's available early.
                    if hasattr(real_module, 'Tensor'):
                        _proxy.__dict__['LoDTensor'] = real_module.Tensor
                        _rthook_log('  LoDTensor alias set on proxy')

                        # CRITICAL: Also inject LoDTensor directly into
                        # paddle.base.core's namespace. At this point, our
                        # lazy load is triggered from within core.py (line 270)
                        # and core module is already in sys.modules (partially
                        # loaded). We inject LoDTensor now so it's available
                        # even if 'from .libpaddle import *' at core.py:281
                        # is affected by the __name__/__file__ overwrite issue
                        # (core.py:283 imports __name__ from libpaddle).
                        _core_mod = sys.modules.get('paddle.base.core')
                        if _core_mod is not None:
                            _core_mod.__dict__['LoDTensor'] = real_module.Tensor
                            # Also set LoDTensorArray if Tensor is available
                            if hasattr(real_module, 'LoDTensorArray'):
                                _core_mod.__dict__['LoDTensorArray'] = real_module.LoDTensorArray
                            _rthook_log(f'  LoDTensor injected into paddle.base.core')

                    # Remove __all__ so 'from .libpaddle import *' in core.py
                    # falls back to __dict__ keys. Otherwise, dynamically added
                    # attributes (like LoDTensor = Tensor) wouldn't be exported.
                    _proxy.__dict__.pop('__all__', None)

                    # Remove __getattr__ now that all attrs are copied.
                    # This prevents it from forwarding __all__ lookups to the
                    # real module (whose __all__ doesn't include LoDTensor).
                    _proxy.__dict__.pop('__getattr__', None)
                    _rthook_log(f'  Proxy setup complete. LoDTensor in proxy: {"LoDTensor" in _proxy.__dict__}')

                    # Keep proxy in sys.modules
                    sys.modules['libpaddle'] = _proxy

                    return _proxy.__dict__.get(name, getattr(real_module, name))
                finally:
                    for h in dll_handles:
                        try:
                            h.close()
                        except Exception:
                            pass

            # Set __getattr__ as a module-level function (PEP 562, Python 3.7+)
            _proxy.__getattr__ = _lazy_load_libpaddle

            # Pre-register the proxy in sys.modules
            sys.modules['paddle.base.libpaddle'] = _proxy
            sys.modules['libpaddle'] = _proxy
            _rthook_log(f'Proxy registered in sys.modules. pyd={_libpaddle_pyd_path}')

    # Set PaddleOCR home directory to user's AppData (writable location)
    import tempfile
    paddleocr_home = os.path.join(
        os.environ.get('APPDATA', tempfile.gettempdir()), 'PaddleOCR')
    os.makedirs(paddleocr_home, exist_ok=True)
    os.environ['HUB_HOME'] = paddleocr_home

    # Redirect stdout/stderr to prevent write errors during model init
    import io
    if not hasattr(sys.stdout, 'write') or sys.stdout is None:
        sys.stdout = io.StringIO()
    if not hasattr(sys.stderr, 'write') or sys.stderr is None:
        sys.stderr = io.StringIO()
