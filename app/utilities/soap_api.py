# import logging
# import os
# import uuid
# import xml.etree.ElementTree as ET

# import requests
# from dotenv import load_dotenv

# # --- Configuration ---
# load_dotenv()

# # --- MyAlerts API Configuration ---
# MYALERTS_API_USERNAME = os.getenv("MYALERTS_USER")
# MYALERTS_API_PASSWORD = os.getenv("MYALERTS_PWD")
# MYALERTS_URL = "https://testv3.myusage.com/v3/soap/alerts"
# MYALERTS_SOAP_ACTION = "GetAccountByContact"

# # --- MyUsage API Configuration ---
# MYUSAGE_API_USERNAME = os.getenv("MYUSAGE_USER")
# MYUSAGE_API_PASSWORD = os.getenv("MYUSAGE_PWD")
# MYUSAGE_URL = "https://api.myusage.com/test/2/Data"
# MYUSAGE_SOAP_ACTION = "http://www.exceleron.com/PAMS/Data/GetAccount"


# def my_alerts(phone_number: str) -> str | None:
# 	"""Builds and sends the SOAP request to the GetAccount endpoint (MyAlerts).

# 	Args:
# 	    phone_number: The customer's phone number to verify.

# 	Returns:
# 	    The AccountID if found, otherwise None.
# 	"""
# 	request_id = str(uuid.uuid4())
# 	soap_request_body = f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
# <soap:Envelope xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\">
#   <soap:Header>
#     <AuthHeader Usr=\"{MYALERTS_API_USERNAME}\" Pwd=\"{MYALERTS_API_PASSWORD}\" RequestID=\"{request_id}\" xmlns=\"https://api.myusage.com/alerts/\" />
#   </soap:Header>
#   <soap:Body>
#     <GetAccountByContact xmlns=\"https://api.myusage.com/alerts/\">
#       <Contact>
#         <Type>Phone</Type>
#         <Value>{phone_number}</Value>
#       </Contact>
#     </GetAccountByContact>
#   </soap:Body>
# </soap:Envelope>"""
# 	soap_request_body_bytes = soap_request_body.encode("utf-8")
# 	headers = {
# 		"Content-Type": "text/xml; charset=utf-8",
# 		"SOAPAction": MYALERTS_SOAP_ACTION,
# 		"Content-Length": str(len(soap_request_body_bytes)),
# 	}
# 	try:
# 		logging.info(f"Sending SOAP request to MyAlerts API to validate {phone_number}.")
# 		with requests.post(
# 			MYALERTS_URL,
# 			data=soap_request_body_bytes,
# 			headers=headers,
# 			timeout=30,
# 			stream=True,
# 		) as response:
# 			if not response.ok:
# 				logging.error(f"Server returned an error: {response.status_code}")
# 				return None
# 			logging.info("Received response from MyAlerts API")

# 			parser = ET.XMLPullParser(["end"])
# 			for chunk in response.iter_content(chunk_size=1024):
# 				parser.feed(chunk)
# 				for _, elem in parser.read_events():
# 					if elem.tag.endswith("}Account"):
# 						account_id = elem.get("Id")
# 						if account_id:
# 							logging.info(f"Found AccountID: {account_id}")
# 							return account_id
# 						elem.clear()

# 		logging.warning("AccountID not found in the response.")
# 		return None
# 	except requests.exceptions.RequestException as e:
# 		logging.error(f"An error occurred during the HTTP request: {e}", exc_info=True)
# 		return None
# 	except ET.ParseError as e:
# 		logging.error(f"Failed to parse XML response: {e}", exc_info=True)
# 		return None


# def my_usage(account_id):
# 	"""Builds and sends the SOAP request to the GetAccount endpoint (MyUsage)."""
# 	request_id = str(uuid.uuid4())
# 	# usage_to = datetime.now()
# 	# usage_from = usage_to - timedelta(days=10)
# 	logging.info("Step 1: Building the SOAP XML payload.")
# 	soap_request_body = f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
# <soap:Envelope xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\">
#   <soap:Header>
#     <DataHeader Usr=\"{MYUSAGE_API_USERNAME}\" Pwd=\"{MYUSAGE_API_PASSWORD}\" xmlns=\"http://www.exceleron.com/PAMS/Data/\" ActionByUsr=\"\" RequestID=\"{request_id}\"  />
#   </soap:Header>
#   <soap:Body>
#     <GetAccount xmlns=\"http://www.exceleron.com/PAMS/Data/\">
#       <Request>
#         <AccountID>
#           <string>{account_id}</string>
#         </AccountID>
#         <GetUsage>true</GetUsage>
#         <GetBalance>true</GetBalance>
#       </Request>
#     </GetAccount>
#   </soap:Body>
# </soap:Envelope>"""
# 	soap_request_body_bytes = soap_request_body.encode("utf-8")
# 	headers = {
# 		"Content-Type": "text/xml; charset=utf-8",
# 		"SOAPAction": MYUSAGE_SOAP_ACTION,
# 		"Content-Length": str(len(soap_request_body_bytes)),
# 	}
# 	try:
# 		with requests.post(
# 			MYUSAGE_URL,
# 			data=soap_request_body_bytes,
# 			headers=headers,
# 			timeout=30,
# 			stream=True,
# 		) as response:
# 			logging.info(f"Response: {response.ok}")
# 			if not response.ok:
# 				logging.error(f"Response: {response.content}")
# 				logging.error(f"The server returned an error: {response.status_code}")
# 				logging.error(f"Response body: {response.text}")
# 				return None

# 			# Use a pull parser for memory efficiency
# 			parser = ET.XMLPullParser(["end"])
# 			data = {}
# 			ns_prefix = "{http://www.exceleron.com/PAMS/Data/}"

# 			for chunk in response.iter_content(chunk_size=1024):
# 				parser.feed(chunk)
# 				for _, elem in parser.read_events():
# 					tag = elem.tag.replace(ns_prefix, "")
# 					if tag == "Name":
# 						data["name"] = elem.text
# 					elif tag == "CurrentBalance":
# 						data["balance"] = float(elem.text) if elem.text is not None else None
# 					elif tag == "DaysLeft":
# 						data["days_left"] = int(elem.text) if elem.text is not None else None
# 					elif tag == "Used":
# 						data["used"] = float(elem.text) if elem.text is not None else None
# 					elif tag == "ReadDate":
# 						data["read_date"] = elem.text
# 					elif tag == "ChargeAmount":
# 						data["charge_amount"] = float(elem.text) if elem.text is not None else None

# 					# Clear the element to free memory
# 					elem.clear()

# 		logging.info(f"Account Name: {data.get('name')}")
# 		logging.info(f"Balance: {data.get('balance')}")
# 		logging.info(f"Days Left: {data.get('days_left')}")
# 		logging.info(f"Used: {data.get('used')}")
# 		logging.info(f"ReadDate: {data.get('read_date')}")
# 		logging.info(f"ChargeAmount: {data.get('charge_amount')}")

# 		return data

# 	except requests.exceptions.RequestException as e:
# 		logging.error(f"An error occurred during the HTTP request: {e}")
# 		return None
# 	except (ET.ParseError, KeyError) as e:
# 		logging.error(f"Failed to parse XML response or find key: {e}")
# 		return None

from app.utilities.soap_client import soap_client


def my_alerts(phone_number: str):
	"""Wrapper for backward compatibility"""
	return soap_client.my_alerts(phone_number)


def my_usage(account_id: str):
	"""Wrapper for backward compatibility"""
	return soap_client.my_usage(account_id)
