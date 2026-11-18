"""Per-Windows-user DPAPI protection. No plaintext fallback or production secrets."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]


def _transform(data: bytes, protect: bool) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('Windows DPAPI requires Windows; plaintext fallback prohibited')
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN; current-user scope, no machine-wide flag.
    if protect:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(incoming), 'GANOH', None, None, None, 1, ctypes.byref(outgoing))
    else:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def save_secret(path: Path, value: bytes):
    protected = _transform(value, True)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents silently replacing another installation key.
    with path.open('xb') as file:
        file.write(protected)
        file.flush()
        os.fsync(file.fileno())


def load_secret(path: Path):
    return _transform(path.read_bytes(), False)
