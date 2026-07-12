"""ジョブ名 → 実行callable のレジストリ。

ディスパッチャ実装（local.py等）がcv-worker/backendの内部実装に直接依存しないための
間接層。呼び出し側は job_name（文字列）だけを知っていればよい。
"""

from collections.abc import Callable

_REGISTRY: dict[str, Callable[[dict], dict]] = {}


def register(job_name: str, fn: Callable[[dict], dict]) -> None:
    """job_name にジョブ本体（payload dict を受けてdictを返す関数）を登録する。"""
    _REGISTRY[job_name] = fn


def get(job_name: str) -> Callable[[dict], dict]:
    if job_name not in _REGISTRY:
        raise KeyError(f"no job registered for job_name={job_name!r} (registered: {sorted(_REGISTRY)})")
    return _REGISTRY[job_name]


def clear() -> None:
    """テスト用：レジストリを空にする。"""
    _REGISTRY.clear()
