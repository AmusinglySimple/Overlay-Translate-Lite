# gui/resource_monitor.py
import logging
import psutil
import os # Import os to get process ID

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout
from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtGui import QColor

logger = logging.getLogger("OverlayTranslate")

class ResourceMonitorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_process = None # Store the psutil Process object
        try:
            # Get the Process object for the current Python script
            pid = os.getpid()
            self.current_process = psutil.Process(pid)
            # Call cpu_percent once initially to start the interval calculation
            # subsequent calls will return usage since the last call.
            self.current_process.cpu_percent(interval=None)
            logger.info(f"Resource monitor attached to process PID: {pid}")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.error(f"Failed to get current process info for resource monitoring: {e}")
            self.current_process = None # Ensure it's None if failed

        self.initUI()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_stats)
        # Update slightly more frequently for app-specific usage
        self.update_timer.start(1500) # Update every 1.5 seconds

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0) # Adjust margins for status bar
        layout.setSpacing(8)

        # --- CPU ---
        cpu_layout = QHBoxLayout()
        cpu_layout.setSpacing(2)
        # Changed label to indicate "App CPU"
        self.cpu_label = QLabel("App CPU:")
        self.cpu_label.setStyleSheet("font-size: 11px; color: #cccccc;")
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100) # CPU can exceed 100% on multi-core, but usually cap display
        self.cpu_progress.setValue(0)
        self.cpu_progress.setTextVisible(True)
        self.cpu_progress.setFormat("%p%")
        self.cpu_progress.setFixedHeight(14)
        self.cpu_progress.setFixedWidth(60)
        self.cpu_progress.setStyleSheet(self.get_progress_bar_style())
        cpu_layout.addWidget(self.cpu_label)
        cpu_layout.addWidget(self.cpu_progress)

        # --- RAM ---
        ram_layout = QHBoxLayout()
        ram_layout.setSpacing(2)
        # Changed label to indicate "App RAM" and added value label
        self.ram_label = QLabel("App RAM:")
        self.ram_label.setStyleSheet("font-size: 11px; color: #cccccc;")
        self.ram_value_label = QLabel("0 MB") # Label to show MB value
        self.ram_value_label.setStyleSheet("font-size: 10px; color: #bbbbbb; min-width: 40px;")
        self.ram_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Progress bar for RAM is less intuitive for specific app usage,
        # showing MB might be better. We can remove the bar or keep it.
        # Let's keep it for now, maybe representing % of total system RAM used by app?
        # Or just remove it? Let's remove it for clarity.

        # self.ram_progress = QProgressBar()
        # self.ram_progress.setRange(0, 100) # Representing % of total?
        # self.ram_progress.setValue(0)
        # self.ram_progress.setTextVisible(False) # Hide % text
        # self.ram_progress.setFixedHeight(14)
        # self.ram_progress.setFixedWidth(40)
        # self.ram_progress.setStyleSheet(self.get_progress_bar_style())

        ram_layout.addWidget(self.ram_label)
        ram_layout.addWidget(self.ram_value_label) # Add value label instead of progress
        # ram_layout.addWidget(self.ram_progress) # Removed progress bar

        layout.addLayout(cpu_layout)
        layout.addLayout(ram_layout)

        self.setLayout(layout)
        self.update_stats() # Initial update

    def get_progress_bar_style(self, value=0):
        # (Style remains the same, used only for CPU now)
        if value > 85: chunk_color = "#E74C3C" # Red
        elif value > 60: chunk_color = "#F39C12" # Orange
        else: chunk_color = "#2ECC71" # Green
        return f"""
            QProgressBar {{
                border: 1px solid #555555; border-radius: 3px;
                background-color: #333333; text-align: center;
                color: white; font-size: 9px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_color}; border-radius: 2px; margin: 1px;
            }}"""

    def update_stats(self):
        # Check if we successfully got the process object
        if not self.current_process:
            self.cpu_label.setText("CPU: N/A")
            self.ram_value_label.setText("N/A")
            return

        try:
            # Get CPU % for *this specific process* since the last call
            # Divide by cpu_count for a normalized percentage (optional but common)
            cpu_percent = self.current_process.cpu_percent(interval=None)
            # cpu_count = psutil.cpu_count()
            # normalized_cpu = cpu_percent / cpu_count if cpu_count else cpu_percent

            # Get memory info for *this specific process*
            mem_info = self.current_process.memory_info()
            # rss = Resident Set Size (non-swapped physical memory)
            # vms = Virtual Memory Size
            # Using RSS is often a good measure of actual RAM usage
            ram_mb = mem_info.rss / (1024 * 1024) # Convert bytes to MB

            # Update CPU display
            # self.cpu_progress.setValue(int(normalized_cpu)) # Use normalized %
            self.cpu_progress.setValue(int(cpu_percent)) # Or just the raw %
            self.cpu_progress.setFormat(f"{int(cpu_percent)}%") # Update text format too
            self.cpu_progress.setStyleSheet(self.get_progress_bar_style(cpu_percent))

            # Update RAM display (value label)
            self.ram_value_label.setText(f"{ram_mb:.1f} MB")

            # Update RAM progress bar (optional, if kept) - maybe % of total system RAM?
            # total_system_ram = psutil.virtual_memory().total
            # ram_percent_of_total = (mem_info.rss / total_system_ram) * 100 if total_system_ram else 0
            # self.ram_progress.setValue(int(ram_percent_of_total))
            # self.ram_progress.setStyleSheet(self.get_progress_bar_style(ram_percent_of_total))


        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process might have ended or permissions changed
            logger.warning("Lost access to process for resource monitoring.")
            self.cpu_label.setText("CPU: N/A")
            self.ram_value_label.setText("N/A")
            self.update_timer.stop() # Stop updates if process is gone
            self.current_process = None
        except Exception as e:
            logger.error(f"Error updating resource stats: {e}")
            # Don't stop timer on temporary errors, maybe just log

    def stop_updates(self):
        self.update_timer.stop()
        logger.debug("Resource monitor updates stopped.")