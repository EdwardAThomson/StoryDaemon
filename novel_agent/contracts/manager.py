"""Persistence for beat contracts (project-level ``contracts.json``).

Stored separately from ``plot_outline.json`` so the contract layer stays
opt-in and removable without touching the beat data the agent already relies on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .beat_contract import BeatContract


class ContractManager:
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.contracts_file = self.project_path / "contracts.json"

    def load(self) -> Dict[str, BeatContract]:
        if not self.contracts_file.exists():
            return {}
        with open(self.contracts_file) as f:
            data = json.load(f)
        return {
            entry["beat_id"]: BeatContract.from_dict(entry)
            for entry in data.get("contracts", [])
        }

    def save(self, contracts: Dict[str, BeatContract]) -> None:
        payload = {"contracts": [c.to_dict() for c in contracts.values()]}
        with open(self.contracts_file, "w") as f:
            json.dump(payload, f, indent=2)

    def get(self, beat_id: str) -> Optional[BeatContract]:
        return self.load().get(beat_id)

    def put(self, contract: BeatContract) -> None:
        contracts = self.load()
        contracts[contract.beat_id] = contract
        self.save(contracts)
