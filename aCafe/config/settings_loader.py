"""
設定ファイル読み込みモジュール
JSONファイル + 環境変数をサポート
"""
import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path(__file__).resolve().parent


class ConfigLoader:
    """JSON設定を読み込み、環境変数でオーバーライド可能"""
    
    def __init__(self, env: str = None):
        """
        Args:
            env: 環境名 ('development', 'production', etc.)
                 Noneの場合は DJANGO_ENV環境変数から取得
                 どちらもNoneなら 'development' がデフォルト
        """
        self.env = env or os.getenv('DJANGO_ENV', 'development')
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """デフォルト設定と環境別設定をマージ"""
        # デフォルト設定を読み込み
        default_config_file = CONFIG_DIR / 'default.json'
        with open(default_config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 環境別設定があれば読み込みしてマージ
        env_config_file = CONFIG_DIR / f'{self.env}.json'
        if env_config_file.exists():
            with open(env_config_file, 'r', encoding='utf-8') as f:
                env_config = json.load(f)
                config = self._deep_merge(config, env_config)
        
        return config
    
    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """辞書をマージ（ネストされたキーも対応）"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key_path: str, default=None) -> Any:
        """
        ドット記法でネストされた値を取得
        例: 'api.pixazo.url' -> config['api']['pixazo']['url']
        
        Args:
            key_path: ドット区切りのキーパス
            default: キーが見つからない場合のデフォルト値
        
        Returns:
            設定値、またはデフォルト値
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_all(self) -> Dict[str, Any]:
        """全ての設定を取得"""
        return self.config


# グローバルインスタンス
config = ConfigLoader()

# 便利な関数
def get_config(key_path: str, default=None):
    """グローバルコンフィグから値を取得"""
    return config.get(key_path, default)
