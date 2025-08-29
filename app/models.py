import bcrypt
from sqlalchemy import (
	Column,
	DateTime,
	Float,
	ForeignKey,
	Integer,
	String,
	Text,
	create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from app.utilities.time_utils import get_current_time

Base = declarative_base()
AdminBase = declarative_base()  # New base for admin database


class AdminUser(AdminBase):
	__tablename__ = "admin_users"

	id = Column(Integer, primary_key=True)
	email = Column(String(120), unique=True, nullable=False)
	password_hash = Column(String(128), nullable=False)
	name = Column(String(100), nullable=False)
	created_at = Column(DateTime, default=get_current_time)
	last_login = Column(DateTime)

	def set_password(self, password):
		"""Hash and set the admin's password."""
		salt = bcrypt.gensalt()
		self.password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode(
			"utf-8",
		)

	def check_password(self, password):
		"""Check if the provided password matches the stored hash."""
		return bcrypt.checkpw(
			password.encode("utf-8"),
			self.password_hash.encode("utf-8"),
		)


class Account(Base):
	__tablename__ = "accounts"

	account_id = Column(String, primary_key=True)
	name = Column(String)
	address = Column(String)
	zip_code = Column(String)
	phone = Column(String)
	account_type = Column(String)
	language = Column(String)
	status = Column(String)
	recovery_rate = Column(Float)
	tax_jurisdiction_mapping_code = Column(String)
	created_at = Column(DateTime, default=get_current_time)

	# Relationships
	billing = relationship("BillingInfo", back_populates="account", uselist=False)
	summaries = relationship("Summary", back_populates="account")
	meters = relationship("Meter", back_populates="account")
	outages = relationship("Outage", back_populates="account")
	readings = relationship("Reading", back_populates="account")


class BillingInfo(Base):
	__tablename__ = "billing_info"

	id = Column(Integer, primary_key=True)
	account_id = Column(String, ForeignKey("accounts.account_id"))
	current_balance = Column(Float)
	unpaid_debt_recovery = Column(Float)
	raw_balance = Column(Float)
	days_left = Column(Integer)
	last_payment_date = Column(DateTime, nullable=True)
	last_payment_amount = Column(Float, nullable=True)

	# Relationship
	account = relationship("Account", back_populates="billing")


class Summary(Base):
	__tablename__ = "summaries"

	id = Column(Integer, primary_key=True)
	account_id = Column(String, ForeignKey("accounts.account_id"))
	service_type = Column(String)
	from_date = Column(DateTime)
	to_date = Column(DateTime)
	avg_use_amount = Column(Float)
	avg_use_charge = Column(Float)

	# Relationship
	account = relationship("Account", back_populates="summaries")


class Meter(Base):
	__tablename__ = "meters"

	meter_number = Column(String, primary_key=True)
	account_id = Column(String, ForeignKey("accounts.account_id"))
	type_mapping_code = Column(String)
	rate_mapping_code = Column(String)
	service = Column(String)
	multiplier = Column(Float)
	tier1_rate = Column(Float)
	last_disconnect = Column(DateTime, nullable=True)

	# Relationships
	account = relationship("Account", back_populates="meters")
	readings = relationship("Reading", back_populates="meter")


class Reading(Base):
	__tablename__ = "readings"

	id = Column(Integer, primary_key=True)
	meter_number = Column(String, ForeignKey("meters.meter_number"))
	account_id = Column(String, ForeignKey("accounts.account_id"))
	reading_value = Column(Float)
	read_date = Column(DateTime)
	read_from_date = Column(DateTime)
	read_type = Column(String)
	usage = Column(Float)
	charge_amount = Column(Float)
	tax_amount = Column(Float)
	tou_peak = Column(Float, nullable=True)
	tou_off_peak = Column(Float, nullable=True)
	tou_shoulder = Column(Float, nullable=True)

	# Relationships
	meter = relationship("Meter", back_populates="readings")
	account = relationship("Account", back_populates="readings")


class Outage(Base):
	__tablename__ = "outages"

	id = Column(Integer, primary_key=True)
	account_id = Column(String, ForeignKey("accounts.account_id"))
	name = Column(String)
	reference_number = Column(String, unique=True, nullable=False)
	address = Column(String(200))
	nature = Column(Text)
	start_time = Column(DateTime, nullable=False)
	end_time = Column(DateTime, nullable=True)
	status = Column(String(20), default="reported")  # reported, in_progress, resolved
	Scale = Column(Text, nullable=True)
	latitude = Column(Float, nullable=True)
	longitude = Column(Float, nullable=True)
	created_at = Column(DateTime, default=get_current_time)
	updated_at = Column(
		DateTime,
		default=get_current_time,
		onupdate=get_current_time,
	)

	# Relationship
	account = relationship("Account", back_populates="outages")


# Database setup function
def init_db(db_url="sqlite:///myusage.db?check_same_thread=False"):
	engine = create_engine(db_url)
	Base.metadata.create_all(engine)
	return engine
