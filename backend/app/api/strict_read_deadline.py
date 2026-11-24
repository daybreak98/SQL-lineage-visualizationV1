"""Bounded transport for one optional proof. The parent never runs parser or proof code here.

Wall time includes interpreter startup, imports, IPC and cleanup. Only one lease
per ASGI process; no backlog. A caller can return while an already-killed child
is reaped, but no lease is returned until that child has actually exited.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import sysconfig
import threading
from time import monotonic

ADDON_SECONDS = 4.0
RESPONSE_RESERVE_SECONDS = 1.0
MAX_REQUEST_WIRE = 128 * 1024
MAX_RESPONSE_WIRE = 256 * 1024
MAX_CHILD_MEMORY = 512 * 1024 * 1024
_BUDGET = ("BUDGET_EXCEEDED", None)
_FAILURE = ("OBSERVER_UNAVAILABLE", None)
_SLOT = threading.BoundedSemaphore(1)


def _wire(obj, cap):
    result = bytearray()
    for piece in json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False).iterencode(obj):
        raw = piece.encode("utf-8")
        if len(result) + len(raw) > cap:
            raise OverflowError
        result.extend(raw)
    return bytes(result)


def _stop(proc):
    try:
        if os.name == "posix":
            # Group is created specifically for this launch. Never signal the
            # server's process group or any name/pid discovered elsewhere.
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
        elif proc.poll() is None:
            proc.kill()
    except (OSError, ValueError):
        # Races with natural exit are expected. Lease owner still must wait().
        pass


def _invoke(argv, raw, deadline):
    if len(raw) > MAX_REQUEST_WIRE or deadline <= monotonic() or not _SLOT.acquire(blocking=False):
        return _BUDGET
    done, cancel = threading.Event(), threading.Event()
    published = threading.Lock()
    child = None
    result = _FAILURE

    def supervise():
        nonlocal child, result
        proc = None
        try:
            if cancel.is_set() or monotonic() >= deadline:
                result = _BUDGET
                return
            opts = ({"creationflags":subprocess.CREATE_NO_WINDOW} if os.name == "nt"
                    else {"start_new_session":True})
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, close_fds=True, **opts)
            with published:
                child = proc
            if cancel.is_set() or monotonic() >= deadline:
                result = _BUDGET
                return
            proc.stdin.write(raw)
            proc.stdin.close()
            # Cap BEFORE storing or decoding. Do not use unbounded communicate().
            reply = proc.stdout.read(MAX_RESPONSE_WIRE + 1)
            if len(reply) > MAX_RESPONSE_WIRE:
                result = _BUDGET
                return
            status = proc.wait(timeout=max(0., deadline-monotonic()))
            if status != 0:
                result = _BUDGET if status == 75 else _FAILURE
                return
            parsed = json.loads(reply)
            if type(parsed) is dict:
                result = (None, parsed)
        except (subprocess.TimeoutExpired, OverflowError):
            result = _BUDGET
        except (OSError, ValueError, RuntimeError, MemoryError):
            result = _FAILURE
        finally:
            try:
                if proc is not None:
                    _stop(proc)
                    # Deliberately in the supervisor, not on the request path.
                    # No new worker while OS process termination/reap is pending.
                    proc.wait()
                    proc.stdin.close()
                    proc.stdout.close()
            finally:
                _SLOT.release()
                done.set()

    # This thread does ONLY process creation / bounded pipe I/O / reap. No SQL
    # is ever executed by a thread continuing after the caller's deadline.
    try:
        threading.Thread(target=supervise, name="strict-read-process-reaper", daemon=True).start()
    except RuntimeError:
        _SLOT.release()
        return _FAILURE
    try:
        if done.wait(max(0., deadline-monotonic())) and monotonic() < deadline:
            return result
        return _BUDGET
    finally:
        if not done.is_set():
            cancel.set()
            with published:
                proc = child
            if proc is not None:
                _stop(proc)
            # Late process creation observes cancel before sending the SQL.


def run_bounded(payload, *, request_deadline=None):
    """Return (reason, None) or (None, evidence). request_deadline uses monotonic()."""
    now = monotonic()
    deadline = min(now+ADDON_SECONDS, request_deadline-RESPONSE_RESERVE_SECONDS
                   if request_deadline is not None else float("inf"))
    if deadline <= now:
        return _BUDGET
    # This delivery uses the same interpreter/venv, not the frozen GUI exe.
    # Unsupported worker hosts deliberately stay unavailable.
    if getattr(sys, "frozen", False) or not (os.name == "nt" or sys.platform.startswith("linux")):
        return _FAILURE
    if (type(payload) is not dict or set(payload) != {"sql","dialect","strict_read_site"}
            or type(payload["sql"]) is not str or len(payload["sql"]) > 16384
            or payload["dialect"] != "spark" or type(payload["strict_read_site"]) is not dict):
        return _BUDGET
    selector = payload["strict_read_site"]
    pos = selector.get("call_position")
    if (set(selector) != {"sql_sha256","statement","call_position"}
            or type(selector["sql_sha256"]) is not str or len(selector["sql_sha256"]) != 64
            or type(selector["statement"]) is not int or selector["statement"] != 1
            or type(pos) is not dict or set(pos) != {"start","end"}
            or type(pos["start"]) is not int or type(pos["end"]) is not int
            or not 0 <= pos["start"] < pos["end"] <= len(payload["sql"])):
        return _FAILURE
    try:
        raw = _wire(payload, MAX_REQUEST_WIRE)
    except OverflowError:
        return _BUDGET
    except (ValueError, TypeError, RecursionError):
        return _FAILURE
    return _invoke(_worker_argv(), raw, deadline)


def _worker_argv():
    # On Windows a venv's Scripts/python.exe is a launcher that spawns the
    # real interpreter. TerminateProcess on that launcher does NOT mean the
    # running Python workload is dead. Launch the exact interpreter directly
    # and inject only the server venv's trusted library directories. -S/-I
    # also avoid running shell profiles, .pth, user-site or global site hooks.
    executable = getattr(sys, "_base_executable", None) or sys.executable
    packages = list(dict.fromkeys(sysconfig.get_path(k) for k in ("purelib","platlib")))
    return [executable, "-I", "-S", "-B", "-X", "utf8", str(Path(__file__).resolve()), *packages]


def _cap_memory():
    """Fail closed when the platform cannot install an OS-enforced worker cap."""
    if sys.platform.startswith("linux"):
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        cap = MAX_CHILD_MEMORY if hard == resource.RLIM_INFINITY else min(MAX_CHILD_MEMORY, hard)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        # If the server itself exits unexpectedly, no unbounded orphan.
        signal.setitimer(signal.ITIMER_REAL, ADDON_SECONDS+1)
        return resource.getrlimit(resource.RLIMIT_AS)[0]
    elif os.name == "nt":
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [("process_time",c.c_int64),("job_time",c.c_int64),("flags",w.DWORD),
                        ("min_set",c.c_size_t),("max_set",c.c_size_t),("active",w.DWORD),
                        ("affinity",c.c_size_t),("priority",w.DWORD),("scheduling",w.DWORD)]
        class Extended(c.Structure):
            _fields_ = [("basic",Basic),("io",c.c_uint64*6),("process_memory",c.c_size_t),
                        ("job_memory",c.c_size_t),("peak_proc",c.c_size_t),("peak_job",c.c_size_t)]
        k = c.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.argtypes, k.CreateJobObjectW.restype = [c.c_void_p, w.LPCWSTR], w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        k.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
        k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        k.GetCurrentProcess.restype = w.HANDLE
        job = k.CreateJobObjectW(None,None)
        limits = Extended()
        # JOB_OBJECT_LIMIT_PROCESS_MEMORY | ACTIVE_PROCESS | KILL_ON_JOB_CLOSE
        limits.basic.flags, limits.basic.active, limits.process_memory = 0x2108, 1, MAX_CHILD_MEMORY
        if not (job and k.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits))
                and k.AssignProcessToJobObject(job,k.GetCurrentProcess())):
            raise OSError(c.get_last_error(), "worker resource cap unavailable")
        effective = Extended()
        if not (k.QueryInformationJobObject(job, 9, c.byref(effective), c.sizeof(effective), None)
                and effective.basic.flags & 0x2108 == 0x2108 and effective.basic.active == 1
                and effective.process_memory == MAX_CHILD_MEMORY):
            raise OSError(c.get_last_error(), "unconfirmed worker cap")
        # Process lifetime handle. Closing it while the job is active kills this child.
        return effective.process_memory
    else:
        raise RuntimeError("unsupported worker host")


def _main():
    _cap_memory()
    raw = sys.stdin.buffer.read(MAX_REQUEST_WIRE+1)
    if not raw or len(raw) > MAX_REQUEST_WIRE:
        return 1
    sys.path.extend(sys.argv[1:])
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    try:
        from app.api.strict_read_trial import worker_evidence
        block = worker_evidence(json.loads(raw))
        wire = _wire(block, MAX_RESPONSE_WIRE)
    except (MemoryError, OverflowError):
        # Dedicated tiny transport status, never interpreted as evidence.
        return 75
    sys.stdout.buffer.write(wire)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
