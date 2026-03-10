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
    """Build a Nido-branded HTML email with ranked listings."""
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

        # Score color
        if isinstance(score, (int, float)):
            score_color = "#5A8F5C" if score >= 70 else "#C8944A" if score >= 50 else "#C0524E"
            bar_width = score
        else:
            score_color = "#A89890"
            bar_width = 0

        # Red flag pills
        red_flags_html = ""
        red_flags = red_flag_data.get("red_flags", [])
        if red_flags:
            pills = ""
            for flag in red_flags:
                if isinstance(flag, dict):
                    issue = flag.get("issue", str(flag))
                    severity = flag.get("severity", "low")
                else:
                    issue = str(flag)
                    severity = "low"
                pill_colors = {
                    "high": ("background:#FCEAEA;color:#C0524E;", issue),
                    "medium": ("background:#F5E6CE;color:#8B6914;", issue),
                    "low": ("background:#FFF8E1;color:#9E8600;", issue),
                }
                style, text = pill_colors.get(severity, pill_colors["low"])
                pills += f'<span style="{style}display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;margin:2px 4px 2px 0;">{text}</span>'
            red_flags_html = f'<div style="margin-top:10px;">{pills}</div>'

        # Outreach for top 5
        outreach_html = ""
        if rank <= 5 and outreach:
            outreach_html = f'''
            <div style="margin-top:12px;padding:12px;background:#FBF7F4;border-left:3px solid #C4704B;border-radius:4px;">
                <strong style="font-size:12px;color:#C4704B;">Draft Outreach:</strong><br>
                <span style="font-size:13px;color:#3D2B1F;line-height:1.5;">{outreach}</span>
            </div>'''

        # Price display
        price_display = f"${price:,.0f}/mo" if isinstance(price, (int, float)) else f"${price}/mo"

        listings_html += f'''
        <div style="border:1px solid #E8E0D8;border-radius:12px;padding:20px;margin-bottom:14px;background:#FFFFFF;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                    <td width="40" valign="top">
                        <div style="width:32px;height:32px;border-radius:50%;background:{'#C8944A' if rank <= 3 else '#C4704B'};color:white;text-align:center;line-height:32px;font-weight:700;font-size:13px;">{rank}</div>
                    </td>
                    <td valign="top" style="padding-left:8px;">
                        <div style="font-size:15px;font-weight:600;color:#3D2B1F;">{address}</div>
                        <div style="font-size:11px;color:#A89890;margin-top:2px;">via {source}</div>
                    </td>
                    <td width="60" valign="top" align="right">
                        <div style="font-size:20px;font-weight:700;color:{score_color};">{score}</div>
                        <div style="font-size:10px;color:#A89890;">/ 100</div>
                    </td>
                </tr>
            </table>
            <div style="background:#F0EAE4;border-radius:4px;height:6px;margin:10px 0;">
                <div style="background:{score_color};height:6px;border-radius:4px;width:{bar_width}%;"></div>
            </div>
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:13px;color:#7A6A5E;margin:8px 0;">
                <tr>
                    <td>{price_display}</td>
                    <td>{beds} bd / {baths} ba</td>
                    <td>{shuttle_duration} to {nearest_shuttle}</td>
                </tr>
            </table>
            <p style="font-size:13px;color:#7A6A5E;line-height:1.5;margin:8px 0;">{explanation}</p>
            {red_flags_html}
            {outreach_html}
            <a href="{url}" style="display:inline-block;margin-top:10px;font-size:12px;color:#C4704B;text-decoration:none;font-weight:500;">View listing &rarr;</a>
        </div>'''

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;padding:20px;background:#FBF7F4;">
    <div style="text-align:center;padding:28px 20px;background:#FFFFFF;border-radius:16px 16px 0 0;border-bottom:1px solid #E8E0D8;">
        <div style="font-size:28px;font-weight:700;color:#3D2B1F;letter-spacing:-0.5px;">Nido</div>
        <div style="font-size:14px;color:#A89890;margin-top:4px;">New Rental Matches &middot; {date_str}</div>
    </div>

    <div style="background:#FFFFFF;padding:20px;border-bottom:1px solid #E8E0D8;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="text-align:center;">
            <tr>
                <td>
                    <div style="font-size:22px;font-weight:700;color:#C4704B;">{total_found}</div>
                    <div style="font-size:11px;color:#A89890;text-transform:uppercase;letter-spacing:0.5px;">Scraped</div>
                </td>
                <td>
                    <div style="font-size:22px;font-weight:700;color:#5A8F5C;">{total_passed}</div>
                    <div style="font-size:11px;color:#A89890;text-transform:uppercase;letter-spacing:0.5px;">Passed</div>
                </td>
                <td>
                    <div style="font-size:22px;font-weight:700;color:#C8944A;">{top_score}</div>
                    <div style="font-size:11px;color:#A89890;text-transform:uppercase;letter-spacing:0.5px;">Top Score</div>
                </td>
            </tr>
        </table>
    </div>

    <div style="padding:16px 0;">
        {listings_html}
    </div>

    <div style="text-align:center;padding:20px;color:#A89890;font-size:11px;">
        Sent by Nido &middot; Your apartment search assistant
    </div>
</body>
</html>"""

    return html


def send_email(to_email, listings, filter_stats):
    """Send the alert email or save as local HTML file."""
    html_content = build_email_html(listings, filter_stats)
    date_str = datetime.now().strftime("%Y-%m-%d")
    passed_count = filter_stats.get("passed", len(listings))
    subject = f"Nido: {passed_count} New Rental Matches - {date_str}"

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
        msg["From"] = f"Nido <{SMTP_EMAIL}>"
        msg["To"] = to_email

        plain_text = f"You have {passed_count} new rental matches from Nido. View the HTML version for details."
        msg.attach(MIMEText(plain_text, "plain"))
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
