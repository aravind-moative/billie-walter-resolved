import logging
import time

from google.maps import addressvalidation_v1
from google.type.postal_address_pb2 import PostalAddress

# Set up logging
logger = logging.getLogger(__name__)


def validate_customer_address(address):
	# Create a client
	try:
		logger.info(f"Validating address: {address}")
		address_obj = PostalAddress(address_lines=[address])
		client = addressvalidation_v1.AddressValidationClient()

		# Initialize request argument(s)
		request = addressvalidation_v1.ValidateAddressRequest(
			address=address_obj,
		)

		# Make the request with increased timeout and retry logic
		max_retries = 10
		for attempt in range(max_retries):
			try:
				response = client.validate_address(request=request, timeout=3)
				break
			except Exception as e:
				logger.warning(f"Attempt {attempt + 1} failed: {e}")
				if attempt == max_retries - 1:
					raise
				time.sleep(2)  # Wait 2 seconds before retry

		# return response.result.verdict.address_complete
		verified = response.result.verdict.address_complete
		if verified:
			latitude = response.result.geocode.location.latitude
			longitude = response.result.geocode.location.longitude
			logger.info(f"Address verified with coordinates: {latitude}, {longitude}")
			return verified, [latitude, longitude]
		logger.warning("Address not verified")
		return verified, None
	except Exception as e:
		logger.error(f"Error validating address: {e}")
		# Return a default result instead of freezing
		return False, None


# xx2505 Delmac Dr, Dallas, TX 75233, USAxx
# xx2505 Delmac Dr, Dallas, TX 75233, USAxx
