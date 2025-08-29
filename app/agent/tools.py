import logging
import re
import uuid
from datetime import datetime
from typing import Annotated

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.utilities.address_validation import validate_customer_address
from app.utilities.instances import get_db_manager

from .prompts import extract_address_prompt, get_time_extraction_prompt


@tool
def report_outage(
	start_time: str,
	state: Annotated[dict, InjectedState],
	address: str | None = None,
	address_type: str | None = None,
) -> str:
	"""Report a utility outage

	Args:
	    start_time: The time the outage started - this may be a time like "3 hours ago" or "yesterday" or "2 days ago"
	    address: The address of the outage
	    address_type: The type of address - must be one of: "registered" or "new"
	"""
	llm = state.get("llm")
	db_manager = get_db_manager()
	local_data = state.get("local_data")
	account_id = state.get("account_id")
	name = state.get("customer_name")
	if address is not None:
		prompt = extract_address_prompt(address)
		address_string = llm.invoke(prompt).content.strip()
	elif address_type == "registered" and local_data:
		address_string = state.get("registered_address")
	elif (address_type == "registered" and not local_data) or (address_type == "new"):
		return "Please provide the address where the outage is occurring."
	else:
		return "Do you want to use your registered address or a different address?"
	verified, coordinates = validate_customer_address(address_string)
	if verified:
		latitude = coordinates[0]
		longitude = coordinates[1]
	else:
		return "Please provide a valid address."
	current_time = datetime(2025, 7, 3, 8, 0, 0).strftime("%Y-%m-%dT%H:%M:%S")
	time_prompt = get_time_extraction_prompt(start_time, current_time)
	extracted_time = llm.invoke(time_prompt).content.strip()
	if extracted_time == "absent":
		return "Could not determine the outage start time. Please provide a clear time reference."
	start_time_dt = datetime.fromisoformat(extracted_time)
	reference_number = f"OUT-{uuid.uuid4()}"
	reference_number = db_manager.create_outage(
		reference_number=reference_number,
		name=name,
		account_id=account_id,
		nature="Water",
		start_time=start_time_dt,
		address=address_string,
		latitude=latitude,
		longitude=longitude,
		scale="medium",
	)
	logging.info(f"Reporting at {address_string}. Start time: {start_time_dt}")
	return f"Reported at {address_string}. Start time: {start_time_dt}\nReference number: {reference_number}"


def extract_zip_code(address: str) -> str | None:
	"""Extract zip code from address string"""
	# Common zip code patterns: 5 digits or 5+4 format
	zip_pattern = r"\b\d{5}(?:-\d{4})?\b"
	match = re.search(zip_pattern, address)
	return match.group() if match else None


@tool
def check_outage_status(
	state: Annotated[dict, InjectedState],
	address: str | None = None,
	address_type: str | None = None,
) -> str:
	"""Check the status of outages for a specific address.

	Args:
	    address: The address where to check for outages
	    address_type: The type of address - must be one of: "registered" or "new"
	"""
	db_manager = get_db_manager()
	llm = state.get("llm")
	local_data = state.get("local_data")
	if address is not None:
		prompt = extract_address_prompt(address)
		address_string = llm.invoke(prompt).content.strip()
	elif address_type == "registered" and local_data:
		address_string = state.get("registered_address")
	elif (address_type == "registered" and not local_data) or (address_type == "new"):
		return "Please provide the address where the outage is occurring."
	else:
		return "Do you want to use your registered address or a different address?"

	# Extract zip code from address
	zip_code = extract_zip_code(address_string)
	if not zip_code:
		return "Unable to extract zip code from the provided address. Please provide a valid address with zip code."

	# Get outages by zip code
	outages = db_manager.get_active_outages_by_zip_code(zip_code)
	if len(outages) > 0:
		return f"{len(outages)} active outages reported in your area (zip code: {zip_code}). Service should be restored within 3 hours."
	return f"There are no active outages reported in your area (zip code: {zip_code})."


@tool
def get_meter_reading(state: Annotated[dict, InjectedState]) -> str:
	"""Get the latest meter reading for an account. The phone number is automatically detected from the active verification record."""
	db_manager = get_db_manager()
	
	# Get the active phone verification from database (only one should exist at a time)
	active_verification = db_manager.get_active_phone_verification()
	
	if not active_verification:
		return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No active phone verification found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
	
	# Get the verified phone number from the active verification
	phone_number = active_verification["phone_number"]
	
	# Get customer by phone number
	customer = db_manager.get_customer_by_phone(phone_number)
	if not customer:
		return f"No customer found with phone number: {phone_number}. Please check the number and try again."
	
	# Get meter reading for the customer's account
	reading = db_manager.get_meter_readings(customer.account_id)
	if not reading:
		return f"There is no water consumption data available for {customer.name} as of now. Please check back later for updated meter readings."
	
	rate_per_gallon = 0.0125  # 1.25 cents per gallon
	cost = reading.usage * rate_per_gallon
	
	return f"""Latest meter reading for {customer.name}:
Account: {customer.account_id}
Reading: {reading.reading_value} gallons
Reading date: {reading.read_date.strftime("%B %d, %Y")}
Rate: ${rate_per_gallon:.4f} per gallon
Estimated cost: ${cost:.2f}"""


@tool
def enroll_paperless_billing() -> str:
	"""Enroll a customer in paperless billing."""
	return "Could not enroll in paperless billing. Please try again later."


@tool
def get_bill_balance(state: Annotated[dict, InjectedState]) -> str:
	"""Check the current bill balance."""
	local_data = state.get("local_data")
	if local_data:
		db_manager = get_db_manager()
		account_id = state.get("account_id")
		customer_name = state.get("customer_name")
		billing_info = db_manager.get_billing_by_customer_id(account_id)
		return f"Raw balance: ${billing_info.current_balance:.2f}\nCustomer: {customer_name}"
	elif not local_data:
		balance = state.get("balance")
		return f"Raw balance: ${balance:.2f}"
	else:
		return "No billing information found"


@tool
def get_payment_link(state: Annotated[dict, InjectedState]) -> str:
	"""Generate a payment link for the customer's Raw balance."""
	local_data = state.get("local_data")
	account_id = state.get("account_id")
	if local_data:
		db_manager = get_db_manager()
		billing_info = db_manager.get_billing_by_customer_id(account_id)
		payment_url = f"https://pay.acmeutilities.com/pay/{account_id}?amount={billing_info.current_balance}"
		return f"Payment link: {payment_url}\nAmount due: ${billing_info.current_balance:.2f}"
	elif not local_data:
		balance = state.get("balance")
		payment_url = f"https://pay.acmeutilities.com/pay/{account_id}?amount={balance}"
		return f"Payment link: {payment_url}\nAmount due: ${balance:.2f}"
	return "No billing information found"


@tool
def analyze_usage_patterns(state: Annotated[dict, InjectedState]) -> str:
	"""Analyze utility usage patterns for the customer. The phone number is automatically detected from the active verification record."""
	db_manager = get_db_manager()
	
	# Get the active phone verification from database (only one should exist at a time)
	active_verification = db_manager.get_active_phone_verification()
	
	if not active_verification:
		return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No active phone verification found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
	
	# Get the verified phone number from the active verification
	phone_number = active_verification["phone_number"]
	
	# Get customer by phone number
	customer = db_manager.get_customer_by_phone(phone_number)
	if not customer:
		return f"No customer found with phone number: {phone_number}. Please check the number and try again."
	
	# Get meter reading for the customer's account
	reading = db_manager.get_meter_readings(customer.account_id)
	if reading:
		usage_data = {
			"daily": {"avg_usage": reading.usage / 30, "peak_hours": "6PM-10PM", "trend": "stable"},
			"weekly": {"avg_usage": reading.usage / 4, "peak_day": "Tuesday", "trend": "decreasing"},
			"monthly": {"avg_usage": reading.usage, "peak_month": "July", "trend": "increasing"}
		}
		
		return f"""Usage analysis for {customer.name}:
Account: {customer.account_id}
Average daily usage: {usage_data['daily']['avg_usage']:.1f} gallons
Average weekly usage: {usage_data['weekly']['avg_usage']:.1f} gallons
Monthly usage: {usage_data['monthly']['avg_usage']:.1f} gallons
Peak usage hours: {usage_data['daily']['peak_hours']}
Trend: {usage_data['monthly']['trend']}
Recommendation: Consider adjusting usage during peak periods to reduce costs."""
	else:
		return f"There is no water consumption data available for {customer.name} as of now. Please check back later for usage analysis."
		reading = db_manager.get_meter_readings(account_id)
		if reading:
			usage_data = {
				"daily": {"avg_usage": reading.usage / 30, "peak_hours": "6PM-10PM", "trend": "stable"},
				"weekly": {"avg_usage": reading.usage / 4, "peak_day": "Tuesday", "trend": "decreasing"},
				"monthly": {"avg_usage": reading.usage, "peak_month": "July", "trend": "increasing"}
			}
			
			return f"""Usage analysis for {customer_name}:
Account: {account_id}
Average daily usage: {usage_data['daily']['avg_usage']:.1f} gallons
Average weekly usage: {usage_data['weekly']['avg_usage']:.1f} gallons
Monthly usage: {usage_data['monthly']['avg_usage']:.1f} gallons
Peak usage hours: {usage_data['daily']['peak_hours']}
Trend: {usage_data['monthly']['trend']}
Recommendation: Consider adjusting usage during peak periods to reduce costs."""



@tool
def check_phone_verification_status(state: Annotated[dict, InjectedState]) -> str:
	"""Check if the current user is phone number verified and retrieve all customer metadata from the database. The phone number is automatically detected from the active verification record."""
	
	# Get the active phone verification from database (only one should exist at a time)
	db_manager = get_db_manager()
	active_verification = db_manager.get_active_phone_verification()
	
	if not active_verification:
		return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No active phone verification found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
	
	# Get the verified phone number from the active verification
	phone_number = active_verification["phone_number"]
	
	# Check verification status in database
	verification_status = db_manager.check_phone_verification_status(phone_number)
	
	try:
		# Check if customer exists in database
		customer = db_manager.get_customer_by_phone(phone_number)
		
		if customer:
			# Customer exists in database - get all metadata
			billing_info = db_manager.get_billing_by_customer_id(customer.account_id)
			
			# Determine verification status based on database verification
			if verification_status["verified"]:
				verification_status_text = "✅ VERIFIED (Database Verified)"
				verification_note = f"This customer has been verified through phone number authentication on {verification_status['verified_at']}."
			else:
				verification_status_text = "⚠️ DATABASE MATCH (Not Verified)"
				verification_note = f"""
This customer exists in our database but has not completed phone number verification.

**To verify this phone number:**
1. Go to Settings (gear icon)
2. Enter phone number: {phone_number}
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
			
			customer_metadata = f"""
🔐 **PHONE VERIFICATION STATUS: {verification_status_text}**

👤 **CUSTOMER INFORMATION:**
• **Name:** {customer.name}
• **Phone Number:** {customer.phone}
• **Account ID:** {customer.account_id}
• **Account Type:** {customer.account_type}
• **Status:** {customer.status}
• **Language:** {customer.language}
• **Recovery Rate:** {customer.recovery_rate}
• **Tax Jurisdiction:** {customer.tax_jurisdiction_mapping_code}

📍 **ADDRESS INFORMATION:**
• **Full Address:** {customer.address}
• **ZIP Code:** {customer.zip_code}

💰 **BILLING INFORMATION:"""
			
			if billing_info:
				last_payment_amount = f"${billing_info.last_payment_amount:.2f}" if billing_info.last_payment_amount else "$0.00"
				last_payment_date = billing_info.last_payment_date.strftime('%B %d, %Y') if billing_info.last_payment_date else 'No previous payments'
				customer_metadata += f"""
• **Current Balance:** ${billing_info.current_balance:.2f}
• **Raw Balance:** ${billing_info.raw_balance:.2f}
• **Unpaid Debt Recovery:** ${billing_info.unpaid_debt_recovery:.2f}
• **Days Left to Pay:** {billing_info.days_left}
• **Last Payment Date:** {last_payment_date}
• **Last Payment Amount:** {last_payment_amount}"""
			else:
				customer_metadata += f"""
• **Billing Status:** No billing information available"""

			customer_metadata += f"""

📅 **ACCOUNT DETAILS:**
• **Created:** {customer.created_at.strftime('%B %d, %Y at %I:%M %p')}
• **Verification Method:** Phone Number Authentication
• **Verification Status:** {'Verified' if verification_status["verified"] else 'Not Verified'}
• **Access Level:** {'Full Customer Access' if verification_status["verified"] else 'Limited Access (Verification Required)'}

{verification_note}"""
			
			return customer_metadata
			
		else:
			# Customer not found in database
			return f"""
❌ **PHONE VERIFICATION STATUS: NOT VERIFIED**

📱 **Phone Number:** {phone_number}
🔍 **Status:** Customer not found in database
⚠️ **Access:** No access to Davidson Water services

**Possible Solutions:**
1. **Check the phone number** - Make sure it's correct (10 digits)
2. **Contact Support** - If you believe this number should be registered
3. **Try a different number** - If you have multiple phone numbers

**Note:** Only customers registered with Davidson Water can access our services."""
			
	except Exception as e:
		logging.error(f"Error checking phone verification status: {e}")
		return f"""
❌ **VERIFICATION CHECK FAILED**

📱 **Phone Number:** {phone_number}
🔍 **Error:** Unable to verify customer status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""


@tool
def verify_phone_number(phone_number: str, state: Annotated[dict, InjectedState]) -> str:
	"""Verify a phone number against the database and return verification status."""
	
	if not phone_number:
		return "Please provide a phone number to verify."
	
	# Validate phone number format
	import re
	if not re.match(r"^\d{10}$", phone_number):
		return "Please provide a valid 10-digit phone number."
	
	try:
		db_manager = get_db_manager()
		
		# Verify the phone number in the database
		verification_success = db_manager.verify_phone_number(phone_number)
		
		if verification_success:
			# Get customer and billing information
			customer = db_manager.get_customer_by_phone(phone_number)
			billing_info = db_manager.get_billing_by_customer_id(customer.account_id)
			
			logging.info(f"Phone number {phone_number} verified successfully for customer {customer.name}")
			return f"""
✅ **PHONE VERIFICATION SUCCESSFUL**

📱 **Phone Number:** {phone_number}
👤 **Customer:** {customer.name}
🏠 **Address:** {customer.address}
💰 **Current Balance:** ${billing_info.current_balance:.2f if billing_info else 'N/A'}

**Verification Details:**
• **Account ID:** {customer.account_id}
• **Account Type:** {customer.account_type}
• **Status:** {customer.status}
• **Days Left to Pay:** {billing_info.days_left if billing_info else 'N/A'}

**Verification Result:** ✅ VERIFIED
**Access Level:** Full Customer Access
**Next Step:** Customer can now access all Davidson Water services."""
			
		else:
			logging.info(f"Phone number {phone_number} verification failed")
			return f"""
❌ **PHONE VERIFICATION FAILED**

📱 **Phone Number:** {phone_number}
🔍 **Status:** Verification failed
⚠️ **Access:** No access to Davidson Water services

**Verification Result:** ❌ NOT VERIFIED
**Next Steps:**
1. Verify the phone number is correct
2. Ensure the customer is registered with Davidson Water
3. Contact support if the issue persists"""
			
	except Exception as e:
		logging.error(f"Error verifying phone number: {e}")
		return f"""
❌ **VERIFICATION ERROR**

📱 **Phone Number:** {phone_number}
🔍 **Error:** Unable to verify customer status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""
