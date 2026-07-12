"""dev用ディスパッチャ：ジョブをローカルプロセス内で実行する（10 §「devでは cv-worker を
ローカルCPUで動かす」）。

実プロバイダ（RunPod/Modal）向けの `serverless.py` と同じインターフェース
（`GpuJobDispatcher.dispatch`）を実装するため、本番切替時はディスパッチャの
差し替えだけで済む（呼び出し側のコードは変更不要）。

同時起動数はセマフォで制御する（10 §「キュー長連動の並列度」＝ディスパッチャの
同時起動数制御で実現、Celery gpuキューの廃止を前提とした設計）。
"""

import threading

from dispatcher import GpuJobDispatcher, GpuJobError
from dispatcher.registry import get as get_job


class LocalDispatcher(GpuJobDispatcher):
    def __init__(self, max_concurrent: int = 1):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = threading.Semaphore(max_concurrent)

    def dispatch(self, job_name: str, payload: dict) -> dict:
        fn = get_job(job_name)
        with self._semaphore:
            try:
                return fn(payload)
            except Exception as exc:  # noqa: BLE001 — GPU側の失敗として統一的に扱う
                raise GpuJobError(f"job {job_name!r} failed: {exc}") from exc
