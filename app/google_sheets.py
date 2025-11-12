from __future__ import annotations
import gspread
from google.oauth2.service_account import Credentials
from loguru import logger
from typing import Any, cast, List

from .constants import COLUMNS

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class Sheets:
    def __init__(self, spreadsheet_id: str, sheet_name: str, cred_path: str = "credentials.json"):
        creds = Credentials.from_service_account_file(cred_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        self.ws = client.open_by_key(spreadsheet_id).worksheet(sheet_name)
        logger.info(f"Google Sheets подключен: {sheet_name}")

    def append_deal(self, values: List[str]) -> None:
        """Добавляет заявку (одну строку) в конец листа по новому ТЗ."""
        try:
            if len(values) != len(COLUMNS):
                logger.warning(f"append_deal: ожидается {len(COLUMNS)} значений, получено {len(values)}")

            # Коррекция прибыли с учетом расходов (%). Если поле заполнено, уменьшаем прибыль.
            try:
                expense_pct = float(values[COLUMNS['expenses']]) if values[COLUMNS['expenses']] else 0
                profit_eur = float(values[COLUMNS['profit_eur']]) if values[COLUMNS['profit_eur']] else 0
                if expense_pct > 0 and profit_eur != 0:
                    adjusted_profit = profit_eur * (1 - expense_pct / 100)
                    values[COLUMNS['profit_eur']] = f"{adjusted_profit:.2f}"
            except Exception as err:
                logger.warning(f"Ошибка расчета прибыли с учетом расходов: {err}")

            self.ws.append_row(values, value_input_option=cast(Any, "USER_ENTERED"))
            logger.info("Добавлена новая заявка в Google Sheet!")
        except Exception as e:
            logger.exception(e)
            raise

    def get_all_rows(self) -> list[list[str]]:
        try:
            return self.ws.get_all_values()
        except Exception as e:
            logger.exception(e)
            return []