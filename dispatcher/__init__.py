"""GPUジョブディスパッチャ（10 §リポジトリ構成・不変原則3）。

CeleryワーカーモデルとサーバーレスGPU（RunPod/Modal）は素直に接続できないため、
接着コンポーネントとして本パッケージを置く。cpuキュー上から呼ばれ、GPUプロバイダの
API でコンテナを起動しジョブ引数を渡して完了を待つ（＝Celery gpuキューは廃止し、
「キュー長連動の並列度」はディスパッチャの同時起動数制御で実現する）。

現状の実装範囲（設計レビュー13 C-3）：
- `GpuJobDispatcher` インターフェース（本ファイル）と、dev用の `LocalDispatcher`
  （`local.py`）は実装・テスト済み
- 実プロバイダ（RunPod/Modal等）向け実装は `serverless.py` に骨格のみ用意し、
  未実装として明示する（実クラウド資格情報・Docker実行環境が無い開発セッションでは
  実装しても検証できず、動作未確認のコードを「実装済み」と偽ることになるため。
  不変原則1）。プロバイダ選定・資格情報の準備ができ次第、このモジュールを完成させ、
  `docker-compose.yml` の `worker-gpu`（常駐Celery gpuキュー）をディスパッチャ経由の
  起動に置き換える
"""

from abc import ABC, abstractmethod


class GpuJobError(Exception):
    """ディスパッチしたジョブがGPU側で失敗した場合の例外。"""


class GpuJobDispatcher(ABC):
    """GPUジョブディスパッチャの共通インターフェース。

    実装はコンテナ起動方式（ローカル/RunPod/Modal等）を問わず、このインターフェースの
    背後に隠す。呼び出し側（cpuキュー上のCeleryタスク）はプロバイダを意識しない。
    """

    @abstractmethod
    def dispatch(self, job_name: str, payload: dict) -> dict:
        """job_name のジョブをpayload付きで起動し、完了を待って結果を返す（同期呼び出し）。

        失敗時は GpuJobError を送出する（一時失敗・恒久失敗の分類は呼び出し側の責務、
        10 §ジョブオーケストレーションと同じ方針）。
        """
        raise NotImplementedError
