import logging
import os
import time
import uuid
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()


class SOAPClientService:
	"""SOAP API client with connection pooling and resilience"""

	def __init__(self):
		self.session = requests.Session()

		# Configure connection pooling
		retry_strategy = Retry(
			total=3,
			backoff_factor=1,
			status_forcelist=[429, 500, 502, 503, 504],
			allowed_methods=["POST"],
		)

		adapter = HTTPAdapter(
			pool_connections=5,  # Number of connection pools
			pool_maxsize=25,  # Max connections per pool
			pool_block=True,  # Block when pool is full
			max_retries=retry_strategy,
		)

		self.session.mount("http://", adapter)
		self.session.mount("https://", adapter)

		# API Configuration
		self.myalerts_config = {
			"url": os.getenv("MYALERTS_URL", "https://testv3.myusage.com/v3/soap/alerts"),
			"username": os.getenv("MYALERTS_USER"),
			"password": os.getenv("MYALERTS_PWD"),
			"soap_action": "GetAccountByContact",
		}

		self.myusage_config = {
			"url": os.getenv("MYUSAGE_URL", "https://api.myusage.com/test/2/Data"),
			"username": os.getenv("MYUSAGE_USER"),
			"password": os.getenv("MYUSAGE_PWD"),
			"soap_action": "http://www.exceleron.com/PAMS/Data/GetAccount",
		}

	@contextmanager
	def _api_call_context(self, api_name: str):
		"""Context manager for API calls with monitoring"""
		start_time = time.time()
		try:
			yield
		except requests.RequestException as e:
			duration = time.time() - start_time
			logging.error(f"{api_name} API call failed after {duration:.2f}s: {e}")
			raise
		except Exception as e:
			duration = time.time() - start_time
			logging.error(f"{api_name} processing failed after {duration:.2f}s: {e}")
			raise
		else:
			duration = time.time() - start_time
			logging.info(f"{api_name} API call completed in {duration:.2f}s")

	def my_alerts(self, phone_number: str) -> str | None:
		"""Get account ID by phone number using connection pool"""
		request_id = str(uuid.uuid4())

		soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <AuthHeader Usr="{self.myalerts_config["username"]}"
                Pwd="{self.myalerts_config["password"]}"
                RequestID="{request_id}"
                xmlns="https://api.myusage.com/alerts/" />
  </soap:Header>
  <soap:Body>
    <GetAccountByContact xmlns="https://api.myusage.com/alerts/">
      <Contact>
        <Type>Phone</Type>
        <Value>{phone_number}</Value>
      </Contact>
    </GetAccountByContact>
  </soap:Body>
</soap:Envelope>"""

		headers = {
			"Content-Type": "text/xml; charset=utf-8",
			"SOAPAction": self.myalerts_config["soap_action"],
			"Content-Length": str(len(soap_body.encode("utf-8"))),
		}

		with self._api_call_context("MyAlerts"):
			try:
				# Use pooled session instead of new connection
				response = self.session.post(
					self.myalerts_config["url"],
					data=soap_body.encode("utf-8"),
					headers=headers,
					timeout=30,
				)

				if not response.ok:
					logging.error(f"MyAlerts API error: {response.status_code}")
					return None

				# Parse response
				root = ET.fromstring(response.content)
				for account_element in root.iter("*"):
					tag_name = account_element.tag.split("}")[-1]
					if tag_name == "Account":
						account_id = account_element.get("Id")
						if account_id:
							logging.info(f"Found AccountID: {account_id}")
							return account_id

				logging.warning("AccountID not found in MyAlerts response")
				return None

			except requests.RequestException as e:
				logging.error(f"MyAlerts request failed: {e}")
				return None
			except ET.ParseError as e:
				logging.error(f"MyAlerts XML parsing failed: {e}")
				return None

	def my_usage(self, account_id: str) -> dict[str, Any] | None:
		"""Get account usage data using connection pool"""
		request_id = str(uuid.uuid4())

		soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Header>
    <DataHeader Usr="{self.myusage_config["username"]}"
                Pwd="{self.myusage_config["password"]}"
                xmlns="http://www.exceleron.com/PAMS/Data/"
                ActionByUsr=""
                RequestID="{request_id}" />
  </soap:Header>
  <soap:Body>
    <GetAccount xmlns="http://www.exceleron.com/PAMS/Data/">
      <Request>
        <AccountID>
          <string>{account_id}</string>
        </AccountID>
        <GetUsage>true</GetUsage>
        <GetBalance>true</GetBalance>
      </Request>
    </GetAccount>
  </soap:Body>
</soap:Envelope>"""

		headers = {
			"Content-Type": "text/xml; charset=utf-8",
			"SOAPAction": self.myusage_config["soap_action"],
			"Content-Length": str(len(soap_body.encode("utf-8"))),
		}

		with self._api_call_context("MyUsage"):
			try:
				# Use pooled session
				response = self.session.post(
					self.myusage_config["url"],
					data=soap_body.encode("utf-8"),
					headers=headers,
					timeout=30,
				)

				if not response.ok:
					logging.error(f"MyUsage API error: {response.status_code}")
					logging.error(f"MyUsage error response: {response.text}")
					return None
				if os.getenv("FLASK_ENV") == "development":
					logging.info(f"MyUsage response body: {response.text}")
				return self._parse_usage_response(response.content)

			except requests.RequestException as e:
				logging.error(f"MyUsage request failed: {e}")
				return None

	def _parse_usage_response(self, xml_content: bytes) -> dict[str, Any] | None:
		"""Parse MyUsage XML response"""
		try:
			root = ET.fromstring(xml_content)
			ns = {
				"soap": "http://schemas.xmlsoap.org/soap/envelope/",
				"pams": "http://www.exceleron.com/PAMS/Data/",
			}

			account_get = root.find(".//pams:AccountGet", ns)
			if account_get is None:
				logging.warning("Could not find AccountGet in MyUsage response")
				return None

			# Extract data with null checks
			name_element = account_get.find("pams:Name", ns)
			account_name = name_element.text if name_element is not None else None

			billing_info = root.find(".//pams:BillingInfo", ns)
			if billing_info is None:
				logging.warning("Could not find BillingInfo in MyUsage response")
				return None

			balance_element = billing_info.find(".//pams:RawBalance", ns)
			balance = float(balance_element.text) if balance_element is not None and balance_element.text else 0.0

			daysleft_element = billing_info.find(".//pams:DaysLeft", ns)
			daysleft = int(daysleft_element.text) if daysleft_element is not None and daysleft_element.text else 0

			last_meter_read = root.find(".//pams:LastMeterRead", ns)
			used = 0.0
			read_date = None
			charge_amount = 0.0

			if last_meter_read is not None:
				used_element = last_meter_read.find("pams:Used", ns)
				read_date_element = last_meter_read.find("pams:ReadDate", ns)
				charge_amount_element = last_meter_read.find(".//pams:ChargeAmount", ns)

				used = float(used_element.text) if used_element is not None and used_element.text else 0.0
				read_date = read_date_element.text if read_date_element is not None else None
				charge_amount = float(charge_amount_element.text) if charge_amount_element is not None and charge_amount_element.text else 0.0

			return {
				"name": account_name,
				"balance": balance,
				"days_left": daysleft,
				"used": used,
				"read_date": read_date,
				"charge_amount": charge_amount,
			}

		except ET.ParseError as e:
			logging.error(f"Failed to parse MyUsage XML response: {e}")
			return None
		except Exception as e:
			logging.error(f"Error processing MyUsage response: {e}")
			return None

	def health_check(self) -> dict[str, Any]:
		"""Check SOAP API connectivity"""
		status = {"myalerts": "unknown", "myusage": "unknown"}

		try:
			# Test MyAlerts connectivity
			test_response = self.session.get(
				self.myalerts_config["url"].replace("/soap/alerts", ""),
				timeout=5,
			)
			status["myalerts"] = "healthy" if test_response.status_code < 500 else "unhealthy"
		except Exception:
			status["myalerts"] = "unhealthy"

		try:
			# Test MyUsage connectivity
			test_response = self.session.get(
				self.myusage_config["url"].replace("/test/2/Data", ""),
				timeout=5,
			)
			status["myusage"] = "healthy" if test_response.status_code < 500 else "unhealthy"
		except Exception:
			status["myusage"] = "unhealthy"

		return status


# Global singleton instance
soap_client = SOAPClientService()
