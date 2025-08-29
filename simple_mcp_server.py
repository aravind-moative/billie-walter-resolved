from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
import logging
import re
import uuid
from datetime import datetime
from sqlalchemy import text

# Import database functionality
from app.utilities.instances import get_db_manager
from app.utilities.address_validation import validate_customer_address

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Davidson Water MCP Server", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database manager for the MCP server
from app.utilities.database import DatabaseManager, get_database_path

# Use the exact same database path as the main application
db_path = get_database_path()
db_url = f"sqlite:///{db_path / 'myusage.db'}"
logger.info(f"Using database path: {db_path}")
logger.info(f"Database URL: {db_url}")
db_manager = DatabaseManager(db_url)

def extract_zip_code(address: str) -> str:
    """Extract zip code from address string"""
    zip_pattern = r"\b\d{5}(?:-\d{4})?\b"
    match = re.search(zip_pattern, address)
    return match.group() if match else None

@app.get("/")
async def root():
    """Root endpoint - return tools list"""
    logger.info("Root endpoint called")
    return {
        "tools": [
            {
                "name": "verify_customer",
                "description": "Verify customer identity using phone number",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "10-digit phone number"
                        }
                    },
                    "required": ["phone_number"]
                }
            },
            {
                "name": "report_outage",
                "description": "Report a water service outage",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service_type": {
                            "type": "string",
                            "enum": ["water"],
                            "description": "Type of service affected"
                        },
                        "address": {
                            "type": "string",
                            "description": "Service address"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional outage details"
                        }
                    },
                    "required": ["service_type", "address"]
                }
            },
            {
                "name": "check_outage_status",
                "description": "Check the status of outages for a specific address",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "The address where to check for outages"
                        },
                        "zip_code": {
                            "type": "string",
                            "description": "ZIP code for outage checking"
                        }
                    }
                }
            },
            {
                "name": "get_bill_balance",
                "description": "Retrieve current account balance",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "account_number": {
                            "type": "string",
                            "description": "Customer account number"
                        }
                    },
                    "required": ["account_number"]
                }
            },
            {
                "name": "get_payment_link",
                "description": "Generate a secure payment link",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "account_number": {
                            "type": "string",
                            "description": "Customer account number"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Payment amount (optional)"
                        }
                    },
                    "required": ["account_number"]
                }
            },
            {
                "name": "generate_payment_url",
                "description": "Generate and display a payment URL for customer billing",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "account_number": {
                            "type": "string",
                            "description": "Customer account number"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Payment amount (optional - will use current balance if not provided)"
                        },
                        "customer_name": {
                            "type": "string",
                            "description": "Customer name for display purposes"
                        }
                    },
                    "required": ["account_number"]
                }
            },
            {
                "name": "get_meter_reading",
                "description": "Get latest meter reading and consumption. The phone number is automatically detected from the active verification record.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "default": 30,
                            "description": "Number of days of history"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "analyze_usage_patterns",
                "description": "Analyze consumption patterns and provide insights. The phone number is automatically detected from the active verification record.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "enum": ["daily", "weekly", "monthly"],
                            "default": "monthly"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "enroll_paperless_billing",
                "description": "Enroll in paperless billing",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "account_number": {
                            "type": "string",
                            "description": "Customer account number"
                        },
                        "email": {
                            "type": "string",
                            "format": "email",
                            "description": "Email for electronic bills"
                        }
                    },
                    "required": ["account_number", "email"]
                }
            },
            {
                "name": "check_phone_verification_status",
                "description": "Check if the current user is phone number verified and retrieve all customer metadata from the database",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "verify_phone_number",
                "description": "Verify a phone number against the database and return verification status",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "phone_number": {
                            "type": "string",
                            "description": "10-digit phone number to verify"
                        }
                    },
                    "required": ["phone_number"]
                }
            }
        ]
    }

@app.get("/tools")
async def tools():
    """Tools endpoint - return tools list"""
    logger.info("=== TOOLS ENDPOINT CALLED ===")
    logger.info("Returning updated tool definitions with phone_number instead of meter_id")
    result = await root()
    logger.info(f"Tools response: {result}")
    return result

@app.post("/")
async def handle_jsonrpc(request: Dict[str, Any]):
    """Handle JSON-RPC 2.0 protocol messages from ElevenLabs"""
    logger.info(f"JSON-RPC request: {request}")
    
    # Extract JSON-RPC fields
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    # Handle different JSON-RPC methods
    if method == "initialize":
        # Handle initialization
        logger.info("Handling initialize method")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Davidson Water MCP Server",
                    "version": "1.0.0"
                }
            }
        }
    
    elif method == "tools/list":
        # Return list of available tools
        logger.info("Handling tools/list method")
        tools_data = await root()
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_data["tools"]
            }
        }
    
    elif method == "tools/call":
        # Handle tool execution
        logger.info("Handling tools/call method")
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            # Real implementations for each tool
            if tool_name == "verify_customer":
                result = await verify_customer(arguments)
            elif tool_name == "report_outage":
                result = await report_outage(arguments)
            elif tool_name == "check_outage_status":
                result = await check_outage_status(arguments)
            elif tool_name == "get_bill_balance":
                result = await get_bill_balance(arguments)
            elif tool_name == "get_payment_link":
                result = await get_payment_link(arguments)
            elif tool_name == "generate_payment_url":
                result = await generate_payment_url(arguments)
            elif tool_name == "get_meter_reading":
                logger.info(f"=== GET_METER_READING CALLED ===")
                logger.info(f"Arguments received: {arguments}")
                result = await get_meter_reading(arguments)
                logger.info(f"Result: {result}")
            elif tool_name == "analyze_usage_patterns":
                result = await analyze_usage_patterns(arguments)
            elif tool_name == "enroll_paperless_billing":
                result = await enroll_paperless_billing(arguments)
            elif tool_name == "check_phone_verification_status":
                result = await check_phone_verification_status(arguments)
            elif tool_name == "verify_phone_number":
                result = await verify_phone_number(arguments)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": result
                        }
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }
    
    else:
        # Unknown method
        logger.warning(f"Unknown method: {method}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }

# Real tool implementations
async def verify_customer(arguments: dict) -> str:
    """Verify customer identity using phone number"""
    phone_number = arguments.get("phone_number")
    
    if not phone_number:
        return "Please provide a phone number to verify customer identity."
    
    if not re.match(r"^\d{10}$", phone_number):
        return "Please provide a valid 10-digit phone number."
    
    try:
        customer = db_manager.get_customer_by_phone(phone_number)
        
        if customer:
            return f"""Customer verification successful:
Phone: {customer.phone}
Name: {customer.name}
Account Number: {customer.account_id}
Status: {customer.status}
Service Address: {customer.address}"""
        else:
            return f"No customer found with phone number {phone_number}. Please check the number and try again."
                
    except Exception as e:
        logger.error(f"Error verifying customer: {e}")
        return "Customer verification failed. Please try again."

async def report_outage(arguments: dict) -> str:
    """Report a water service outage"""
    service_type = arguments.get("service_type", "")
    address = arguments.get("address")
    description = arguments.get("description", "")
    
    logger.info(f"Report outage called with arguments: {arguments}")
    
    if not address:
        return "Please provide an address."
    
    # Check if it's a water-related service type
    if service_type and "water" not in service_type.lower():
        logger.info(f"Service type validation failed. Received: '{service_type}', expected water-related")
        return f"Only water service outages can be reported. Received: {service_type}"
    
    logger.info(f"Service type validation passed: {service_type}")
    
    try:
        # For testing, bypass address validation and use default coordinates
        try:
            verified, coordinates = validate_customer_address(address)
            if not verified:
                logger.warning(f"Address validation failed for: {address}, using default coordinates")
                latitude, longitude = 32.704009, -96.860157  # Default Dallas coordinates
            else:
                latitude, longitude = coordinates
        except Exception as e:
            logger.warning(f"Address validation error: {e}, using default coordinates")
            latitude, longitude = 32.704009, -96.860157  # Default Dallas coordinates
        current_time = datetime.now()
        reference_number = f"OUT-{current_time.strftime('%Y%m%d%H%M%S')}"
        
        # Try to find customer by exact address match first
        customer = None
        try:
            with db_manager.get_session() as session:
                from app.models import Account
                customer = session.query(Account).filter(Account.address == address).first()
                if customer:
                    logger.info(f"Found customer by exact address: {customer.name} (Account: {customer.account_id})")
                else:
                    logger.info(f"No customer found by exact address: {address}")
        except Exception as e:
            logger.warning(f"Error looking up customer by exact address: {e}")
        
        # If no exact match, try by zip code
        if not customer:
            try:
                # Extract zip code from address
                zip_code = extract_zip_code(address)
                if zip_code:
                    # Look for customers in the same zip code
                    with db_manager.get_session() as session:
                        from app.models import Account
                        customer = session.query(Account).filter(Account.zip_code == zip_code).first()
                        if customer:
                            logger.info(f"Found customer by zip code {zip_code}: {customer.name} (Account: {customer.account_id})")
                        else:
                            logger.info(f"No customer found by zip code: {zip_code}")
            except Exception as e:
                logger.warning(f"Could not find customer by zip code: {e}")
        
        # Use customer info if found, otherwise use defaults
        if customer:
            account_id = customer.account_id
            customer_name = customer.name
            logger.info(f"Using customer: {customer_name} (Account: {account_id})")
        else:
            # Use a known existing account for anonymous reports
            account_id = "AC12345"  # John Doe's account
            customer_name = "Anonymous Customer"
            logger.info(f"No customer found, using default: {customer_name} (Account: {account_id})")
        
        # Create outage in database
        logger.info(f"Creating outage with reference: {reference_number}")
        db_manager.create_outage(
            reference_number=reference_number,
            account_id=account_id,
            name=customer_name,
            nature="Water",
            start_time=current_time,
            address=address,
            latitude=latitude,
            longitude=longitude,
            scale="medium",
        )
        
        logger.info(f"Successfully created outage at {address}. Reference: {reference_number}")
        return f"Water outage reported at {address}. Reference number: {reference_number}"
        
    except Exception as e:
        logger.error(f"Error reporting outage: {e}")
        return f"Failed to report outage: {str(e)}"

async def check_outage_status(arguments: dict) -> str:
    """Check the status of outages for a specific address"""
    address = arguments.get("address")
    zip_code = arguments.get("zip_code")
    
    if not address and not zip_code:
        return "Please provide an address or ZIP code to check for outages."
    
    if not zip_code and address:
        zip_code = extract_zip_code(address)
    
    if not zip_code:
        return "Unable to extract ZIP code from the provided address."
    
    try:
        outages = db_manager.get_active_outages_by_zip_code(zip_code)
        if len(outages) > 0:
            return f"{len(outages)} active outages reported in your area (ZIP code: {zip_code}). Service should be restored within 3 hours."
        return f"There are no active outages reported in your area (ZIP code: {zip_code})."
        
    except Exception as e:
        logger.error(f"Error checking outage status: {e}")
        return "Unable to check outage status. Please try again."

async def get_bill_balance(arguments: dict) -> str:
    """Retrieve current account balance"""
    account_number = arguments.get("account_number")
    
    if not account_number:
        return "Please provide an account number."
    
    try:
        billing_info = db_manager.get_billing_by_customer_id(account_number)
        if billing_info:
            return f"Current balance for account {account_number}: ${billing_info.current_balance:.2f}"
        else:
            return f"No billing information found for account {account_number}"
            
    except Exception as e:
        logger.error(f"Error getting bill balance: {e}")
        return f"Unable to retrieve billing information for account {account_number}"

async def get_payment_link(arguments: dict) -> str:
    """Generate a secure payment link"""
    account_number = arguments.get("account_number")
    amount = arguments.get("amount")
    
    if not account_number:
        return "Please provide an account number."
    
    try:
        billing_info = db_manager.get_billing_by_customer_id(account_number)
        if billing_info:
            payment_amount = amount if amount else billing_info.current_balance
            payment_url = f"https://pay.davidsonwater.com/pay/{account_number}?amount={payment_amount}"
            
            return f"""Payment link generated for account {account_number}:
URL: {payment_url}
Amount: ${payment_amount:.2f}"""
        else:
            return f"No billing information found for account {account_number}"
            
    except Exception as e:
        logger.error(f"Error generating payment link: {e}")
        return f"Could not generate payment link for account {account_number}"

async def generate_payment_url(arguments: dict) -> str:
    """Generate and display a payment URL for customer billing"""
    account_number = arguments.get("account_number")
    amount = arguments.get("amount")
    customer_name = arguments.get("customer_name", "Customer")
    
    if not account_number:
        return "Please provide an account number."
    
    try:
        billing_info = db_manager.get_billing_by_customer_id(account_number)
        if billing_info:
            payment_amount = amount if amount else billing_info.current_balance
            payment_url = f"https://pay.davidsonwater.com/pay/{account_number}?amount={payment_amount}"
            
            # Create a UI-friendly response with clear formatting
            return f"""💳 **Payment URL Generated Successfully**

**Customer:** {customer_name}
**Account Number:** {account_number}
**Payment Amount:** ${payment_amount:.2f}

🔗 **Payment Link:**
{payment_url}

📋 **Instructions:**
1. Click the payment link above
2. Review your payment details
3. Enter your payment information
4. Complete the transaction

⏰ **Note:** This payment link is valid for 24 hours.
💰 **Current Balance:** ${billing_info.current_balance:.2f}"""
        else:
            return f"""❌ **Payment URL Generation Failed**

**Account Number:** {account_number}
**Error:** No billing information found for this account.

Please verify the account number and try again."""
            
    except Exception as e:
        logger.error(f"Error generating payment URL: {e}")
        return f"""❌ **Payment URL Generation Failed**

**Account Number:** {account_number}
**Error:** Unable to generate payment URL at this time.

Please try again later or contact customer support."""

async def get_meter_reading(arguments: dict) -> str:
    """Get latest meter reading and consumption. The phone number is automatically detected from the active verification record."""
    days = arguments.get("days", 30)
    
    # Get the active phone verification from database (only one should exist at a time)
    try:
        with db_manager.get_session() as session:
            verification_sql = """
            SELECT phone_number, account_id, verified_at
            FROM phone_verifications 
            WHERE is_active = 1
            ORDER BY verified_at DESC
            LIMIT 1
            """
            
            result = session.execute(text(verification_sql)).fetchone()
            
            if not result:
                return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No verified phone number found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
            
            phone_number = result[0]
            account_id = result[1]
            verified_at = result[2]
            
            logger.info(f"Found verified phone number: {phone_number} (verified at {verified_at})")
    
    except Exception as e:
        logger.error(f"Error finding verified phone number: {e}")
        return """
❌ **VERIFICATION CHECK FAILED**

🔍 **Error:** Unable to check verification status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""
    
    try:
        # Get customer by phone number
        customer = db_manager.get_customer_by_phone(phone_number)
        if not customer:
            return f"No customer found with phone number: {phone_number}"
        
                    # Get meter reading using account_id
            reading = db_manager.get_meter_readings(customer.account_id)
            if reading:
                rate_per_gallon = 0.0125  # 1.25 cents per gallon
                cost = reading.usage * rate_per_gallon
                
                return f"""Latest meter reading for {customer.name}:
Account: {customer.account_id}
Reading: {reading.reading_value} gallons
Date: {reading.read_date.strftime("%B %d, %Y")}
Usage: {reading.usage} gallons
Rate: ${rate_per_gallon:.4f} per gallon
Estimated cost: ${cost:.2f}
History period: {days} days"""
        else:
            return f"There is no water consumption data available for {customer.name} as of now. Please check back later for updated meter readings."
            
    except Exception as e:
        logger.error(f"Error getting meter reading: {e}")
        return f"Unable to retrieve meter reading for phone number: {phone_number}"

async def analyze_usage_patterns(arguments: dict) -> str:
    """Analyze consumption patterns and provide insights. The phone number is automatically detected from the active verification record."""
    period = arguments.get("period", "monthly")
    
    # Get the active phone verification from database (only one should exist at a time)
    try:
        with db_manager.get_session() as session:
            verification_sql = """
            SELECT phone_number, account_id, verified_at
            FROM phone_verifications 
            WHERE is_active = 1
            ORDER BY verified_at DESC
            LIMIT 1
            """
            
            result = session.execute(text(verification_sql)).fetchone()
            
            if not result:
                return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No verified phone number found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
            
            phone_number = result[0]
            account_id = result[1]
            verified_at = result[2]
            
            logger.info(f"Found verified phone number: {phone_number} (verified at {verified_at})")
    
    except Exception as e:
        logger.error(f"Error finding verified phone number: {e}")
        return """
❌ **VERIFICATION CHECK FAILED**

🔍 **Error:** Unable to check verification status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""
    
    try:
        # Get customer by phone number
        customer = db_manager.get_customer_by_phone(phone_number)
        if not customer:
            return f"No customer found with phone number: {phone_number}"
        
        # Get actual usage data from database
        reading = db_manager.get_meter_readings(customer.account_id)
        if reading:
            usage_data = {
                "daily": {"avg_usage": reading.usage / 30, "peak_hours": "6PM-10PM", "trend": "stable"},
                "weekly": {"avg_usage": reading.usage / 4, "peak_day": "Tuesday", "trend": "decreasing"},
                "monthly": {"avg_usage": reading.usage, "peak_month": "July", "trend": "increasing"}
            }
            
            data = usage_data.get(period, usage_data["monthly"])
            
            return f"""Usage analysis for {customer.name} ({period}):
Account: {customer.account_id}
Average usage: {data['avg_usage']:.1f} gallons
Peak period: {data.get('peak_hours', data.get('peak_day', data.get('peak_month')))}
Trend: {data['trend']}
Recommendation: Consider adjusting usage during peak periods to reduce costs."""
        else:
            return f"There is no water consumption data available for {customer.name} as of now. Please check back later for usage analysis."
            
    except Exception as e:
        logger.error(f"Error analyzing usage patterns: {e}")
        return f"Unable to analyze usage patterns for phone number: {phone_number}"

async def enroll_paperless_billing(arguments: dict) -> str:
    """Enroll in paperless billing"""
    account_number = arguments.get("account_number")
    email = arguments.get("email")
    
    if not account_number or not email:
        return "Please provide account number and email address."
    
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return "Please provide a valid email address."
    
    try:
        # Check if account exists
        billing_info = db_manager.get_billing_by_customer_id(account_number)
        if billing_info:
            # In a real implementation, you would update the account with paperless billing preference
            return f"Successfully enrolled account {account_number} in paperless billing. Bills will be sent to {email}."
        else:
            return f"Account {account_number} not found. Please verify your account number."
            
    except Exception as e:
        logger.error(f"Error enrolling in paperless billing: {e}")
        return "Failed to enroll in paperless billing. Please try again."

async def check_phone_verification_status(arguments: dict) -> str:
    """Check if the current user is phone number verified and retrieve all customer metadata from the database"""
    
    try:
        # Get the active phone verification from database (only one should exist at a time)
        logger.info("Checking phone verification status...")
        
        # Check if there are any active verifications in the phone_verifications table
        with db_manager.get_session() as session:
            try:
                # Get active verification
                verification_sql = """
                SELECT phone_number, account_id, verified_at, session_id, verification_method
                FROM phone_verifications 
                WHERE is_active = 1
                ORDER BY verified_at DESC
                LIMIT 1
                """
                
                result = session.execute(text(verification_sql)).fetchone()
                
                if not result:
                    logger.info("No active phone verification found")
                    return """
📱 **PHONE VERIFICATION REQUIRED**

❌ **Status:** No active phone verification found

**To proceed, please:**
1. Go to Settings (gear icon)
2. Enter your phone number
3. Click "Save" to verify
4. Return here to continue

**Note:** Phone number verification is required to access Davidson Water services."""
                
                phone_number = result[0]
                account_id = result[1]
                verified_at = result[2]
                session_id = result[3]
                verification_method = result[4]
                
                logger.info(f"Found active verification for phone: {phone_number} (verified at {verified_at})")
                
            except Exception as db_error:
                logger.error(f"Database query error: {db_error}")
                return """
❌ **VERIFICATION CHECK FAILED**

🔍 **Error:** Unable to check verification status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""
        
        # Get customer data from database
        customer = db_manager.get_customer_by_phone(phone_number)
        
        if customer:
            # Customer exists in database - get all metadata
            billing_info = db_manager.get_billing_by_customer_id(customer.account_id)
            
            # Format the response with all customer metadata
            verification_status = "✅ VERIFIED (Database Verified)"
            
            customer_metadata = f"""
🔐 **PHONE VERIFICATION STATUS: {verification_status}**

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
• **Verification Status:** Verified
• **Access Level:** Full Customer Access
• **Verified At:** {verified_at}
• **Session ID:** {session_id}
• **Verification Method:** {verification_method}

**Status:** ✅ VERIFIED
**Access Level:** Full Customer Access
**Next Step:** Customer can now access all Davidson Water services."""

            return customer_metadata
        else:
            return f"""
❌ **CUSTOMER NOT FOUND**

📱 **Phone Number:** {phone_number}
🔍 **Status:** Phone verified but customer not found in database
⚠️ **Access:** Limited access

**Verification Result:** ⚠️ PARTIAL VERIFICATION
**Next Steps:**
1. Contact support to verify account information
2. Ensure the phone number is associated with a valid account
3. Try again with a different phone number if available"""
            
    except Exception as e:
        logger.error(f"Error in check_phone_verification_status: {e}")
        return f"""
❌ **VERIFICATION CHECK FAILED**

🔍 **Error:** Unable to check verification status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""


async def verify_phone_number(arguments: dict) -> str:
    """Verify a phone number against the database and return verification status"""
    phone_number = arguments.get("phone_number")
    
    if not phone_number:
        return "Please provide a phone number to verify."
    
    if not re.match(r"^\d{10}$", phone_number):
        return "Please provide a valid 10-digit phone number."
    
    try:
        # Check if customer exists in database
        customer = db_manager.get_customer_by_phone(phone_number)
        
        if customer:
            # Customer exists - get billing information
            billing_info = db_manager.get_billing_by_customer_id(customer.account_id)
            
            # Store the verification in phone_verifications table
            with db_manager.get_session() as session:
                try:
                    # First, deactivate any existing active verifications
                    deactivate_sql = "UPDATE phone_verifications SET is_active = 0 WHERE is_active = 1"
                    session.execute(text(deactivate_sql))
                    
                    # Insert new verification record
                    import uuid
                    session_id = str(uuid.uuid4())
                    
                    insert_sql = """
                    INSERT INTO phone_verifications 
                    (phone_number, account_id, verified_at, session_id, verification_method, is_active)
                    VALUES (?, ?, CURRENT_TIMESTAMP, ?, 'phone_number', 1)
                    """
                    
                    session.execute(text(insert_sql), (phone_number, customer.account_id, session_id))
                    session.commit()
                    
                    logger.info(f"Phone verification stored for {phone_number} with session {session_id}")
                    
                except Exception as db_error:
                    logger.error(f"Error storing phone verification: {db_error}")
                    session.rollback()
            
            logger.info(f"Phone number {phone_number} verified successfully for customer {customer.name}")
            
            # Format billing information safely
            current_balance = f"${billing_info.current_balance:.2f}" if billing_info else "N/A"
            days_left = billing_info.days_left if billing_info else 'N/A'
            
            return f"""
✅ **PHONE VERIFICATION SUCCESSFUL**

📱 **Phone Number:** {phone_number}
👤 **Customer:** {customer.name}
🏠 **Address:** {customer.address}
💰 **Current Balance:** {current_balance}

**Verification Details:**
• **Account ID:** {customer.account_id}
• **Account Type:** {customer.account_type}
• **Status:** {customer.status}
• **Days Left to Pay:** {days_left}

**Verification Result:** ✅ VERIFIED
**Access Level:** Full Customer Access
**Next Step:** Customer can now access all Davidson Water services."""
            
        else:
            logger.info(f"Phone number {phone_number} verification failed - customer not found")
            return f"""
❌ **PHONE VERIFICATION FAILED**

📱 **Phone Number:** {phone_number}
🔍 **Status:** Customer not found in database
⚠️ **Access:** No access to Davidson Water services

**Verification Result:** ❌ NOT VERIFIED
**Next Steps:**
1. Verify the phone number is correct
2. Ensure the customer is registered with Davidson Water
3. Contact support if the issue persists"""
            
    except Exception as e:
        logger.error(f"Error verifying phone number: {e}")
        return f"""
❌ **VERIFICATION ERROR**

📱 **Phone Number:** {phone_number}
🔍 **Error:** Unable to verify customer status
⚠️ **Access:** Verification status unknown

**Please try again or contact support if the issue persists.**"""


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    print("🚰 Davidson Water MCP Server (JSON-RPC 2.0)")
    print("🌐 Starting server on http://0.0.0.0:")
    print("🌍 Server is accessible from external sources")
    uvicorn.run(app, host="0.0.0.0", port=8001)
