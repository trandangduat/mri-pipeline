import tkinter as tk
from tkinter import ttk

class LineChart(ttk.Frame):
    def __init__(self, parent: tk.Widget, title: str, color: str, unit: str, minimum_scale: float) -> None:
        super().__init__(parent)
        self.title = title
        self.color = color
        self.unit = unit
        self.minimum_scale = minimum_scale
        self.points: list[float] = []
        self.max_points = 180
        self.label = tk.StringVar(value=f"{title}: n/a")

        ttk.Label(self, textvariable=self.label).pack(anchor=tk.W, pady=(0, 4))
        # Use tk.Canvas since ttk doesn't have a Canvas. sv-ttk doesn't style canvas backgrounds nicely by default
        # so we keep the dark background for the chart.
        self.canvas = tk.Canvas(self, height=90, highlightthickness=1, highlightbackground="#374151")
        self.canvas.pack(fill=tk.X, expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw_chart())

    def reset(self) -> None:
        self.points.clear()
        self.label.set(f"{self.title}: n/a")
        self._draw_chart()

    def add(self, value: float, text: str) -> None:
        self.points.append(max(value, 0.0))
        self.points = self.points[-self.max_points :]
        self.label.set(f"{self.title}: {text}")
        self._draw_chart()

    def _draw_chart(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 10)
        height = max(self.canvas.winfo_height(), 10)
        pad_left = 42
        pad_bottom = 24
        pad_top = 10
        pad_right = 8
        max_value = max(self.minimum_scale, max(self.points or [0]))

        self.canvas.create_line(pad_left, height - pad_bottom, width - pad_right, height - pad_bottom, fill="#4b5563")
        self.canvas.create_line(pad_left, pad_top, pad_left, height - pad_bottom, fill="#4b5563")

        self.canvas.create_text(6, pad_top + 2, text=f"{max_value:.0f}{self.unit}", fill="#9ca3af", anchor=tk.W, font=("Inter", 8))
        self.canvas.create_text(6, height - pad_bottom, text=f"0{self.unit}", fill="#9ca3af", anchor=tk.W, font=("Inter", 8))

        for frac in (0.25, 0.5, 0.75):
            y = height - pad_bottom - frac * (height - pad_bottom - pad_top)
            self.canvas.create_line(pad_left, y, width - pad_right, y, fill="#1f2937")

        if len(self.points) == 1:
            x = pad_left
            y = height - pad_bottom - (min(self.points[0], max_value) / max_value) * (height - pad_bottom - pad_top)
            self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=self.color, outline=self.color)
            return
        if len(self.points) < 2:
            return

        usable_w = width - pad_left - pad_right
        usable_h = height - pad_bottom - pad_top
        step = usable_w / max(len(self.points) - 1, 1)
        coords: list[float] = []
        for idx, point in enumerate(self.points):
            x = pad_left + idx * step
            y = height - pad_bottom - (min(point, max_value) / max_value) * usable_h
            coords.extend([x, y])
        self.canvas.create_line(*coords, fill=self.color, width=2, smooth=True)


class MetricsCharts(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.container_label = tk.StringVar(value="Container: n/a")
        ttk.Label(self, textvariable=self.container_label).pack(anchor=tk.W, pady=(0, 6))

        charts = ttk.Frame(self)
        charts.pack(fill=tk.X, expand=True)
        self.cpu_chart = LineChart(charts, "CPU", "#60a5fa", "%", 100.0)
        self.ram_chart = LineChart(charts, "RAM", "#34d399", " MiB", 1024.0)
        self.cpu_chart.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ram_chart.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

    def reset(self) -> None:
        self.container_label.set("Container: n/a")
        self.cpu_chart.reset()
        self.ram_chart.reset()

    def add(self, cpu_pct: float | None, ram_bytes: int | None, container_name: str) -> None:
        cpu = max(cpu_pct or 0.0, 0.0)
        ram_mib = (ram_bytes or 0) / (1024 * 1024)
        ram_text = f"{ram_mib:.1f} MiB" if ram_mib < 1024 else f"{ram_mib / 1024:.2f} GiB"
        self.container_label.set(f"Container: {container_name or 'n/a'}")
        self.cpu_chart.add(cpu, f"{cpu:.1f}%")
        self.ram_chart.add(ram_mib, ram_text)
