"""GPUジョブディスパッチャのテスト（設計レビュー13 C-3）。"""

import threading
import time

import pytest

from dispatcher import GpuJobError
from dispatcher.local import LocalDispatcher
from dispatcher.registry import clear as clear_registry
from dispatcher.registry import get as get_job
from dispatcher.registry import register


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


def test_register_and_get_job():
    register("echo", lambda payload: {"echoed": payload})
    fn = get_job("echo")
    assert fn({"a": 1}) == {"echoed": {"a": 1}}


def test_get_unregistered_job_raises_keyerror():
    with pytest.raises(KeyError, match="no job registered"):
        get_job("does_not_exist")


def test_local_dispatcher_runs_registered_job_and_returns_result():
    register("double", lambda payload: {"value": payload["value"] * 2})
    dispatcher = LocalDispatcher(max_concurrent=1)
    result = dispatcher.dispatch("double", {"value": 21})
    assert result == {"value": 42}


def test_local_dispatcher_wraps_job_exceptions_as_gpu_job_error():
    def _boom(payload):
        raise ValueError("gpu exploded")

    register("boom", _boom)
    dispatcher = LocalDispatcher(max_concurrent=1)
    with pytest.raises(GpuJobError, match="gpu exploded"):
        dispatcher.dispatch("boom", {})


def test_local_dispatcher_rejects_invalid_max_concurrent():
    with pytest.raises(ValueError):
        LocalDispatcher(max_concurrent=0)


def test_local_dispatcher_limits_concurrent_jobs():
    # 10 §「キュー長連動の並列度」はディスパッチャの同時起動数制御で実現する、の検証。
    # max_concurrent=1 なら2件同時dispatchしても片方が完了するまでもう片方は始まらない。
    started_at = []
    finished_at = []

    def _slow_job(payload):
        started_at.append(time.monotonic())
        time.sleep(0.1)
        finished_at.append(time.monotonic())
        return {}

    register("slow", _slow_job)
    dispatcher = LocalDispatcher(max_concurrent=1)

    threads = [threading.Thread(target=lambda: dispatcher.dispatch("slow", {})) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(started_at) == 2
    assert len(finished_at) == 2
    starts, finishes = sorted(started_at), sorted(finished_at)
    # 直列実行なら「早く始まった方の終了」は「遅く始まった方の開始」以前になる
    # （どちらのスレッドが先に走るかは保証されないため、開始/終了時刻を個別にソートして比較する）
    assert finishes[0] <= starts[1] + 0.01
