from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict


class SheetLoader(ABC):
    @abstractmethod
    def load_services(self) -> List[Dict[str, str]]:
        raise NotImplementedError

    @abstractmethod
    def load_availability(self) -> List[Dict[str, str]]:
        raise NotImplementedError

    def load_from_google_api(self) -> List[Dict[str, str]]:
        raise NotImplementedError("Google Sheets API loader not implemented")


class CSVSheetLoader(SheetLoader):
    def __init__(self, data_dir: str) -> None:
        self._data_dir = Path(data_dir)

    def _read_csv(self, filename: str) -> List[Dict[str, str]]:
        path = self._data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing CSV file: {path}")
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return [row for row in reader]

    def load_services(self) -> List[Dict[str, str]]:
        return self._read_csv("services.csv")

    def load_availability(self) -> List[Dict[str, str]]:
        return self._read_csv("availability.csv")
