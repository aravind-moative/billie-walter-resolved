import csv
import logging
import os
import re
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.routes.auth import get_current_user
from app.utilities.instances import get_db_manager
from app.utilities.time_utils import get_current_time

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates"))

# Router for dashboard
dashboard_router = APIRouter()


# Pydantic models for request/response
class FilterRequest(BaseModel):
    nature: Optional[str] = None
    time: Optional[str] = None
    scale: Optional[str] = None


class FilterResponse(BaseModel):
    success: bool
    outages: list
    outage_zipcodes: list
    highest_outage_zipcode: dict
    scale_counts: dict
    legend_counts: dict
    alerts: list
    chart_data: dict
    error: Optional[str] = None


class ExportRequest(BaseModel):
    nature: Optional[str] = None
    time: Optional[str] = None
    scale: Optional[str] = None


# Configure dashboard-specific logging
def setup_dashboard_logging():
    """Setup logging for dashboard functionality."""
    # Create output directory if it doesn't exist
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output")  # noqa: PTH118, PTH120
    os.makedirs(output_dir, exist_ok=True)  # noqa: PTH103

    log_file = os.path.join(output_dir, "dashboard.log")  # noqa: PTH118

    # Create logger
    logger = logging.getLogger("dashboard")
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
dashboard_logger = setup_dashboard_logging()


def extract_zip_codes_from_outages(outages):
    """Helper function to extract unique zip codes from outages."""
    dashboard_logger.debug(f"Extracting zip codes from {len(outages)} outages")

    zip_codes = set()
    zip_pattern = r"\b\d{5}(?:-\d{4})?\b"  # Matches 5-digit or 5+4 zip codes

    for outage in outages:
        if outage.address:
            # Find all zip codes in the address string
            matches = re.findall(zip_pattern, outage.address)
            for match in matches:
                # Take only the 5-digit part if it's a 5+4 format
                zip_code = match.split("-")[0]
                zip_codes.add(zip_code)

    zip_list = list(zip_codes)
    dashboard_logger.info(f"Extracted {len(zip_list)} unique zip codes: {zip_list}")
    return zip_list


def _prepare_outages_data(outages):
    """Prepare outage data for serialization."""
    return [
        {
            "name": o.name if o.name else "",
            "address": o.address,
            "nature": o.nature,
            "start_time": o.start_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "latitude": o.latitude,
            "longitude": o.longitude,
            "reference_number": o.reference_number,
            "scale": o.Scale if hasattr(o, "Scale") else None,
        }
        for o in outages
    ]


def _prepare_alerts_data(alerts):
    """Prepare alerts data for serialization."""
    return [
        {
            "name": alert.name if alert.name else "Unknown",
            "address": alert.address or "Address not available",
            "nature": alert.nature,
            "status": alert.status or "reported",
            "start_time": alert.start_time.strftime("%Y-%m-%d %H:%M:%S") if alert.start_time else "",
        }
        for alert in alerts
    ]


def _prepare_legend_counts_data(counts):
    """Prepare legend counts data for serialization."""
    return {
        "Water": counts.get("Water", 0),
    }


def _prepare_chart_data(outages, hours_back, nature_filter=None):
    """Process filtered outages into 1-hour interval chart data."""
    dashboard_logger.debug(f"Processing {len(outages)} outages for chart with {hours_back} hours back")

    current_time = get_current_time()
    start_time = current_time - timedelta(hours=hours_back)
    start_time = start_time.replace(minute=0, second=0, microsecond=0)

    labels = []
    datasets = {nature_filter: []} if nature_filter else {"Water": []}

    interval_end = start_time
    while interval_end < current_time:
        interval_start = interval_end
        interval_end += timedelta(hours=1)
        labels.append(interval_end.strftime("%I %p").strip())

        interval_counts = dict.fromkeys(datasets, 0)

        for outage in outages:
            try:
                # Parse the datetime from outage
                outage_time_str = outage.start_time
                outage_time = datetime.strptime(outage_time_str, "%Y-%m-%dT%H:%M:%S") if isinstance(outage_time_str, str) else outage_time_str

                # Check if outage falls within this interval
                if interval_start <= outage_time < interval_end:
                    outage_nature = outage.nature
                    if outage_nature in interval_counts:
                        interval_counts[outage_nature] += 1
            except (ValueError, TypeError) as e:
                dashboard_logger.warning(f"Error parsing outage time: {e}")
                continue

        # Add data for each type
        for nature_type in datasets:  # noqa: PLC0206
            datasets[nature_type].append(interval_counts.get(nature_type, 0))

        start_time = interval_end

    total_reports = sum(sum(datasets[nature]) for nature in datasets)
    dashboard_logger.info(f"Generated hourly chart data: {len(labels)} intervals, total reports: {total_reports}")

    return {"labels": labels, "datasets": datasets}


def _generate_csv_response(outages, nature=None, time_filter=None, scale_filter=None):
    """Generate a CSV response for export."""
    if not outages:
        dashboard_logger.warning("No data for CSV export")
        raise HTTPException(status_code=404, detail="No data available for export")

    csv_data = [
        {
            "Customer Name": o.name if o.name else "",
            "Address": o.address or "",
            "Nature": o.nature,
            "Start Time": o.start_time.strftime("%Y-%m-%d %H:%M:%S") if o.start_time else "",
        }
        for o in outages
    ]

    output = StringIO()
    if csv_data:
        writer = csv.DictWriter(output, fieldnames=csv_data[0].keys())
        writer.writeheader()
        writer.writerows(csv_data)
    csv_content = output.getvalue()
    output.close()

    timestamp = get_current_time().strftime("%Y%m%d_%H%M%S")
    filename_parts = ["outages_report", timestamp]
    if nature:
        filename_parts.append(f"nature_{nature}")
    if time_filter:
        filename_parts.append(f"time_{time_filter}")
    if scale_filter:
        filename_parts.append(f"scale_{scale_filter}")
    filename = "_".join(filename_parts) + ".csv"

    dashboard_logger.info(f"Exporting {len(csv_data)} records to {filename}")
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _extract_area_from_address(address):
    """Extract area/city name from address format: Street, City, TX ZIP, USA"""
    if not address:
        return None
    try:
        parts = address.split(", ")
        if len(parts) >= 3:
            city = parts[1].strip()
            if city:
                return city
        dashboard_logger.debug(f"Could not extract area from address: {address}")
        return None
    except Exception as e:
        dashboard_logger.warning(f"Error extracting area from address '{address}': {e}")
        return None


def _calculate_highest_outage_zipcode(outages):
    if not outages:
        return {"zipcode": None, "count": 0, "area_name": None}
    zipcode_counts = {}
    zipcode_addresses = {}
    for outage in outages:
        if outage.address:
            zipcode_match = re.search(r"\b(\d{5})\b", outage.address)
            if zipcode_match:
                zipcode = zipcode_match.group(1)
                zipcode_counts[zipcode] = zipcode_counts.get(zipcode, 0) + 1
                if zipcode not in zipcode_addresses:
                    zipcode_addresses[zipcode] = outage.address
    if not zipcode_counts:
        return {"zipcode": None, "count": 0, "area_name": None}
    highest_zipcode = max(zipcode_counts, key=zipcode_counts.get)
    highest_count = zipcode_counts[highest_zipcode]
    area_name = _extract_area_from_address(zipcode_addresses.get(highest_zipcode))
    dashboard_logger.info(f"Highest outage zipcode: {highest_zipcode} ({area_name}) with {highest_count} outages")
    return {
        "zipcode": highest_zipcode,
        "count": highest_count,
        "area_name": area_name,
    }


def _calculate_scale_counts(outages):
    """Calculate counts of small, medium, and large outages from the list."""
    scale_counts = {"small": 0, "medium": 0, "large": 0}
    for outage in outages:
        if outage.Scale in scale_counts:
            scale_counts[outage.Scale] += 1
    dashboard_logger.info(f"Scale counts: {scale_counts}")
    return scale_counts


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    dashboard_logger.info("=== DASHBOARD PAGE LOAD ===")

    # Get all outage data for initial load
    outages = get_db_manager().get_outages_filtered()

    # Extract unique zip codes from outages
    outage_zipcodes = extract_zip_codes_from_outages(outages)

    dashboard_logger.info(f"Dashboard rendered with {len(outages)} outages and {len(outage_zipcodes)} highlighted zip codes")
    return templates.TemplateResponse(
        "dashboard.html", 
        {
            "request": request, 
            "outages": outages, 
            "outage_zipcodes": outage_zipcodes,
            "session": request.session
        }
    )


@dashboard_router.post("/dashboard/filter", response_model=FilterResponse)
async def filter_outages(
    request_data: FilterRequest,
    current_user: dict = Depends(get_current_user)
):
    """AJAX endpoint for filtering outages."""
    dashboard_logger.info("=== FILTER REQUEST RECEIVED ===")

    try:
        nature_filter = request_data.nature
        time_filter = request_data.time
        scale_filter = request_data.scale

        dashboard_logger.info(f"Filter parameters: nature='{nature_filter}', time_filter='{time_filter}', scale_filter='{scale_filter}'")

        outages = get_db_manager().get_outages_filtered(
            nature=nature_filter,
            time_filter=time_filter,
            scale_filter=scale_filter,
        )

        # Prepare all data for JSON response
        outages_data = _prepare_outages_data(outages)
        outage_zipcodes = extract_zip_codes_from_outages(outages)
        highest_outage_zipcode = _calculate_highest_outage_zipcode(outages)
        scale_counts = _calculate_scale_counts(outages)

        legend_counts = get_db_manager().get_outage_counts_by_nature()
        legend_counts_data = _prepare_legend_counts_data(legend_counts)

        alerts = get_db_manager().get_latest_outage_alerts(limit=5, nature_filter=nature_filter)
        alerts_data = _prepare_alerts_data(alerts)

        # Chart data is always for the last 24 hours
        chart_outages = get_db_manager().get_outages_filtered(nature=nature_filter, time_filter="1d")
        chart_data = _prepare_chart_data(chart_outages, 24, nature_filter)

        return FilterResponse(
            success=True,
            outages=outages_data,
            outage_zipcodes=outage_zipcodes,
            highest_outage_zipcode=highest_outage_zipcode,
            scale_counts=scale_counts,
            legend_counts=legend_counts_data,
            alerts=alerts_data,
            chart_data=chart_data,
        )

    except Exception as e:
        error_msg = str(e)
        dashboard_logger.error(f"FILTER ERROR: {error_msg}")
        return FilterResponse(success=False, error=error_msg)


@dashboard_router.post("/dashboard/export-csv")
async def export_csv(
    request_data: ExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Endpoint for exporting outages to a CSV file."""
    dashboard_logger.info("=== CSV EXPORT REQUEST RECEIVED ===")
    try:
        nature_filter = request_data.nature
        time_filter = request_data.time
        scale_filter = request_data.scale

        dashboard_logger.info(f"Export parameters: nature='{nature_filter}', time_filter='{time_filter}', scale_filter='{scale_filter}'")

        outages = get_db_manager().get_outages_filtered(
            nature=nature_filter,
            time_filter=time_filter,
            scale_filter=scale_filter,
        )

        return _generate_csv_response(
            outages,
            nature=nature_filter,
            time_filter=time_filter,
            scale_filter=scale_filter,
        )

    except Exception as e:
        error_msg = str(e)
        dashboard_logger.error(f"CSV EXPORT ERROR: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
