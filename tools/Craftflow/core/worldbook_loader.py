# tools/Craftflow/core/worldbook_loader.py
"""
Worldbook loader: 讀取 worldbook/ 下的 YAML 設定檔，
轉成結構化的 Character / WorldRules 物件供分析器使用。

設計原則：
- 設定檔即真實來源，分析器不擅自推論未定義內容。
- Loader 不負責驗證語意，只負責解析與規範化。
- 缺欄位 / 空檔 → 安全預設值，不丟例外（避免阻擋創作流程）。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
import yaml


@dataclass
class Character:
    name: str
    aliases: List[str] = field(default_factory=list)
    core_traits: List[str] = field(default_factory=list)
    behavior_rules: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    voice_style: str = ""
    notes: str = ""
    source_file: Optional[Path] = None

    @property
    def all_names(self) -> List[str]:
        """name + aliases，用於文本中的提及偵測。"""
        return [self.name] + list(self.aliases)


@dataclass
class WorldRules:
    name: str = "default"
    hard_rules: List[str] = field(default_factory=list)
    soft_rules: List[str] = field(default_factory=list)
    forbidden_keywords: List[str] = field(default_factory=list)
    factions: List[Dict] = field(default_factory=list)
    notes: str = ""
    source_file: Optional[Path] = None


@dataclass
class Worldbook:
    characters: List[Character] = field(default_factory=list)
    worlds: List[WorldRules] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.characters and not self.worlds

    def find_character(self, name: str) -> Optional[Character]:
        for c in self.characters:
            if c.name == name or name in c.aliases:
                return c
        return None


class WorldbookLoader:
    """
    讀取 worldbook 目錄。預設目錄結構：
        worldbook/
            characters/*.yml
            world/*.yml

    任何單一檔案解析失敗都會被記錄但不阻斷其他檔案載入。
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.errors: List[str] = []

    def load(self) -> Worldbook:
        wb = Worldbook()

        if not self.root.exists():
            return wb

        char_dir = self.root / "characters"
        if char_dir.is_dir():
            for f in sorted(char_dir.glob("*.yml")) + sorted(char_dir.glob("*.yaml")):
                c = self._load_character(f)
                if c is not None:
                    wb.characters.append(c)

        world_dir = self.root / "world"
        if world_dir.is_dir():
            for f in sorted(world_dir.glob("*.yml")) + sorted(world_dir.glob("*.yaml")):
                w = self._load_world(f)
                if w is not None:
                    wb.worlds.append(w)

        return wb

    # ---------- internal ----------

    def _read_yaml(self, path: Path) -> Optional[dict]:
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if data is None:
                return {}
            if not isinstance(data, dict):
                self.errors.append(f"{path}: top-level YAML must be a mapping.")
                return None
            return data
        except yaml.YAMLError as e:
            self.errors.append(f"{path}: YAML parse error: {e}")
            return None
        except OSError as e:
            self.errors.append(f"{path}: read error: {e}")
            return None

    def _load_character(self, path: Path) -> Optional[Character]:
        data = self._read_yaml(path)
        if data is None:
            return None
        name = data.get("name") or path.stem
        return Character(
            name=str(name),
            aliases=[str(x) for x in (data.get("aliases") or [])],
            core_traits=[str(x) for x in (data.get("core_traits") or [])],
            behavior_rules=[str(x) for x in (data.get("behavior_rules") or [])],
            forbidden_actions=[str(x) for x in (data.get("forbidden_actions") or [])],
            voice_style=str(data.get("voice_style") or ""),
            notes=str(data.get("notes") or ""),
            source_file=path,
        )

    def _load_world(self, path: Path) -> Optional[WorldRules]:
        data = self._read_yaml(path)
        if data is None:
            return None
        return WorldRules(
            name=str(data.get("name") or path.stem),
            hard_rules=[str(x) for x in (data.get("hard_rules") or [])],
            soft_rules=[str(x) for x in (data.get("soft_rules") or [])],
            forbidden_keywords=[str(x) for x in (data.get("forbidden_keywords") or [])],
            factions=list(data.get("factions") or []),
            notes=str(data.get("notes") or ""),
            source_file=path,
        )
