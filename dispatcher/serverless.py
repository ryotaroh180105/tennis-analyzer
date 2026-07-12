"""本番用ディスパッチャ：サーバーレスGPU（RunPod/Modal等）でコンテナを起動しジョブを実行する。

**未実装**（設計レビュー13 C-3）。このセッションには実クラウドの資格情報も
docker実行環境も無く、実装しても一度も実行検証できない（不変原則1：検証していない
統合コードを「実装済み」と偽らない）。実装時に必要なもの：

1. プロバイダの選定（RunPod / Modal のどちらかを09/10の想定から確定する）
2. プロバイダAPIの資格情報（環境変数等でのシークレット管理）
3. cv-worker用コンテナイメージのプロバイダ側イメージキャッシュ登録
   （10 §「未キャッシュ時のpullはコールドスタート1〜2分の想定を超える」）
4. Docker/実クラウドが使える環境でのE2E検証

実装する際は `GpuJobDispatcher.dispatch(job_name, payload)` を満たすこと：
- プロバイダAPIでコンテナを起動し、payloadをジョブ引数として渡す
- 完了を待ち、結果（stage_results等のJSON）を返す
- 失敗時は `dispatcher.GpuJobError` を送出する
- 同時起動数の制御はプロバイダのキュー機構 or ローカルのセマフォで行う
  （`local.py` の `LocalDispatcher` を参考にできる）
"""

from dispatcher import GpuJobDispatcher


class ServerlessDispatcher(GpuJobDispatcher):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ServerlessDispatcher is not implemented yet (13 C-3). "
            "See this module's docstring for what's needed before implementing it."
        )

    def dispatch(self, job_name: str, payload: dict) -> dict:
        raise NotImplementedError
