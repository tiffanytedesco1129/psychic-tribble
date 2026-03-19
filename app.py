"""
Check Processing Web App
========================
Run with:  python app.py
Then open: http://localhost:5000

Upload a PDF or image of scanned checks, get the formatted gift-processing
report displayed in the browser ready to copy-paste into an email.
"""

import os
import tempfile
from pathlib import Path

from flask import Flask, render_template_string, request

from check_processor import extract_check_data
from donation_report import generate_report, report_subject

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB limit

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

_UPLOAD_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Check Processor — Midnight Mission</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 620px; margin: 60px auto;
           padding: 0 20px; color: #222; }
    h1 { color: #1a3a5c; }
    label { display: block; margin-top: 16px; font-weight: bold; }
    input[type=file], input[type=text] {
      display: block; width: 100%; margin-top: 6px; padding: 8px;
      border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;
      font-size: 14px;
    }
    .row { display: flex; gap: 12px; }
    .row > div { flex: 1; }
    button {
      margin-top: 24px; padding: 12px 28px; background: #1a3a5c; color: #fff;
      border: none; border-radius: 4px; font-size: 15px; cursor: pointer;
    }
    button:hover { background: #254e7a; }
    .note { color: #666; font-size: 13px; margin-top: 8px; }
    .error { background: #fff0f0; border: 1px solid #e88; border-radius: 4px;
             padding: 12px 16px; margin-top: 20px; color: #c00; }
  </style>
</head>
<body>
  <h1>Midnight Mission — Check Processor</h1>
  <p>Upload a scanned PDF or image of donation checks. The formatted gift-processing
     report will appear on the next page, ready to copy into an email.</p>

  {% if error %}
  <div class="error"><strong>Error:</strong> {{ error }}</div>
  {% endif %}

  <form method="post" enctype="multipart/form-data" action="/process">
    <label>Check scan (PDF, PNG, JPG…)</label>
    <input type="file" name="scan" accept=".pdf,.png,.jpg,.jpeg,.gif,.webp" required>

    <div class="row">
      <div>
        <label>Period start <span style="font-weight:normal">(optional)</span></label>
        <input type="text" name="start" placeholder="e.g. March 1, 2026">
      </div>
      <div>
        <label>Period end <span style="font-weight:normal">(optional)</span></label>
        <input type="text" name="end" placeholder="e.g. March 15, 2026">
      </div>
    </div>

    <button type="submit">Process Checks</button>
    <p class="note">Processing may take 15–30 seconds depending on the number of pages.</p>
  </form>
</body>
</html>
"""

_RESULT_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Gift Report — {{ subject }}</title>
  <style>
    /* toolbar */
    #toolbar {
      position: fixed; top: 0; left: 0; right: 0; background: #1a3a5c;
      color: #fff; padding: 10px 20px; display: flex; align-items: center;
      gap: 16px; z-index: 999; font-family: Arial, sans-serif; font-size: 14px;
    }
    #toolbar strong { flex: 1; }
    #toolbar button {
      padding: 7px 16px; background: #fff; color: #1a3a5c; border: none;
      border-radius: 4px; font-size: 13px; cursor: pointer; font-weight: bold;
    }
    #toolbar button:hover { background: #e8eef5; }
    #toolbar a { color: #ccd9e8; text-decoration: none; font-size: 13px; }
    #toolbar a:hover { color: #fff; }
    /* report body pushed below toolbar */
    #report-wrap { margin-top: 56px; padding: 20px; }
    /* copy flash */
    #copy-msg {
      display: none; background: #d4edda; color: #155724; border: 1px solid #c3e6cb;
      border-radius: 4px; padding: 4px 12px; font-size: 13px;
    }
  </style>
</head>
<body>
  <div id="toolbar">
    <strong>{{ subject }}</strong>
    <span id="copy-msg">Copied!</span>
    <button onclick="copyReport()">Copy Report</button>
    <a href="/">&#8592; Process another</a>
  </div>
  <div id="report-wrap">
    <div id="report-content">{{ report_html|safe }}</div>
  </div>
  <script>
    function copyReport() {
      const el = document.getElementById('report-content');
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand('copy');
      sel.removeAllRanges();
      const msg = document.getElementById('copy-msg');
      msg.style.display = 'inline';
      setTimeout(() => { msg.style.display = 'none'; }, 2000);
    }
  </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(_UPLOAD_PAGE, error=None)


@app.route("/process", methods=["POST"])
def process():
    scan = request.files.get("scan")
    if not scan or not scan.filename:
        return render_template_string(_UPLOAD_PAGE, error="Please select a file to upload."), 400

    suffix = Path(scan.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return render_template_string(
            _UPLOAD_PAGE,
            error=f"Unsupported file type '{suffix}'. Please upload a PDF, PNG, or JPG.",
        ), 400

    period_start = request.form.get("start") or None
    period_end = request.form.get("end") or None

    # Save upload to a temp file, process it, then clean up
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        scan.save(tmp_path)

    try:
        data = extract_check_data(tmp_path)
    except Exception as exc:
        return render_template_string(_UPLOAD_PAGE, error=str(exc)), 500
    finally:
        os.unlink(tmp_path)

    if not data.get("checks"):
        return render_template_string(
            _UPLOAD_PAGE,
            error="No checks were detected in the uploaded file. Please check the scan and try again.",
        ), 400

    _, html_report = generate_report(data, period_start, period_end)
    subject = report_subject(data, period_start, period_end)

    # Strip the outer <html>…</html> wrapper — we embed it in our result page
    inner = html_report
    if "<body>" in inner and "</body>" in inner:
        inner = inner.split("<body>", 1)[1].rsplit("</body>", 1)[0]

    return render_template_string(
        _RESULT_PAGE,
        subject=subject,
        report_html=inner,
    )


if __name__ == "__main__":
    print("\nMidnight Mission Check Processor")
    print("=================================")
    print("Open your browser and go to:  http://localhost:5000\n")
    app.run(debug=False, port=5000)
