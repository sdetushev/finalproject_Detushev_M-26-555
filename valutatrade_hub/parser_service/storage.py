"""Хранение истории и актуальных валютных курсов."""

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.parser_service.config import ParserConfig

_PAIR_PATTERN = re.compile(r"^[A-Z]{2,5}_[A-Z]{2,5}$")


def _utc_now() -> str:
    """Получить текущее время в ISO UTC."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_timestamp(value: str) -> str:
    """Проверить временную метку и привести её к ISO UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Временная метка должна быть строкой")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Некорректная временная метка: {value}") from error

    if parsed.tzinfo is None:
        raise ValueError("Временная метка должна содержать часовой пояс")

    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_rate(value: Any) -> float:
    """Проверить положительное конечное значение курса."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("Курс должен быть положительным числом")

    return float(value)


class RatesStorage:
    """Управлять историей котировок и текущим кэшем."""

    def __init__(
        self,
        config: ParserConfig | None = None,
    ) -> None:
        """Сохранить конфигурацию и создать блокировку."""
        self.config = config if config is not None else ParserConfig()

        self.rates_path = self.config.RATES_FILE_PATH
        self.history_path = self.config.HISTORY_FILE_PATH

        self._lock = RLock()

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        """Прочитать JSON или вернуть значение по умолчанию."""
        if not path.exists():
            return default

        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)

        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Не удалось прочитать JSON: {path.name}") from error

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        """Атомарно сохранить JSON через временный файл."""
        path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)

                json.dump(
                    data,
                    file,
                    ensure_ascii=False,
                    indent=2,
                )

                file.flush()
                os.fsync(file.fileno())

            os.replace(temporary_path, path)

        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def load_history(self) -> list[dict[str, Any]]:
        """Прочитать историю всех измерений."""
        with self._lock:
            data = self._read_json(self.history_path, [])

            if not isinstance(data, list):
                raise ValueError("История курсов должна содержать список")

            return data

    def load_cache(self) -> dict[str, Any]:
        """Прочитать актуальные курсы, поддерживая старый формат."""
        with self._lock:
            data = self._read_json(self.rates_path, {})

            if not isinstance(data, dict):
                raise ValueError("Кэш курсов должен содержать JSON-объект")

            # Новый формат этапа 4.
            if "pairs" in data:
                if not isinstance(data["pairs"], dict):
                    raise ValueError("Поле pairs должно содержать словарь")

                return {
                    "pairs": data["pairs"],
                    "last_refresh": data.get("last_refresh"),
                }

            # Старый плоский формат этапа 3.
            pairs: dict[str, dict[str, Any]] = {}

            for pair, record in data.items():
                if not _PAIR_PATTERN.fullmatch(pair):
                    continue

                if not isinstance(record, dict):
                    raise ValueError(f"Некорректная запись курса {pair}")

                rate = _validate_rate(record.get("rate"))
                source = str(record.get("source", "unknown"))

                if source == "fixed_snapshot" and record.get("snapshot_date"):
                    # Для исторической заглушки используем дату
                    # снимка, а не время обновления её кэша.
                    raw_time = f"{record['snapshot_date']}T00:00:00Z"
                else:
                    raw_time = (
                        record.get("updated_at")
                        or record.get("saved_at")
                        or "1970-01-01T00:00:00Z"
                    )

                pairs[pair] = {
                    "rate": rate,
                    "updated_at": _normalize_timestamp(raw_time),
                    "source": source,
                }

            return {
                "pairs": pairs,
                "last_refresh": None,
            }

    def save_rates(
        self,
        rates: dict[str, float],
        source: str,
        timestamps: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Сохранить измерения и обновить только более свежие курсы."""
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Источник курсов не может быть пустым")

        if not isinstance(rates, dict):
            raise ValueError("Курсы должны передаваться словарём")

        if not rates:
            return 0

        timestamps = timestamps if timestamps is not None else {}
        meta = meta if meta is not None else {}

        received_at = _utc_now()
        records: list[dict[str, Any]] = []

        # Полная валидация до изменения файлов.
        for pair, raw_rate in rates.items():
            if not isinstance(pair, str) or not _PAIR_PATTERN.fullmatch(pair):
                raise ValueError(f"Некорректный код валютной пары: {pair}")

            from_code, to_code = pair.split("_")

            get_currency(from_code)
            get_currency(to_code)

            rate = _validate_rate(raw_rate)

            timestamp = _normalize_timestamp(timestamps.get(pair, received_at))

            records.append(
                {
                    "id": f"{pair}_{timestamp}",
                    "from_currency": from_code,
                    "to_currency": to_code,
                    "rate": rate,
                    "timestamp": timestamp,
                    "source": source,
                    "meta": dict(meta),
                }
            )

        with self._lock:
            history = self.load_history()
            cache = self.load_cache()

            existing_ids = {record["id"] for record in history}

            history_changed = False
            updated_count = 0

            for record in records:
                record_id = record["id"]

                # Одинаковое измерение в историю не добавляем.
                if record_id not in existing_ids:
                    history.append(record)
                    existing_ids.add(record_id)
                    history_changed = True

                pair = f"{record['from_currency']}_{record['to_currency']}"

                current = cache["pairs"].get(pair)
                new_time = record["timestamp"]

                if current is not None:
                    current_time = _normalize_timestamp(current["updated_at"])

                    if new_time <= current_time:
                        continue

                cache["pairs"][pair] = {
                    "rate": record["rate"],
                    "updated_at": new_time,
                    "source": source,
                }

                updated_count += 1

            if history_changed:
                self._write_json(self.history_path, history)

            if updated_count:
                cache["last_refresh"] = received_at
                self._write_json(self.rates_path, cache)

            return updated_count
