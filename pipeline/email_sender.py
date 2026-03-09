"""Email alert assembly and sending."""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config import SMTP_EMAIL, SMTP_PASSWORD, PROJECT_ROOT

logger = logging.getLogger(__name__)


def build_email_html(listings, filter_stats):
    """Build a nicely formatted HTML email with ranked listings.

    Args:
        listings: Ranked list of listing dicts (with all analysis data)
        filter_stats: Dict with filtering statistics

    Returns:
        HTML string
    """
    date_str = datetime.now().strftime("%B %d, %Y")
    total_found = filter_stats.get("total_input", 0)
    total_passed = filter_stats.get("passed", len(listings))
    top_score = listings[0].get("score", "N/A") if listings else "N/A"

    listings_html = ""
    for i, listing in enumerate(listings):
        rank = i + 1
        score = listing.get("score", "N/A")
        address = listing.get("address", "Unknown address")
        price = listing.get("price", "N/A")
        beds = listing.get("bedrooms", "N/A")
        baths = listing.get("bathrooms", "N/A")
        source = listing.get("source", "Unknown")
        url = listing.get("url", "#")
        nearest_shuttle = listing.get("nearest_shuttle", "N/A")
        shuttle_duration = listing.get("nearest_shuttle_duration", "N/A")
        explanation = listing.get("explanation", "")
        red_flag_data = listing.get("red_flag_analysis", {})
        outreach = listing.get("outreach_message", "")

        # Format red flags
        red_flags_html = ""
        red_flags = red_flag_data.get("red_flags", [])
        if red_flags:
            flags_list = ""
            for flag in red_flags:
                if isinstance(flag, dict):
                    issue = flag.get("issue", str(flag))
                    severity = flag.get("severity", "low")
                else:
                    issue = str(flag)
                    severity = "low"
                color = {"high": "#dc3545", "medium": "#fd7e14", "low": "#ffc107"}.get(severity, "#ffc107")
                flags_list += f'<li style="color: {color};">{issue} ({severity})</li>'
            red_flags_html = f'<div style="margin-top:8px;"><strong style="color:#dc3545;">Red Flags:</strong><ul style="margin:4px 0;">{flags_list}</ul></div>'

        # Outreach message for top 5
        outreach_html = ""
        if rank <= 5 and outreach:
            outreach_html = f'''
            <div style="margin-top:10px; padding:10px; background:#f0f7ff; border-left:3px solid #4a90d9; font-style:italic;">
                <strong>Draft Outreach Message:</strong><br>
                {outreach}
            </div>'''

        # Score bar color
        if isinstance(score, (int, float)):
            bar_color = "#28a745" if score >= 70 else "#fd7e14" if score >= 50 else "#dc3545"
            bar_width = score
        else:
            bar_color = "#6c757d"
            bar_width = 0

        listings_html += f'''
        <div style="border:1px solid #dee2e6; border-radius:8px; padding:16px; margin-bottom:16px; background:#fff;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3 style="margin:0; color:#333;">#{rank} — {address}</h3>
                <span style="font-size:24px; font-weight:bold; color:{bar_color};">{score}/100</span>
            </div>
            <div style="background:#e9ecef; border-radius:4px; height:8px; margin:8px 0;">
                <div style="background:{bar_color}; height:8px; border-radius:4px; width:{bar_width}%;"></div>
            </div>
            <table style="width:100%; margin:8px 0; font-size:14px;">
                <tr>
                    <td><strong>Price:</strong> ${price}/mo</td>
                    <td><strong>Beds/Baths:</strong> {beds}BR / {baths}BA</td>
                    <td><strong>Source:</strong> {source}</td>
                </tr>
                <tr>
                    <td colspan="2"><strong>Nearest Shuttle:</strong> {nearest_shuttle} ({shuttle_duration} walk)</td>
                    <td><a href="{url}" style="color:#4a90d9;">View Listing</a></td>
                </tr>
            </table>
            <p style="margin:8px 0; color:#555;">{explanation}</p>
            {red_flags_html}
            {outreach_html}
        </div>'''

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width:700px; margin:0 auto; padding:20px; background:#f8f9fa;">
    <div style="background:linear-gradient(135deg, #4a90d9, #7b68ee); color:white; padding:24px; border-radius:12px 12px 0 0; text-align:center;">
        <h1 style="margin:0;">New Rental Matches</h1>
        <p style="margin:8px 0 0; opacity:0.9;">{date_str}</p>
    </div>

    <div style="background:#fff; padding:16px; border-bottom:1px solid #dee2e6;">
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div>
                <div style="font-size:24px; font-weight:bold; color:#4a90d9;">{total_found}</div>
                <div style="font-size:12px; color:#666;">Listings Found</div>
            </div>
            <div>
                <div style="font-size:24px; font-weight:bold; color:#28a745;">{total_passed}</div>
                <div style="font-size:12px; color:#666;">Passed Filters</div>
            </div>
            <div>
                <div style="font-size:24px; font-weight:bold; color:#7b68ee;">{top_score}</div>
                <div style="font-size:12px; color:#666;">Top Score</div>
            </div>
        </div>
    </div>

    <div style="padding:16px 0;">
        {listings_html}
    </div>

    <div style="text-align:center; padding:16px; color:#999; font-size:12px;">
        Generated by Nefeli Rental Agent
    </div>
</body>
</html>"""

    return html


def send_email(to_email, listings, filter_stats):
    """Send the alert email or save as local HTML file.

    Args:
        to_email: Recipient email address
        listings: Ranked list of listing dicts
        filter_stats: Dict with filtering statistics

    Returns:
        Tuple of (success: bool, message: str)
    """
    html_content = build_email_html(listings, filter_stats)
    date_str = datetime.now().strftime("%Y-%m-%d")
    passed_count = filter_stats.get("passed", len(listings))
    subject = f"New Rental Matches ({passed_count}) - {date_str}"

    # Always save a local copy
    output_dir = PROJECT_ROOT / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    local_path = output_dir / f"alert_{date_str}.html"
    with open(local_path, "w") as f:
        f.write(html_content)
    logger.info(f"[Email] Saved alert HTML to {local_path}")

    # Try to send email
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        msg = f"Email credentials not set. Alert saved to {local_path}"
        logger.warning(f"[Email] {msg}")
        return False, msg

    if not to_email:
        msg = f"No recipient email provided. Alert saved to {local_path}"
        logger.warning(f"[Email] {msg}")
        return False, msg

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_EMAIL
        msg["To"] = to_email

        msg.attach(MIMEText(f"You have {passed_count} new rental matches. View the HTML version for details.", "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_email, msg.as_string())

        logger.info(f"[Email] Alert sent to {to_email}")
        return True, f"Email sent to {to_email}"

    except Exception as e:
        error_msg = f"Failed to send email: {e}. Alert saved to {local_path}"
        logger.error(f"[Email] {error_msg}")
        return False, error_msg
