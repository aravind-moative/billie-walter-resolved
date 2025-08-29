from typing import Annotated

from langchain_openai import ChatOpenAI
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class UtilityAgentState(TypedDict):
	llm: ChatOpenAI
	messages: Annotated[list, add_messages]
	verified_customer: bool = False
	phone_number: str | None
	local_data: bool | None
	account_id: str | None
	registered_address: str | None
	customer_name: str | None
	balance: float | None
	days_left: int | None
	used: float | None
	read_date: str | None
	charge_amount: float | None
