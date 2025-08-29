"""
Memory-Monitored Utility Agent for Performance Analysis

This is a copy of the original UtilityAgent with extensive memory monitoring added.
The goal is to identify exactly where and when memory usage spikes occur during
customer verification and message processing, particularly during SOAP API calls.

Key monitoring points:
1. Before/after each major operation
2. Memory usage during agent creation
3. Memory tracking during SOAP API calls
4. Peak memory usage identification
5. Memory growth over multiple requests

Usage: Replace the import in routes to use this class temporarily for debugging.
"""

import gc
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command

from app.utilities.instances import get_db_manager
from app.utilities.soap_api import my_alerts, my_usage

from .prompts import get_system_prompt
from .state import UtilityAgentState
from .tools import analyze_usage_patterns, check_outage_status, check_phone_verification_status, enroll_paperless_billing, get_bill_balance, get_meter_reading, get_payment_link, report_outage, verify_phone_number

load_dotenv()


def setup_checkpoint_logging():
	"""Set up logging for checkpoint clearing operations."""
	output_dir = Path(__file__).resolve().parent.parent / "output"
	output_dir.mkdir(parents=True, exist_ok=True)

	log_file = output_dir / "checkpoint.logs"

	logger = logging.getLogger("checkpoint_clearer")
	logger.setLevel(logging.INFO)
	logger.propagate = False  # Prevent logs from appearing in the terminal

	# Remove existing handlers to avoid duplicates
	if logger.hasHandlers():
		logger.handlers.clear()

	file_handler = logging.FileHandler(log_file)
	file_handler.setLevel(logging.INFO)

	formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
	file_handler.setFormatter(formatter)

	logger.addHandler(file_handler)

	return logger


class MemoryMonitor:
	"""
	Utility class for tracking memory usage at different points in the application.
	Logs detailed memory statistics to help identify memory leaks and spikes.
	"""

	def __init__(self, process_name="UtilityAgent"):
		self.process = psutil.Process(os.getpid())
		self.process_name = process_name
		self.baseline_memory = None
		self.peak_memory = 0
		self.monitoring_active = os.getenv("FLASK_ENV") == "development"

	def get_memory_info(self):
		"""Get comprehensive memory information."""
		try:
			memory_info = self.process.memory_info()
			memory_percent = self.process.memory_percent()

			return {
				"rss_mb": memory_info.rss / 1024 / 1024,  # Resident Set Size in MB
				"vms_mb": memory_info.vms / 1024 / 1024,  # Virtual Memory Size in MB
				"percent": memory_percent,
				"pid": self.process.pid,
				"num_threads": self.process.num_threads(),
			}
		except Exception as e:
			logging.error(f"Failed to get memory info: {e}")
			return {"error": str(e)}

	def log_memory(self, stage, details=None):
		"""Log memory usage at a specific stage with optional details."""
		if not self.monitoring_active:
			return

		try:
			info = self.get_memory_info()

			if "error" not in info:
				# Track peak memory
				self.peak_memory = max(self.peak_memory, info["rss_mb"])

				# Set baseline on first call
				if self.baseline_memory is None:
					self.baseline_memory = info["rss_mb"]

				# Calculate growth from baseline
				growth_mb = info["rss_mb"] - self.baseline_memory

				# Log comprehensive memory info
				log_msg = (
					f"[MEMORY-{stage}] "
					f"RSS: {info['rss_mb']:.1f}MB "
					f"VMS: {info['vms_mb']:.1f}MB "
					f"Growth: +{growth_mb:.1f}MB "
					f"Peak: {self.peak_memory:.1f}MB "
					f"CPU: {info['percent']:.1f}% "
					f"Threads: {info['num_threads']} "
					f"PID: {info['pid']}"
				)

				if details:
					log_msg += f" | {details}"

				logging.info(log_msg)

				# Force garbage collection and log impact
				if stage in ["POST_SOAP", "POST_AGENT_CREATE", "POST_PROCESS"]:
					before_gc = info["rss_mb"]
					collected = gc.collect()
					after_info = self.get_memory_info()
					gc_freed = before_gc - after_info["rss_mb"]
					logging.info(f"[MEMORY-GC] Collected {collected} objects, freed {gc_freed:.1f}MB")

		except Exception as e:
			logging.error(f"Memory monitoring error at {stage}: {e}")

	def log_object_counts(self, stage):
		"""Log Python object counts to identify memory leaks."""
		if not self.monitoring_active:
			return
		try:
			# Get counts of different object types

			counts = {}
			for obj in gc.get_objects():
				obj_type = type(obj).__name__
				counts[obj_type] = counts.get(obj_type, 0) + 1

			# Log top 10 most common objects
			top_objects = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
			obj_summary = ", ".join([f"{name}:{count}" for name, count in top_objects])
			logging.info(f"[OBJECTS-{stage}] Top objects: {obj_summary}")

		except Exception as e:
			logging.error(f"Object counting error at {stage}: {e}")


class UtilityAgent:
	"""
	Identical to UtilityAgent but with comprehensive memory monitoring.

	This class adds memory tracking at every critical point:
	- Agent initialization
	- LLM creation
	- Graph compilation
	- SOAP API calls
	- Customer verification
	- Message processing

	Memory is logged before and after each major operation to identify
	exactly where memory spikes occur and how much memory each operation consumes.
	"""

	def __init__(self):
		# Initialize memory monitor first
		self.memory_monitor = MemoryMonitor("UtilityAgent")
		self.memory_monitor.log_memory("INIT_START", "Agent initialization starting")

		# Original initialization code
		self.tools = [
			report_outage,
			check_outage_status,
			get_meter_reading,
			enroll_paperless_billing,
			get_bill_balance,
			get_payment_link,
			analyze_usage_patterns,
			check_phone_verification_status,
			verify_phone_number,
		]
		self.memory = None
		self.graph_path = Path("output/utility_agent_graph.png")

		# Monitor LLM creation - This now happens once on init.
		self.memory_monitor.log_memory("PRE_LLM_CREATE", "Before ChatOpenAI creation")
		self.llm = ChatOpenAI(
			model="gpt-4.1",
			temperature=0.2,
			max_retries=3,
		)
		self.memory_monitor.log_memory("POST_LLM_CREATE", "After ChatOpenAI creation")

		# Monitor agent creation - This is the BIG memory consumer and now runs once.
		self.memory_monitor.log_memory("PRE_AGENT_CREATE", "Before agent creation (CRITICAL POINT)")
		self.graph = self.create_utility_agent(self.llm)
		self.memory_monitor.log_memory("POST_AGENT_CREATE", "After agent creation (MEMORY PEAK LIKELY HERE)")

		# Track initialization completion
		self.memory_monitor.log_memory("INIT_END", "Agent initialization complete")
		self.memory_monitor.log_object_counts("INIT")

	def verify_customer(self, state: UtilityAgentState) -> UtilityAgentState:
		"""
		Customer verification with memory monitoring at each step.
		This is where SOAP API calls happen, so we monitor closely.
		"""
		self.memory_monitor.log_memory("VERIFY_START", "Starting customer verification")

		phone_number = state.get("phone_number")
		system_prompt = get_system_prompt()

		# SOAP API verification path - This is where memory issues likely occur
		self.memory_monitor.log_memory("PRE_SOAP_ALERTS", f"Before SOAP MyAlerts call for {phone_number}")

		# Monitor MyAlerts API call
		account_id = my_alerts(phone_number)

		self.memory_monitor.log_memory("POST_SOAP_ALERTS", f"After SOAP MyAlerts, account_id: {account_id}")
		logging.info(f"account_id: {account_id}")

		if account_id:
			# Monitor MyUsage API call - this is likely the biggest memory consumer
			self.memory_monitor.log_memory("PRE_SOAP_USAGE", f"Before SOAP MyUsage call for account {account_id}")

			data = my_usage(account_id)

			self.memory_monitor.log_memory("POST_SOAP_USAGE", "After SOAP MyUsage call, data retrieved")

			hm = SystemMessage(content=f"{system_prompt}\n\nThe customer's full name is {data['name']}. Greet them with their first name, and do not use it too often.")

			self.memory_monitor.log_memory("SOAP_VERIFY_SUCCESS", f"SOAP verification complete for {data['name']}")

			return Command(
				goto="chatbot",
				update={
					"verified_customer": True,
					"messages": [hm],
					"local_data": False,
					"account_id": account_id,
					"customer_name": data["name"],
					"balance": data["balance"],
					"days_left": data["days_left"],
					"used": data["used"],
					"read_date": data["read_date"],
					"charge_amount": data["charge_amount"],
				},
			)

		# Monitor local database lookup
		self.memory_monitor.log_memory("PRE_LOCAL_DB", f"Before local DB lookup for {phone_number}")
		customer = get_db_manager().get_customer_by_phone(phone_number)
		self.memory_monitor.log_memory("POST_LOCAL_DB", f"After local DB lookup, found: {customer is not None}")

		if customer:
			# Local database verification path - proceed to chatbot even if not in SOAP
			customer_name = customer.name
			account_id = customer.account_id
			registered_address = customer.address
			hm = SystemMessage(content=f"{system_prompt}\n\nThe customer's full name is {customer_name}. Greet them with their first name, and do not use it too often.")

			self.memory_monitor.log_memory("LOCAL_VERIFY_SUCCESS", f"Local verification for {customer_name}")
			return Command(
				goto="chatbot",
				update={
					"verified_customer": True,
					"messages": [hm],
					"local_data": True,
					"account_id": account_id,
					"customer_name": customer_name,
					"registered_address": registered_address,
				},
			)

		# If customer not found in database, still proceed to chatbot
		# The phone number verification will be handled by the check_phone_verification_status tool
		hm = SystemMessage(content=f"{system_prompt}\n\nCustomer verification will be handled through phone number verification.")

		self.memory_monitor.log_memory("VERIFY_PROCEED", "Proceeding to chatbot for phone verification")

		return Command(
			goto="chatbot",
			update={
				"verified_customer": False,
				"messages": [hm],
			},
		)

	def _create_sqlite_connection(self) -> sqlite3.Connection:
		"""SQLite connection creation with memory monitoring."""
		self.memory_monitor.log_memory("PRE_SQLITE", "Before SQLite connection creation")

		try:
			conn = sqlite3.connect(
				"app/databases/utility_agent_memory.db",
				check_same_thread=False,
				timeout=30.0,
			)
			conn.execute("PRAGMA foreign_keys = ON")
			conn.execute("PRAGMA journal_mode = WAL")

			self.memory_monitor.log_memory("POST_SQLITE", "After SQLite connection creation")
			return conn

		except sqlite3.Error as e:
			logging.error(f"Failed to initialize SQLite connection: {e!s}", exc_info=True)
			self.memory_monitor.log_memory("SQLITE_ERROR", f"SQLite connection failed: {e}")
			raise

	def create_utility_agent(self, llm):
		"""
		Agent creation with detailed memory monitoring.
		This is called once during initialization to create the main agent graph.
		"""
		self.memory_monitor.log_memory("AGENT_CREATE_START", "Starting agent creation")

		tools = self.tools

		# Monitor StateGraph creation
		self.memory_monitor.log_memory("PRE_STATE_GRAPH", "Before StateGraph creation")
		graph_builder = StateGraph(UtilityAgentState)
		self.memory_monitor.log_memory("POST_STATE_GRAPH", "After StateGraph creation")

		def chatbot(state: UtilityAgentState):
			verified_customer = state.get("verified_customer")
			phone_number = state.get("phone_number")
			
			# If customer is not verified but has a phone number, consider them verified
			# since phone number verification is the only gateway required
			if not verified_customer and phone_number:
				logging.info(f"Customer with phone number {phone_number} automatically considered verified")
				# Set verified_customer to True and proceed with conversation
				state["verified_customer"] = True
			
			# If still not verified (no phone number), go to verification
			if not verified_customer:
				return Command(goto="verify_customer")
				
			llm_with_tools = llm.bind_tools(tools)
			return {"messages": [llm_with_tools.invoke(state["messages"])]}

		# Monitor node and edge creation
		self.memory_monitor.log_memory("PRE_GRAPH_BUILD", "Before graph structure building")

		tool_node = ToolNode(tools=tools)
		graph_builder.add_node("verify_customer", self.verify_customer)
		graph_builder.add_node("chatbot", chatbot)
		graph_builder.add_node("tools", tool_node)
		graph_builder.set_entry_point("chatbot")
		graph_builder.add_conditional_edges(
			"chatbot",
			tools_condition,
		)
		graph_builder.add_edge("tools", "chatbot")

		self.memory_monitor.log_memory("POST_GRAPH_BUILD", "After graph structure building")

		# Monitor SQLite connection creation
		conn = self._create_sqlite_connection()

		# Monitor SqliteSaver creation
		self.memory_monitor.log_memory("PRE_SQLITE_SAVER", "Before SqliteSaver creation")
		memory = SqliteSaver(conn)
		self.memory = memory
		logging.info("Successfully initialized SQLite connection")
		self.memory_monitor.log_memory("POST_SQLITE_SAVER", "After SqliteSaver creation")

		# Monitor graph compilation - This is likely expensive
		self.memory_monitor.log_memory("PRE_GRAPH_COMPILE", "Before graph compilation")
		graph = graph_builder.compile(checkpointer=memory)
		self.memory_monitor.log_memory("POST_GRAPH_COMPILE", "After graph compilation")

		# Monitor PNG generation - This is definitely expensive and unnecessary
		# self.memory_monitor.log_memory("PRE_PNG_GENERATE", "Before PNG generation")
		# with self.graph_path.open("wb") as f:
		# 	f.write(graph.get_graph().draw_mermaid_png())
		# logging.info(f"Graph visualization saved to {self.graph_path}")
		# self.memory_monitor.log_memory("POST_PNG_GENERATE", "After PNG generation")

		# Final agent creation memory check
		self.memory_monitor.log_memory("AGENT_CREATE_END", "Agent creation complete")
		self.memory_monitor.log_object_counts("AGENT_CREATE")

		return graph

	def process_message(self, user_input: str, phone_number: str | None = None, session_id: str | None = None) -> str:
		"""
		Message processing with comprehensive memory monitoring.
		This method is called for every user interaction and uses the single, pre-created agent graph.
		"""
		self.memory_monitor.log_memory("PROCESS_START", f"Starting message processing for {phone_number}")

		try:
			logging.info("=== Starting message processing ===")
			logging.info(f"Input message: {user_input}")
			logging.info(f"Phone number: {phone_number}")
			logging.info(f"Session ID: {session_id}")

			if not phone_number:
				logging.error("No phone number provided")
				raise ValueError("Phone number is required")

			# Agent and LLM are now created in __init__ and stored as self.graph and self.llm

			# Configuration setup
			config = {
				"configurable": {
					"thread_id": session_id,
				},
			}

			logging.info(f"Using thread ID: {config['configurable']['thread_id']}")
			logging.info("Invoking agent with message")

			# Monitor agent streaming
			self.memory_monitor.log_memory("PRE_AGENT_STREAM", "Before agent.stream() call")

			events = self.graph.stream(
				{
					"messages": [HumanMessage(content=user_input if user_input else "ignore this message. Dont reply to this message")],
					"phone_number": phone_number,
					"llm": self.llm,
				},
				config,
				stream_mode="values",
			)

			# Process events
			for event in events:
				last_message = event["messages"][-1]

			self.memory_monitor.log_memory("POST_AGENT_STREAM", "After agent.stream() processing")

			logging.info("Agent response received successfully")
			logging.info(f"Response content: {last_message.content[:100]}...")

			# Final memory check before returning
			self.memory_monitor.log_memory("PROCESS_END", "Message processing complete")

			# Add logic to get current time here and store it in db
			try:
				conn = self.memory.conn
				cursor = conn.cursor()
				current_time = datetime.utcnow().isoformat()
				cursor.execute(
					"""
					INSERT INTO ttl (thread_id, last_message_time)
					VALUES (?, ?)
					ON CONFLICT(thread_id) DO UPDATE SET last_message_time=excluded.last_message_time;
					""",
					(session_id, current_time),
				)
				conn.commit()
				cursor.close()
				logging.info(f"Updated ttl table for thread_id={session_id} at {current_time}")
			except Exception as e:
				logging.error(f"Failed to upsert ttl for thread_id={session_id}: {e}")

			return last_message.content

		except Exception as e:
			logging.error(f"Unexpected error in process_message: {e!s}", exc_info=True)
			self.memory_monitor.log_memory("PROCESS_ERROR", f"Error occurred: {str(e)[:100]}")
			raise
		finally:
			# Memory cleanup attempt
			self.memory_monitor.log_memory("PRE_CLEANUP", "Before cleanup operations")

			# Try to encourage garbage collection
			collected = gc.collect()

			self.memory_monitor.log_memory("POST_CLEANUP", f"After cleanup, collected {collected} objects")

	def clear_memory(self, session_id: str):
		"""Memory clearing with monitoring."""
		self.memory_monitor.log_memory("CLEAR_START", f"Starting memory clear for session {session_id}")

		try:
			thread_id = session_id
			logging.info("=== Starting memory clear operation ===")
			logging.info(f"Clearing memory for thread: {thread_id}")

			# Use the existing connection from the SqliteSaver for consistency
			conn = self.memory.conn
			cursor = conn.cursor()
			try:
				# Use a transaction to ensure atomicity
				cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
				conn.commit()
				logging.info(f"Cleared memory for thread {thread_id} from database")
			except sqlite3.Error as e:
				conn.rollback()
				logging.error(f"Database error during memory clear: {e!s}", exc_info=True)
				raise
			finally:
				cursor.close()

			logging.info("=== Memory clear operation completed successfully ===")

			self.memory_monitor.log_memory("CLEAR_END", "Memory clear complete")

		except sqlite3.Error as e:
			logging.error(
				f"Failed to clear thread memory from database: {e!s}",
				exc_info=True,
			)
			self.memory_monitor.log_memory("CLEAR_ERROR", f"Memory clear failed: {e}")
			raise

	def clear_old_checkpoints(self):
		"""Clear old checkpoints from the checkpoints database."""
		try:
			checkpoint_logger = setup_checkpoint_logging()

			now = datetime.utcnow()
			stale_cutoff = now - timedelta(minutes=45)
			cursor = self.memory.conn.cursor()
			cursor.execute("SELECT thread_id, last_message_time FROM ttl")
			rows = cursor.fetchall()

			cleared = 0
			for thread_id, last_message_time in rows:
				try:
					if last_message_time is None:
						continue
					checkpoint_logger.info(f"last_message_time: {last_message_time}")
					last_time = datetime.fromisoformat(last_message_time)
					checkpoint_logger.info(f"last_time: {last_time}")
					checkpoint_logger.info(f"stale_cutoff: {stale_cutoff}")
					if last_time < stale_cutoff:
						checkpoint_logger.info(f"Clearing memory for stale thread_id={thread_id} (last_message_time={last_message_time})")
						self.clear_memory(thread_id)
						cleared += 1
				except Exception as e:
					checkpoint_logger.error(f"Error processing thread_id={thread_id}: {e}")
				checkpoint_logger.info(f"Cleared {cleared} stale sessions.")
		except Exception as e:
			checkpoint_logger.error(f"Error clearing old checkpoints: {e!s}", exc_info=True)
			self.memory_monitor.log_memory("CLEAR_ERROR", f"Error clearing old checkpoints: {e}")
			raise
