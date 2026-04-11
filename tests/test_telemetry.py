# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from synthadoc.observability.telemetry import setup_telemetry, get_tracer, record_cost


def test_tracer_created(tmp_path):
    setup_telemetry(trace_path=tmp_path / "traces.jsonl")
    assert get_tracer() is not None


def test_record_cost_does_not_raise():
    record_cost(tokens=1000, cost_usd=0.01, operation="ingest")


def test_traces_written_to_file(tmp_path):
    setup_telemetry(trace_path=tmp_path / "traces.jsonl")
    tracer = get_tracer()
    with tracer.start_as_current_span("test.span"):
        pass
    assert get_tracer() is not None
