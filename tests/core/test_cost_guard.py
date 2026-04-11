# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.core.cost_guard import CostGuard, CostEstimate, CostGateError
from synthadoc.config import CostConfig


def test_under_soft_warn_no_output(capsys):
    guard = CostGuard(CostConfig(soft_warn_usd=1.0, hard_gate_usd=5.0))
    guard.check(CostEstimate(tokens=100, cost_usd=0.01, operation="ingest"), auto_confirm=True)
    assert "warn" not in capsys.readouterr().out.lower()


def test_over_soft_warn_prints_warning(capsys):
    guard = CostGuard(CostConfig(soft_warn_usd=0.05, hard_gate_usd=5.0))
    guard.check(CostEstimate(tokens=5000, cost_usd=0.10, operation="ingest"), auto_confirm=True)
    out = capsys.readouterr().out.lower()
    assert "warn" in out or "cost" in out


def test_over_hard_gate_raises_without_confirm():
    guard = CostGuard(CostConfig(soft_warn_usd=0.01, hard_gate_usd=0.05))
    with pytest.raises(CostGateError):
        guard.check(CostEstimate(tokens=10000, cost_usd=1.00, operation="batch"),
                    auto_confirm=False, interactive=False)


def test_over_hard_gate_passes_with_auto_confirm():
    guard = CostGuard(CostConfig(soft_warn_usd=0.01, hard_gate_usd=0.05))
    guard.check(CostEstimate(tokens=10000, cost_usd=1.00, operation="batch"), auto_confirm=True)
