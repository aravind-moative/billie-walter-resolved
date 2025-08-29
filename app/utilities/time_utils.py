from datetime import datetime

REFERENCE_TIME = datetime(2025, 7, 14, 9, 0, 0)


def get_current_time():
	"""
	Returns the current time. For debugging and testing, this can be configured
	to return a fixed time.
	"""
	return REFERENCE_TIME
