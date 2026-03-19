"""
app.py  —  GUI front-end for the Check Processor / Donation Report tool.

Run with:
    python app.py

No extra dependencies beyond what's already in requirements.txt.
tkinter ships with every standard Python installation.
"""

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# Load .env before importing local modules so ANTHROPIC_API_KEY is set
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed yet; user must set env var manually


# ── Redirect stdout/stderr into a queue so we can stream it to the GUI ────────

class _QueueWriter:
    """File-like object that puts lines onto a queue."""
    def __init__(self, q: queue.Queue) -> None:
        self._q = q

    def write(self, text: str) -> None:
        if text:
            self._q.put(text)

    def flush(self) -> None:
        pass


# ── Main application window ───────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Check Processor — Donation Report Generator")
        self.resizable(True, True)
        self.minsize(640, 520)

        self._log_queue: queue.Queue = queue.Queue()
        self._processing = False
        self._report_path: Path | None = None

        self._build_ui()
        self._poll_log()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        # ── API key row ───────────────────────────────────────────────────────
        frame_key = ttk.LabelFrame(self, text="Anthropic API Key")
        frame_key.pack(fill="x", **pad)

        self._api_key_var = tk.StringVar(value=os.environ.get("ANTHROPIC_API_KEY", ""))
        ttk.Label(frame_key, text="Key:").pack(side="left", padx=(8, 4), pady=6)
        self._api_entry = ttk.Entry(frame_key, textvariable=self._api_key_var, show="*", width=52)
        self._api_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)
        self._show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame_key, text="Show", variable=self._show_key_var,
            command=self._toggle_key_visibility,
        ).pack(side="left", padx=(0, 8))

        # ── Input PDF row ─────────────────────────────────────────────────────
        frame_in = ttk.LabelFrame(self, text="Input PDF")
        frame_in.pack(fill="x", **pad)

        self._pdf_var = tk.StringVar()
        ttk.Label(frame_in, text="File:").pack(side="left", padx=(8, 4), pady=6)
        ttk.Entry(frame_in, textvariable=self._pdf_var, width=52).pack(
            side="left", fill="x", expand=True, padx=(0, 4), pady=6
        )
        ttk.Button(frame_in, text="Browse…", command=self._browse_pdf).pack(
            side="left", padx=(0, 8), pady=6
        )

        # ── Output HTML row ───────────────────────────────────────────────────
        frame_out = ttk.LabelFrame(self, text="Output Report")
        frame_out.pack(fill="x", **pad)

        self._out_var = tk.StringVar(value="donation_report.html")
        ttk.Label(frame_out, text="Save to:").pack(side="left", padx=(8, 4), pady=6)
        ttk.Entry(frame_out, textvariable=self._out_var, width=52).pack(
            side="left", fill="x", expand=True, padx=(0, 4), pady=6
        )
        ttk.Button(frame_out, text="Browse…", command=self._browse_out).pack(
            side="left", padx=(0, 8), pady=6
        )

        # ── Options row ───────────────────────────────────────────────────────
        frame_opts = ttk.Frame(self)
        frame_opts.pack(fill="x", padx=12, pady=2)

        ttk.Label(frame_opts, text="Render DPI:").pack(side="left")
        self._dpi_var = tk.StringVar(value="200")
        dpi_spin = ttk.Spinbox(
            frame_opts, from_=72, to=600, increment=50,
            textvariable=self._dpi_var, width=6,
        )
        dpi_spin.pack(side="left", padx=(4, 20))
        ttk.Label(frame_opts, text="(higher = slower but more accurate)", foreground="#666").pack(side="left")

        # ── Action buttons ────────────────────────────────────────────────────
        frame_btns = ttk.Frame(self)
        frame_btns.pack(fill="x", padx=12, pady=8)

        self._run_btn = ttk.Button(
            frame_btns, text="Process PDF  →  Generate Report",
            command=self._start_processing, style="Accent.TButton",
        )
        self._run_btn.pack(side="left")

        self._open_btn = ttk.Button(
            frame_btns, text="Open Report in Browser",
            command=self._open_report, state="disabled",
        )
        self._open_btn.pack(side="left", padx=(12, 0))

        self._clear_btn = ttk.Button(frame_btns, text="Clear Log", command=self._clear_log)
        self._clear_btn.pack(side="right")

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress = ttk.Progressbar(self, mode="indeterminate")
        self._progress.pack(fill="x", padx=12, pady=(0, 4))

        # ── Log area ──────────────────────────────────────────────────────────
        ttk.Label(self, text="Log output:").pack(anchor="w", padx=12)
        self._log = scrolledtext.ScrolledText(
            self, state="disabled", height=16, font=("Consolas", 10),
            background="#1e1e1e", foreground="#d4d4d4", insertbackground="white",
        )
        self._log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ── Event handlers ────────────────────────────────────────────────────────

    def _toggle_key_visibility(self) -> None:
        self._api_entry.config(show="" if self._show_key_var.get() else "*")

    def _browse_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Select scanned check PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._pdf_var.set(path)
            # Auto-suggest output name next to the PDF
            suggested = Path(path).with_name(
                Path(path).stem + "_donation_report.html"
            )
            self._out_var.set(str(suggested))

    def _browse_out(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save report as",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialfile=self._out_var.get(),
        )
        if path:
            self._out_var.set(path)

    def _open_report(self) -> None:
        if self._report_path and self._report_path.exists():
            webbrowser.open(self._report_path.as_uri())

    def _clear_log(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ── Processing ────────────────────────────────────────────────────────────

    def _start_processing(self) -> None:
        if self._processing:
            return

        api_key = self._api_key_var.get().strip()
        pdf_path = self._pdf_var.get().strip()
        out_path = self._out_var.get().strip()

        if not api_key:
            messagebox.showwarning("Missing API Key", "Please enter your Anthropic API key.")
            return
        if not pdf_path:
            messagebox.showwarning("No PDF selected", "Please choose an input PDF file.")
            return
        if not Path(pdf_path).exists():
            messagebox.showerror("File not found", f"Cannot find:\n{pdf_path}")
            return

        try:
            dpi = int(self._dpi_var.get())
            if not (72 <= dpi <= 600):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid DPI", "DPI must be a number between 72 and 600.")
            return

        # Set the API key in the environment for this session
        os.environ["ANTHROPIC_API_KEY"] = api_key

        self._processing = True
        self._report_path = None
        self._run_btn.config(state="disabled")
        self._open_btn.config(state="disabled")
        self._progress.start(12)

        thread = threading.Thread(
            target=self._run_worker,
            args=(pdf_path, out_path, dpi),
            daemon=True,
        )
        thread.start()

    def _run_worker(self, pdf_path: str, out_path: str, dpi: int) -> None:
        """Runs in a background thread — imports happen here so stdout works."""
        writer = _QueueWriter(self._log_queue)
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = writer  # type: ignore[assignment]

        success = False
        report_path: Path | None = None
        try:
            # Lazy import so we don't block the GUI at startup
            from check_processor import process_pdf
            from donation_report import generate_report

            print(f"\nStep 1/2  Extracting checks from '{Path(pdf_path).name}'...")
            checks = process_pdf(pdf_path, dpi=dpi)

            detected = sum(1 for c in checks if c.donor_name)
            if not detected:
                print("\nNo checks detected — nothing to report.")
            else:
                print(f"\nStep 2/2  Building donation report...")
                report_path = generate_report(checks, output_path=out_path)
                print(f"\nDone!  {detected} check(s) processed.")
                print(f"  Report → {report_path.resolve()}")
                success = True
        except Exception as exc:
            print(f"\nERROR: {exc}")
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            self.after(0, self._on_done, success, report_path)

    def _on_done(self, success: bool, report_path: "Path | None") -> None:
        self._processing = False
        self._progress.stop()
        self._run_btn.config(state="normal")
        if success and report_path:
            self._report_path = report_path
            self._open_btn.config(state="normal")
            messagebox.showinfo(
                "Complete",
                f"Report generated!\n\n{report_path.resolve()}",
            )

    # ── Log polling ───────────────────────────────────────────────────────────

    def _poll_log(self) -> None:
        """Drain the log queue and append text to the log widget every 50 ms."""
        try:
            while True:
                text = self._log_queue.get_nowait()
                self._log.config(state="normal")
                self._log.insert("end", text)
                self._log.see("end")
                self._log.config(state="disabled")
        except queue.Empty:
            pass
        self.after(50, self._poll_log)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
