import logging
import re
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from defusedxml import ElementTree
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import joinedload, sessionmaker

from app.models import (
	Account,
	AdminBase,
	AdminUser,
	Base,
	BillingInfo,
	Meter,
	Outage,
	Reading,
	Summary,
)
from app.utilities.time_utils import get_current_time


def setup_database_logging():
	"""Set up logging for database operations."""
	# Create output directory if it doesn't exist
	output_dir = Path(__file__).parent.parent / "output"
	output_dir.mkdir(parents=True, exist_ok=True)

	log_file = output_dir / "database.log"

	# Create logger
	logger = logging.getLogger("database")
	logger.setLevel(logging.DEBUG)
	logger.propagate = False  # Prevent logs from appearing in terminal

	# Remove existing handlers to avoid duplicates
	for handler in logger.handlers[:]:
		logger.removeHandler(handler)

	# Create file handler
	file_handler = logging.FileHandler(log_file)
	file_handler.setLevel(logging.DEBUG)

	# Create formatter
	formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
	file_handler.setFormatter(formatter)

	# Add handler to logger
	logger.addHandler(file_handler)

	return logger


# Initialize logger
db_logger = setup_database_logging()


# Database URLs constructed with robust path handling for both local and remote
def get_database_path():
    """Get the database path that works for both local and remote deployments"""
    # Try environment variable first
    db_path = os.getenv('DATABASE_PATH')
    if db_path:
        return Path(db_path)
    
    # Try relative to current working directory
    cwd_db_path = Path.cwd() / "app" / "databases"
    if cwd_db_path.exists():
        return cwd_db_path
    
    # Fall back to relative to this file
    file_db_path = Path(__file__).parent.parent / "databases"
    return file_db_path

DB_PATH = get_database_path()
MYUSAGE_DB_URL = f"sqlite:///{DB_PATH / 'myusage.db'}"
ADMIN_DB_URL = f"sqlite:///{DB_PATH / 'admin.db'}?check_same_thread=False"

# Log the database path for debugging
db_logger.info(f"Database path: {DB_PATH}")
db_logger.info(f"MyUsage DB URL: {MYUSAGE_DB_URL}")
db_logger.info(f"Admin DB URL: {ADMIN_DB_URL}")


class DatabaseManager:
	def __init__(
		self,
		db_url=MYUSAGE_DB_URL,
	):
		# Ensure database directory exists
		DB_PATH.mkdir(parents=True, exist_ok=True)
		
		# Configure connection pooling
		self.engine = create_engine(
			db_url,
			pool_size=20,  # Base number of connections
			max_overflow=50,  # Additional connections when needed
			pool_pre_ping=True,  # Validate connections before use
			pool_recycle=3600,  # Recycle connections every hour
			echo=False,  # Set to True for SQL debugging
		)
		Base.metadata.create_all(self.engine)
		self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

		# Initialize connection pool
		self._warm_up_pool()

	def _warm_up_pool(self):
		"""Pre-create base pool connections"""
		try:
			with self.engine.connect() as conn:
				conn.execute(text("SELECT 1")).fetchone()
			db_logger.info("Database connection pool initialized successfully")
		except Exception as e:
			db_logger.error(f"Failed to warm up connection pool: {e}")

	@contextmanager
	def get_session(self):
		"""Context manager for database sessions"""
		session = self.Session()
		try:
			yield session
			session.commit()
		except Exception as e:
			session.rollback()
			logging.error(f"Database session error: {e}")
			raise
		finally:
			session.close()

	def get_customer_by_phone(self, phone_number):
		"""Get customer using connection pool"""
		with self.get_session() as session:
			try:
				account = (
					session.query(Account)
					.filter(
						Account.phone == phone_number,
					)
					.first()
				)

				if account:
					# Ensure object is fully loaded before session closes
					session.refresh(account)

				return account
			except Exception as e:
				logging.error(f"Error querying customer by phone {phone_number}: {e}")
				return None

	def get_billing_by_customer_id(self, account_id):
		"""Get billing info using connection pool"""
		with self.get_session() as session:
			try:
				return (
					session.query(BillingInfo)
					.filter(
						BillingInfo.account_id == account_id,
					)
					.first()
				)
			except Exception as e:
				logging.error(f"Error querying billing for account {account_id}: {e}")
				return None

	def create_customer(self, name, address, account_id, phone_number):
		"""Create customer using connection pool"""
		with self.get_session() as session:
			try:
				account = Account(
					name=name,
					address=address,
					account_id=account_id,
					phone=phone_number,
					status="Active",  # Default status
				)
				session.add(account)
				# Context manager handles commit
				session.refresh(account)
				return account.account_id
			except Exception as e:
				logging.error(f"Error creating customer {account_id}: {e}")
				raise

	def create_outage(  # noqa: PLR0913
		self,
		reference_number,
		account_id,
		name,
		nature,
		start_time,
		address=None,
		latitude=None,
		longitude=None,
		scale="medium",
	):
		"""Create outage using connection pool"""
		with self.get_session() as session:
			try:
				outage = Outage(
					reference_number=reference_number,
					account_id=account_id,
					name=name,
					nature=nature,
					start_time=start_time,
					address=address,
					latitude=latitude,
					longitude=longitude,
					status="Reported",
					Scale=scale,  # Fixed: Use capital S to match model field
				)
				session.add(outage)
				# Context manager handles commit
				return outage.reference_number
			except Exception as e:
				logging.error(f"Error creating outage {reference_number}: {e}")
				raise

	def get_all_outages(self):
		"""Get all outages using connection pool"""
		with self.get_session() as session:
			try:
				return session.query(Outage).options(joinedload(Outage.account)).all()
			except Exception as e:
				logging.error(f"Error querying all outages: {e}")
				return []

	def get_active_outages_by_zip_code(self, zip_code):
		"""Get active outages by zip code using connection pool"""
		with self.get_session() as session:
			try:
				# Get all active outages and filter by zip code in Python
				all_outages = (
					session.query(Outage)
					.filter(
						Outage.status.in_(["In Progress", "Accepted", "Reported"]),
					)
					.all()
				)

				# Filter outages by zip code from address field using regex
				filtered_outages = []
				# Create regex pattern to match the zip code with word boundaries
				zip_pattern = rf"\b{re.escape(zip_code)}\b"

				for outage in all_outages:
					if outage.address and re.search(zip_pattern, outage.address):
						filtered_outages.append(outage)

				return filtered_outages
			except Exception as e:
				logging.error(f"Error querying active outages for zip code {zip_code}: {e}")
				return []

	def get_all_customers(self):
		"""Get all customers using connection pool"""
		with self.get_session() as session:
			try:
				return (
					session.query(Account)
					.options(
						joinedload(Account.billing),
						joinedload(Account.readings),
						joinedload(Account.summaries),
						joinedload(Account.meters).joinedload(Meter.readings),
					)
					.all()
				)
			except Exception as e:
				logging.error(f"Error querying all customers: {e}")
				return []

	def delete_outage(self, reference_number):
		"""Delete outage using connection pool"""
		with self.get_session() as session:
			try:
				outage = (
					session.query(Outage)
					.filter(
						Outage.reference_number == reference_number,
					)
					.first()
				)
				if outage:
					session.delete(outage)
					# Context manager handles commit
					return True
				return False
			except Exception as e:
				logging.error(f"Error deleting outage {reference_number}: {e}")
				return False

	def delete_customer(self, account_id):
		"""Delete customer and all related data using connection pool"""
		with self.get_session() as session:
			try:
				account = session.query(Account).filter(Account.account_id == account_id).first()
				if account:
					# Delete associated outages first
					session.query(Outage).filter(Outage.account_id == account_id).delete()
					# Delete associated billing
					session.query(BillingInfo).filter(
						BillingInfo.account_id == account_id,
					).delete()
					# Delete associated summaries
					session.query(Summary).filter(Summary.account_id == account_id).delete()
					# Delete associated readings and meters
					meters = session.query(Meter).filter(Meter.account_id == account_id).all()
					for meter in meters:
						session.query(Reading).filter(
							Reading.meter_number == meter.meter_number,
						).delete()
					session.query(Meter).filter(Meter.account_id == account_id).delete()
					# Delete account
					session.delete(account)
					# Context manager handles commit
					return True
				return False
			except Exception as e:
				logging.error(f"Error deleting customer {account_id}: {e}")
				return False

	def get_customer_by_account_id(self, account_id):
		"""Get customer by account ID using connection pool"""
		with self.get_session() as session:
			try:
				account = session.query(Account).filter(Account.account_id == account_id).first()
				if account:
					session.refresh(account)
				return account
			except Exception as e:
				logging.error(f"Error querying customer by account ID {account_id}: {e}")
				return None

	def get_meter_readings(self, account_id):
		"""Get the latest meter reading for an account using connection pool"""
		with self.get_session() as session:
			try:
				return session.query(Reading).filter(Reading.account_id == account_id).first()
			except Exception as e:
				logging.error(f"Error querying meter readings for {account_id}: {e}")
				return None

	def parse_and_store_account_data(self, xml_response):
		"""Parse XML response and store in myusage.db using connection pool"""
		try:
			# Parse XML
			root = ElementTree.fromstring(xml_response)
			# Navigate to AccountGet node (using proper namespace)
			ns = {
				"soap": "http://schemas.xmlsoap.org/soap/envelope/",
				"data": "http://www.exceleron.com/PAMS/Data/",
			}
			account_get = root.find(".//data:AccountGet", ns)

			with self.get_session() as session:
				# 1. Parse and create Account
				account = Account(
					account_id=account_get.get("AccountID"),
					name=account_get.find("data:Name", ns).text,
					zip_code=account_get.find("data:Zip", ns).text,
					phone=account_get.find("data:Phone", ns).text,
					account_type=account_get.find("data:Type", ns).text,
					language=account_get.find("data:Language", ns).text,
					status=account_get.find("data:Status", ns).text,
					recovery_rate=float(account_get.find("data:RecoveryRate", ns).text),
				)
				session.add(account)

				# 2. Parse and create BillingInfo
				billing_node = account_get.find("data:BillingInfo", ns)
				last_payment = billing_node.find("data:LastPayment", ns)
				last_payment_date = (
					datetime.strptime(
						last_payment.find("data:Posted", ns).text,
						"%Y-%m-%dT%H:%M:%S",
					).replace(tzinfo=timezone.utc)
					if last_payment.find("data:Posted", ns).text != "0001-01-01T00:00:00"
					else None
				)

				billing = BillingInfo(
					account_id=account.account_id,
					current_balance=float(
						billing_node.find("data:CurrentBalance", ns).text,
					),
					unpaid_debt_recovery=float(
						billing_node.find("data:UnpaidDebtRecoveryAmount", ns).text,
					),
					raw_balance=float(billing_node.find("data:RawBalance", ns).text),
					days_left=int(billing_node.find("data:DaysLeft", ns).text),
					last_payment_date=last_payment_date,
					last_payment_amount=float(
						last_payment.find("data:Amount", ns).text,
					),
				)
				session.add(billing)

				# 3. Parse and create Summary
				for summary_node in account_get.findall(".//data:ServiceSummary", ns):
					summary = Summary(
						account_id=account.account_id,
						service_type=summary_node.find("data:Service", ns).text,
						from_date=datetime.strptime(
							summary_node.find("data:From", ns).text,
							"%Y-%m-%dT%H:%M:%S.%f",
						).replace(tzinfo=timezone.utc),
						to_date=datetime.strptime(
							summary_node.find("data:To", ns).text,
							"%Y-%m-%dT%H:%M:%S.%f",
						).replace(tzinfo=timezone.utc),
						avg_use_amount=float(
							summary_node.find("data:AvgUseAmount", ns).text,
						),
						avg_use_charge=float(
							summary_node.find("data:AvgUseCharge", ns).text,
						),
					)
					session.add(summary)

				# 4. Parse and create Meters and Readings
				for meter_node in account_get.findall(".//data:MeterGet", ns):
					meter = Meter(
						meter_number=meter_node.get("MeterNumber"),
						account_id=account.account_id,
						type_mapping_code=meter_node.find(
							"data:TypeDBMappingCode",
							ns,
						).text,
						rate_mapping_code=meter_node.find(
							"data:RateDBMappingCode",
							ns,
						).text,
						service=meter_node.find("data:Service", ns).text,
						multiplier=float(meter_node.find("data:Multiplier", ns).text),
						tier1_rate=float(meter_node.find(".//data:Tier1Rate", ns).text),
					)
					session.add(meter)

					# Add last meter read
					last_meter_read = meter_node.find(".//data:LastMeterRead", ns)
					if last_meter_read is not None:
						reading = Reading(
							meter_number=meter.meter_number,
							account_id=account.account_id,
							reading_value=float(
								last_meter_read.find("data:Reading", ns).text,
							),
							read_date=datetime.strptime(
								last_meter_read.find("data:ReadDate", ns).text,
								"%Y-%m-%dT%H:%M:%S",
							).replace(tzinfo=timezone.utc),
							read_from_date=datetime.strptime(
								last_meter_read.find("data:ReadFromDate", ns).text,
								"%Y-%m-%dT%H:%M:%S",
							).replace(tzinfo=timezone.utc),
							read_type=last_meter_read.find("data:Type", ns).text,
							usage=float(last_meter_read.find("data:Used", ns).text),
							charge_amount=float(
								last_meter_read.find(".//data:ChargeAmount", ns).text,
							),
							tax_amount=float(
								last_meter_read.find(".//data:TaxAmount", ns).text,
							),
							tou_peak=float(
								last_meter_read.find("data:TOUPeak", ns).text,
							),
							tou_off_peak=float(
								last_meter_read.find("data:TOUOffPeak", ns).text,
							),
							tou_shoulder=float(
								last_meter_read.find("data:TOUShoulder", ns).text,
							),
						)
						session.add(reading)

					# Add VEE readings
					for reading_node in meter_node.findall(".//data:VEE", ns):
						reading = Reading(
							meter_number=meter.meter_number,
							reading_value=float(
								reading_node.find("data:Reading", ns).text,
							),
							read_date=datetime.strptime(
								reading_node.find("data:ReadDate", ns).text,
								"%Y-%m-%dT%H:%M:%S",
							).replace(tzinfo=timezone.utc),
							read_from_date=datetime.strptime(
								reading_node.find("data:ReadFromDate", ns).text,
								"%Y-%m-%dT%H:%M:%S",
							).replace(tzinfo=timezone.utc),
							read_type=reading_node.find("data:Type", ns).text,
							usage=float(reading_node.find("data:Used", ns).text),
							charge_amount=float(
								reading_node.find(".//data:ChargeAmount", ns).text,
							),
							tax_amount=float(
								reading_node.find(".//data:TaxAmount", ns).text,
							),
							tou_peak=float(reading_node.find("data:TOUPeak", ns).text),
							tou_off_peak=float(
								reading_node.find("data:TOUOffPeak", ns).text,
							),
							tou_shoulder=float(
								reading_node.find("data:TOUShoulder", ns).text,
							),
						)
						session.add(reading)

				# Context manager handles commit
				return account.account_id

		except Exception as e:
			logging.error(f"Error parsing and storing XML data: {e}")
			raise Exception(f"Error parsing XML: {e!s}") from e

	def get_outages_filtered(self, nature=None, time_filter=None, scale_filter=None):
		"""Get filtered outages using connection pool"""
		with self.get_session() as session:
			try:
				query = session.query(Outage).options(joinedload(Outage.account))

				if nature:
					query = query.filter(Outage.nature == nature)

				if scale_filter:
					query = query.filter(Outage.Scale == scale_filter)

				if time_filter:
					current_time = get_current_time()
					time_deltas = {
						"15m": timedelta(minutes=15),
						"30m": timedelta(minutes=30),
						"1h": timedelta(hours=1),
						"2h": timedelta(hours=2),
						"4h": timedelta(hours=4),
						"12h": timedelta(hours=12),
						"1d": timedelta(days=1),
					}

					since = current_time - time_deltas.get(time_filter, timedelta.max)

					def to_dt(ts: datetime | str) -> datetime | None:
						if isinstance(ts, datetime):
							return ts
						try:
							return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
						except Exception:
							return None

					outages = query.all()
					return [o for o in outages if (dt := to_dt(o.start_time)) and dt >= since]

				return query.all()
			except Exception as e:
				logging.error(f"Error querying filtered outages: {e}")
				return []

	def get_outage_counts_by_nature(self):
		"""Get count of outages grouped by nature type using connection pool"""
		with self.get_session() as session:
			try:
				# Query to group by nature and count occurrences
				results = (
					session.query(
						Outage.nature,
						func.count(Outage.id).label("count"),
					)
					.group_by(Outage.nature)
					.all()
				)

				# Convert to dictionary format
				counts = {}
				total = 0

				for nature, count in results:
					counts[nature] = count
					total += count

				counts["Total"] = total

				return counts
			except Exception as e:
				logging.error(f"Error querying outage counts: {e}")
				return {"Total": 0}

	def get_latest_outage_alerts(self, limit=5, nature_filter=None):
		"""Get the latest outage alerts using connection pool"""
		with self.get_session() as session:
			try:
				db_logger.debug(f"Fetching latest {limit} outage alerts with nature filter: {nature_filter}")

				# Query latest outages with account information
				query = session.query(Outage).options(joinedload(Outage.account))

				# Apply nature filter if provided
				if nature_filter:
					query = query.filter(Outage.nature == nature_filter)

				outages = query.all()

				def to_dt(ts):
					if isinstance(ts, datetime):
						return ts
					try:
						return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
					except (ValueError, TypeError):
						try:
							return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
						except (ValueError, TypeError):
							return None

				# Sort by parsed datetime
				outages.sort(key=lambda o: to_dt(o.start_time) or datetime.min, reverse=True)

				# Apply limit after sorting
				outages = outages[:limit]

				db_logger.info(f"Retrieved {len(outages)} latest alerts with nature filter: {nature_filter}")
				return outages
			except Exception as e:
				db_logger.error(f"Error in get_latest_outage_alerts: {e!s}")
				return []

	def get_connection_pool_status(self):
		"""Get connection pool health statistics"""
		try:
			pool = self.engine.pool
			return {
				"pool_size": pool.size(),
				"checked_in": pool.checkedin(),
				"checked_out": pool.checkedout(),
				"overflow": pool.overflow(),
				"invalid": pool.invalid(),
			}
		except Exception as e:
			logging.error(f"Error getting connection pool status: {e}")
			return {"error": str(e)}

	def health_check(self):
		"""Verify database connectivity and pool health"""
		try:
			with self.get_session() as session:
				session.execute(text("SELECT 1")).fetchone()
			return {"status": "healthy", "pool": self.get_connection_pool_status()}
		except Exception as e:
			return {"status": "unhealthy", "error": str(e), "pool": self.get_connection_pool_status()}

	def verify_phone_number(self, phone_number: str, session_id: str = None) -> bool:
		"""Verify a phone number and store the verification in database. Only one verification record exists at a time."""
		with self.get_session() as session:
			try:
				# First check if phone number exists in accounts
				customer = session.query(Account).filter(Account.phone == phone_number).first()
				
				if not customer:
					logging.info(f"Phone number {phone_number} not found in accounts table")
					return False
				
				# Check if already verified using raw SQL
				existing_verification = session.execute(text("""
					SELECT id FROM phone_verifications 
					WHERE phone_number = :phone_number AND is_active = 1
				"""), {"phone_number": phone_number}).fetchone()
				
				if existing_verification:
					logging.info(f"Phone number {phone_number} already verified")
					return True
				
				# IMPORTANT: Clear ALL existing verification records first
				# This ensures only one verification record exists at a time
				clear_sql = "DELETE FROM phone_verifications"
				session.execute(text(clear_sql))
				logging.info("Cleared all existing verification records")
				
				# Insert new verification record
				verification_sql = """
				INSERT INTO phone_verifications (phone_number, account_id, session_id, verified_at, verification_method, is_active)
				VALUES (:phone_number, :account_id, :session_id, CURRENT_TIMESTAMP, 'ui_verification', 1)
				"""
				session.execute(text(verification_sql), {
					"phone_number": phone_number,
					"account_id": customer.account_id,
					"session_id": session_id
				})
				
				logging.info(f"Phone number {phone_number} verified successfully for account {customer.account_id}")
				return True
				
			except Exception as e:
				logging.error(f"Error verifying phone number {phone_number}: {e}")
				return False

	def get_active_phone_verification(self) -> dict | None:
		"""Get the currently active phone verification (only one should exist at a time)"""
		with self.get_session() as session:
			try:
				# Get the most recent active verification
				verification_sql = """
				SELECT phone_number, account_id, verified_at, session_id, verification_method
				FROM phone_verifications 
				WHERE is_active = 1
				ORDER BY verified_at DESC
				LIMIT 1
				"""
				
				result = session.execute(text(verification_sql)).fetchone()
				
				if result:
					return {
						"phone_number": result[0],
						"account_id": result[1],
						"verified_at": result[2],
						"session_id": result[3],
						"verification_method": result[4]
					}
				else:
					return None
					
			except Exception as e:
				logging.error(f"Error getting active phone verification: {e}")
				return None

	def check_phone_verification_status(self, phone_number: str) -> dict:
		"""Check if a phone number is verified in the database"""
		with self.get_session() as session:
			try:
				# Check if phone number exists in accounts
				customer = session.query(Account).filter(Account.phone == phone_number).first()
				
				if not customer:
					return {
						"verified": False,
						"exists_in_db": False,
						"message": "Phone number not found in database"
					}
				
				# Check verification status
				verification_sql = """
				SELECT verified_at, session_id, verification_method
				FROM phone_verifications 
				WHERE phone_number = :phone_number AND is_active = 1
				ORDER BY verified_at DESC
				LIMIT 1
				"""
				
				result = session.execute(text(verification_sql), {"phone_number": phone_number}).fetchone()
				
				if result:
					return {
						"verified": True,
						"exists_in_db": True,
						"verified_at": result[0],
						"session_id": result[1],
						"verification_method": result[2],
						"message": "Phone number verified"
					}
				else:
					return {
						"verified": False,
						"exists_in_db": True,
						"message": "Phone number exists but not verified"
					}
					
			except Exception as e:
				logging.error(f"Error checking phone verification status for {phone_number}: {e}")
				return {
					"verified": False,
					"exists_in_db": False,
					"message": f"Error checking verification: {str(e)}"
				}

	def deactivate_phone_verification(self, phone_number: str) -> bool:
		"""Deactivate a phone number verification"""
		with self.get_session() as session:
			try:
				update_sql = """
				UPDATE phone_verifications 
				SET is_active = 0 
				WHERE phone_number = :phone_number
				"""
				result = session.execute(text(update_sql), {"phone_number": phone_number})
				session.commit()
				
				if result.rowcount > 0:
					logging.info(f"Deactivated verification for phone number {phone_number}")
					return True
				else:
					logging.info(f"No active verification found for phone number {phone_number}")
					return False
					
			except Exception as e:
				logging.error(f"Error deactivating phone verification for {phone_number}: {e}")
				return False

	def clear_phone_verifications_by_session(self, session_id: str) -> bool:
		"""Clear phone verification records for a specific session"""
		with self.get_session() as session:
			try:
				delete_sql = """
				DELETE FROM phone_verifications 
				WHERE session_id = :session_id
				"""
				result = session.execute(text(delete_sql), {"session_id": session_id})
				session.commit()
				
				if result.rowcount > 0:
					logging.info(f"Cleared {result.rowcount} phone verification records for session {session_id}")
					return True
				else:
					logging.info(f"No phone verification records found for session {session_id}")
					return False
					
			except Exception as e:
				logging.error(f"Error clearing phone verifications for session {session_id}: {e}")
				return False

	def clear_all_phone_verifications(self) -> bool:
		"""Clear all phone verification records - called when browser tab closes"""
		with self.get_session() as session:
			try:
				delete_sql = "DELETE FROM phone_verifications"
				result = session.execute(text(delete_sql))
				session.commit()
				
				logging.info(f"Cleared all phone verification records ({result.rowcount} records)")
				return True
					
			except Exception as e:
				logging.error(f"Error clearing all phone verifications: {e}")
				return False


class AdminDatabaseManager:
	def __init__(
		self,
		db_url=ADMIN_DB_URL,
	):
		# Ensure database directory exists
		DB_PATH.mkdir(parents=True, exist_ok=True)
		
		# Configure connection pooling for admin database
		self.engine = create_engine(
			db_url,
			pool_size=10,  # Smaller pool for admin operations
			max_overflow=20,  # Smaller overflow for admin
			pool_pre_ping=True,  # Validate connections before use
			pool_recycle=3600,  # Recycle connections every hour
			echo=False,  # Set to True for SQL debugging
		)
		AdminBase.metadata.create_all(self.engine)
		self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

		# Initialize admin connection pool
		self._warm_up_pool()

	def _warm_up_pool(self):
		"""Pre-create base pool connections for admin database"""
		try:
			with self.engine.connect() as conn:
				conn.execute(text("SELECT 1")).fetchone()
			logging.info("Admin database connection pool initialized successfully")
		except Exception as e:
			logging.error(f"Failed to warm up admin connection pool: {e}")

	@contextmanager
	def get_session(self):
		"""Context manager for admin database sessions"""
		session = self.Session()
		try:
			yield session
			session.commit()
		except Exception as e:
			session.rollback()
			logging.error(f"Admin database session error: {e}")
			raise
		finally:
			session.close()

	def create_admin(self, email, password, name):
		"""Create a new admin user with a hashed password using connection pool"""
		with self.get_session() as session:
			try:
				# Check if admin already exists
				existing_admin = session.query(AdminUser).filter(AdminUser.email == email).first()
				if existing_admin:
					return None

				admin = AdminUser(email=email, name=name)
				admin.set_password(password)
				session.add(admin)
				# Context manager handles commit
				session.refresh(admin)
				return admin
			except Exception as e:
				logging.error(f"Error creating admin {email}: {e}")
				return None

	def get_admin_by_email(self, email):
		"""Get an admin by their email address using connection pool"""
		with self.get_session() as session:
			try:
				return session.query(AdminUser).filter(AdminUser.email == email).first()
			except Exception as e:
				logging.error(f"Error querying admin by email {email}: {e}")
				return None

	def update_last_login(self, admin_id):
		"""Update the last login timestamp for an admin using connection pool"""
		with self.get_session() as session:
			try:
				admin = session.query(AdminUser).filter(AdminUser.id == admin_id).first()
				if admin:
					admin.last_login = datetime.now(timezone.utc)
					# Context manager handles commit
					return True
				return False
			except Exception as e:
				logging.error(f"Error updating last login for admin {admin_id}: {e}")
				return False

	def delete_admin(self, email):
		"""Delete an admin by their email address using connection pool"""
		with self.get_session() as session:
			try:
				admin = session.query(AdminUser).filter(AdminUser.email == email).first()
				if admin:
					session.delete(admin)
					# Context manager handles commit
					return True
				return False
			except Exception as e:
				logging.error(f"Error deleting admin {email}: {e}")
				return False

	def get_all_admins(self):
		"""Get all admin users from the database using connection pool"""
		with self.get_session() as session:
			try:
				return session.query(AdminUser).all()
			except Exception as e:
				logging.error(f"Error querying all admins: {e}")
				return []

	def get_connection_pool_status(self):
		"""Get admin connection pool health statistics"""
		try:
			pool = self.engine.pool
			return {
				"pool_size": pool.size(),
				"checked_in": pool.checkedin(),
				"checked_out": pool.checkedout(),
				"overflow": pool.overflow(),
				"invalid": pool.invalid(),
			}
		except Exception as e:
			logging.error(f"Error getting admin connection pool status: {e}")
			return {"error": str(e)}

	def health_check(self):
		"""Verify admin database connectivity and pool health"""
		try:
			with self.get_session() as session:
				session.execute(text("SELECT 1")).fetchone()
			return {"status": "healthy", "pool": self.get_connection_pool_status()}
		except Exception as e:
			return {"status": "unhealthy", "error": str(e), "pool": self.get_connection_pool_status()}
