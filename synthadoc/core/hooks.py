# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import logging
import subprocess
import threading
from typing import Union

logger = logging.getLogger(__name__)


class HookExecutor:
    def __init__(self, hooks: dict[str, Union[str, dict]]) -> None:
        self._hooks = hooks

    def _resolve(self, event: str) -> tuple[str, bool]:
        spec = self._hooks.get(event)
        if not spec:
            return "", False
        if isinstance(spec, str):
            return spec, False
        return spec.get("cmd", ""), spec.get("blocking", False)

    def _run(self, cmd: str, context: dict, blocking: bool) -> None:
        try:
            result = subprocess.run(cmd, shell=True, input=json.dumps(context).encode(),
                                    capture_output=True, timeout=60)
            if result.returncode != 0 and blocking:
                raise RuntimeError(
                    f"Hook failed (exit {result.returncode}): {result.stderr.decode()[:200]}")
            if result.returncode != 0:
                logger.warning("Hook '%s' exited %d", cmd, result.returncode)
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("Hook error '%s': %s", cmd, e)

    def fire(self, event: str, context: dict) -> None:
        cmd, blocking = self._resolve(event)
        if not cmd:
            return
        if blocking:
            self._run(cmd, context, blocking=True)
        else:
            threading.Thread(target=self._run, args=(cmd, context, False), daemon=True).start()

    def fire_blocking(self, event: str, context: dict) -> None:
        cmd, _ = self._resolve(event)
        if cmd:
            self._run(cmd, context, blocking=True)
