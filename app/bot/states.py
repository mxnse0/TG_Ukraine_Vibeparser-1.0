"""FSM state groups."""

from aiogram.fsm.state import State, StatesGroup


class ReplyStates(StatesGroup):
    waiting_text = State()


class SearchStates(StatesGroup):
    waiting_query = State()


class LibraryStates(StatesGroup):
    waiting_file = State()
    waiting_text = State()


class FilterStates(StatesGroup):
    waiting_keywords = State()
    waiting_exclude = State()
    waiting_budget = State()


class SettingsStates(StatesGroup):
    waiting_interval = State()
    waiting_limit = State()


class AutoBidStates(StatesGroup):
    comment = State()
    amount = State()
    days = State()
