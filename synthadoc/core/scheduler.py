# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import platform
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScheduleEntry:
    op: str
    cron: str
    wiki: str
    id: str = field(default_factory=lambda: f"sched-{uuid.uuid4().hex[:8]}")


class Scheduler:
    _TAG_PREFIX = "# synthadoc:"

    def __init__(self, wiki: str, wiki_root: str) -> None:
        self._wiki = wiki
        self._wiki_root = wiki_root

    def add(self, op: str, cron: str) -> str:
        entry_id = f"sched-{uuid.uuid4().hex[:8]}"
        self._register_os_task(op=op, cron=cron, entry_id=entry_id)
        return entry_id

    def list(self) -> list[ScheduleEntry]:
        return self._list_os_tasks()

    def remove(self, entry_id: str) -> None:
        self._remove_os_task(entry_id)

    def apply(self, jobs: list[ScheduleEntry]) -> list[str]:
        return [self.add(op=j.op, cron=j.cron) for j in jobs]

    def _register_os_task(self, op: str, cron: str, entry_id: str) -> None:
        if platform.system() == "Windows":
            args = self._build_schtasks_args(op=op, cron=cron, entry_id=entry_id)
            subprocess.run(["schtasks"] + args, check=True)
        else:
            self._add_crontab_entry(op=op, cron=cron, entry_id=entry_id)

    def _build_crontab_line(self, op: str, cron: str, entry_id: str) -> str:
        cmd = f"synthadoc -w {self._wiki} {op}"
        return f"{cron} {cmd} {self._TAG_PREFIX}{entry_id}"

    def _add_crontab_entry(self, op: str, cron: str, entry_id: str) -> None:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = current.stdout if current.returncode == 0 else ""
        new_line = self._build_crontab_line(op=op, cron=cron, entry_id=entry_id)
        updated = existing.rstrip("\n") + "\n" + new_line + "\n"
        subprocess.run(["crontab", "-"], input=updated, text=True, check=True)

    def _build_schtasks_args(self, op: str, cron: str, entry_id: str) -> list[str]:
        parts = cron.split()
        minute, hour = parts[0], parts[1]
        cmd = f"synthadoc -w {self._wiki} {op}"
        return [
            "/Create", "/F",
            "/TN", f"synthadoc-{entry_id}",
            "/TR", cmd,
            "/SC", "DAILY",
            "/ST", f"{int(hour):02d}:{int(minute):02d}",
        ]

    def _list_os_tasks(self) -> list[ScheduleEntry]:
        if platform.system() == "Windows":
            return self._list_schtasks()
        return self._list_crontab()

    def _list_crontab(self) -> list[ScheduleEntry]:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        entries = []
        for line in result.stdout.splitlines():
            if self._TAG_PREFIX in line:
                entry_id = line.split(self._TAG_PREFIX)[-1].strip()
                parts = line.split()
                cron = " ".join(parts[:5])
                op_parts = parts[5:]
                tag = self._TAG_PREFIX.strip()
                op = " ".join(p for p in op_parts if not p.startswith(tag))
                entries.append(ScheduleEntry(id=entry_id, op=op.strip(),
                                             cron=cron, wiki=self._wiki))
        return entries

    def _list_schtasks(self) -> list[ScheduleEntry]:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V"], capture_output=True, text=True)
        entries = []
        current_name = None
        for line in result.stdout.splitlines():
            if line.startswith("TaskName:") and "synthadoc-" in line:
                current_name = line.split("synthadoc-")[-1].strip()
            if current_name and line.startswith("Task To Run:"):
                cmd = line.split(":", 1)[-1].strip()
                entries.append(ScheduleEntry(id=current_name, op=cmd,
                                             cron="", wiki=self._wiki))
                current_name = None
        return entries

    def _remove_os_task(self, entry_id: str) -> None:
        if platform.system() == "Windows":
            subprocess.run(["schtasks", "/Delete", "/TN", f"synthadoc-{entry_id}", "/F"],
                           check=True)
        else:
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            lines = [ln for ln in result.stdout.splitlines()
                     if f"{self._TAG_PREFIX}{entry_id}" not in ln]
            subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                           text=True, check=True)
