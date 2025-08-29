"""LLM client for synthetic data generation"""

import logging
from typing import Optional, Union

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config import config

# Set up logging
logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class LLMManager:
	"""Manager for LLM instances with rate limiting"""

	_instance = None

	@classmethod
	def get_instance(cls):
		"""Get singleton instance"""
		if cls._instance is None:
			cls._instance = cls()
		return cls._instance

	def __init__(self):
		"""Initialize the LLM manager"""
		self._gemini_flash_client = None
		self._openai_client = None
		self._setup_clients()

	def _setup_clients(self):
		"""Set up LLM clients with appropriate rate limits"""
		self._gemini_flash_client = None  # Reset to force recreation
		self._openai_client = None  # Reset to force recreation

	def _create_gemini_client(self) -> ChatGoogleGenerativeAI:
		logger.info(f"Using {config.gemini_flash_model_name}")

		return ChatGoogleGenerativeAI(
			api_key=config.gemini_api_key,
			model=config.gemini_flash_model_name,
		)

	def _create_openai_client(self) -> ChatOpenAI:
		logger.info(f"Using {config.openai_model_name}")

		return ChatOpenAI(
			api_key=config.openai_api_key,
			model=config.openai_model_name,
		)

	@property
	def gemini_flash_client(self) -> ChatGoogleGenerativeAI:
		"""Get Gemini flash client with rate limiting"""
		if not self._gemini_flash_client:
			self._gemini_flash_client = self._create_gemini_client()
		return self._gemini_flash_client

	@property
	def openai_client(self) -> ChatOpenAI:
		"""Get OpenAI client"""
		if not self._openai_client:
			self._openai_client = self._create_openai_client()
		return self._openai_client

	def get_llm(
		self,
		provider: str = "gemini",
	) -> ChatGoogleGenerativeAI | ChatOpenAI | None:
		"""Get the LLM client for the specified provider"""
		if provider.lower() == "openai":
			if not config.openai_api_key:
				raise ValueError("OpenAI API key not configured")
			try:
				return self.openai_client
			except Exception as e:
				logger.error(f"Error getting OpenAI client: {e!s}")
				return None
		else:  # Default to gemini
			if not config.gemini_api_key:
				raise ValueError("Google API key not configured")
			try:
				return self.gemini_flash_client
			except Exception as e:
				logger.error(f"Error getting Gemini client: {e!s}")
				return None
