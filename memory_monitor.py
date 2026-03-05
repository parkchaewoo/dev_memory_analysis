"""
Windows 11 Disk Usage Monitor GUI
드라이브별 저장 공간 사용량을 실시간으로 시각화하는 도구

사용법: python memory_monitor.py
필요 패키지: pip install psutil
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import os
import sys
import traceback

try:
    import psutil
except ImportError:
    print("psutil 패키지가 필요합니다. 설치 중...")
    os.system(f"{sys.executable} -m pip install psutil")
    import psutil


# ─── 색상/스타일 상수 ───────────────────────────────────────────────
BG_DARK = "#1e1e2e"
BG_CARD = "#2a2a3d"
BG_HEADER = "#313145"
FG_TEXT = "#cdd6f4"
FG_DIM = "#6c7086"
FG_ACCENT = "#89b4fa"
FG_GREEN = "#a6e3a1"
FG_RED = "#f38ba8"
FG_YELLOW = "#f9e2af"
FG_PEACH = "#fab387"
FG_MAUVE = "#cba6f7"
FG_TEAL = "#94e2d5"
FG_SKY = "#89dceb"
FG_PINK = "#f5c2e7"
BAR_BG = "#45475a"
DRIVE_COLORS = [FG_ACCENT, FG_GREEN, FG_YELLOW, FG_PEACH, FG_MAUVE,
                FG_TEAL, FG_SKY, FG_PINK, FG_RED]


def format_bytes(b):
    """바이트를 읽기 쉬운 단위로 변환"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def get_color_for_percent(pct):
    """사용률에 따른 색상 반환"""
    if pct < 50:
        return FG_GREEN
    elif pct < 75:
        return FG_YELLOW
    elif pct < 90:
        return FG_PEACH
    return FG_RED


# ─── 캔버스 그리기 함수들 ────────────────────────────────────────────

def draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """둥근 사각형 그리기"""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def draw_bar(canvas, value, bar_width, bar_height):
    """프로그레스 바를 캔버스에 그리기"""
    canvas.delete("all")
    r = bar_height // 2
    draw_rounded_rect(canvas, 0, 0, bar_width, bar_height, r, fill=BAR_BG)
    if value > 0:
        fill_w = max(bar_height, bar_width * value / 100)
        color = get_color_for_percent(value)
        draw_rounded_rect(canvas, 0, 0, fill_w, bar_height, r, fill=color)
    canvas.create_text(bar_width // 2, bar_height // 2,
                       text=f"{value:.1f}%", fill="white",
                       font=("Segoe UI", 9, "bold"))


def draw_pie(canvas, data, size):
    """도넛 파이 차트. data: list of (label, value, color)"""
    canvas.delete("all")
    pad = 10
    total = sum(v for _, v, _ in data)
    if total == 0:
        return
    start = 0
    for _, value, color in data:
        extent = (value / total) * 360
        canvas.create_arc(pad, pad, size - pad, size - pad,
                          start=start, extent=extent,
                          fill=color, outline=BG_CARD, width=2)
        start += extent
    inner = 35
    canvas.create_oval(pad + inner, pad + inner,
                       size - pad - inner, size - pad - inner,
                       fill=BG_CARD, outline=BG_CARD)
    canvas.create_text(size // 2, size // 2, text="DISK",
                       fill=FG_ACCENT, font=("Segoe UI", 10, "bold"))


def draw_bar_chart(canvas, data, chart_w, chart_h):
    """수평 막대 차트. data: list of (label, used_pct, color)"""
    canvas.delete("all")
    if not data:
        return
    pad_left = 50
    pad_right = 60
    pad_top = 10
    n = len(data)
    bar_h = min(30, max(16, (chart_h - pad_top * 2 - (n - 1) * 6) // n))
    gap = 6

    for i, (label, pct, color) in enumerate(data):
        y = pad_top + i * (bar_h + gap)
        canvas.create_text(pad_left - 5, y + bar_h // 2, text=label,
                           anchor="e", fill=FG_TEXT, font=("Segoe UI", 9))
        bw = chart_w - pad_left - pad_right
        draw_rounded_rect(canvas, pad_left, y, pad_left + bw, y + bar_h,
                          bar_h // 2, fill=BAR_BG)
        if pct > 0:
            fill_w = max(bar_h, bw * pct / 100)
            draw_rounded_rect(canvas, pad_left, y, pad_left + fill_w, y + bar_h,
                              bar_h // 2, fill=color)
        canvas.create_text(pad_left + bw + 8, y + bar_h // 2,
                           text=f"{pct:.1f}%", anchor="w",
                           fill=get_color_for_percent(pct),
                           font=("Segoe UI", 9, "bold"))


def make_canvas(parent, w, h):
    """안전하게 Canvas 생성 (Windows 호환)"""
    c = tk.Canvas(parent)
    c.config(bg=BG_CARD, highlightthickness=0, width=w, height=h)
    return c


# ─── 폴더 크기 스캔 ──────────────────────────────────────────────────

def get_top_folders(path):
    """드라이브 루트의 최상위 폴더별 크기 측정 (빠른 1단계)
    각 폴더의 하위 디렉토리/파일 수도 함께 세어 ETA 사전 추정에 사용"""
    folders = []
    try:
        entries = list(os.scandir(path))
    except (PermissionError, OSError):
        return folders

    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            total_size = 0
            sub_count = 0  # 하위 항목 수 (깊이 추정용)
            try:
                for sub in os.scandir(entry.path):
                    sub_count += 1
                    try:
                        if sub.is_file(follow_symlinks=False):
                            total_size += sub.stat().st_size
                        elif sub.is_dir(follow_symlinks=False):
                            for subsub in os.scandir(sub.path):
                                sub_count += 1
                                try:
                                    if subsub.is_file(follow_symlinks=False):
                                        total_size += subsub.stat().st_size
                                except (PermissionError, OSError):
                                    continue
                    except (PermissionError, OSError):
                        continue
                folders.append({"name": entry.name, "path": entry.path,
                                "size": total_size, "sub_count": sub_count})
            except (PermissionError, OSError):
                continue
        elif entry.is_file(follow_symlinks=False):
            try:
                folders.append({"name": entry.name, "path": entry.path,
                                "size": entry.stat().st_size, "sub_count": 0})
            except (PermissionError, OSError):
                continue

    folders.sort(key=lambda x: x["size"], reverse=True)
    return folders[:20]


def estimate_scan_time(folders):
    """사전 측정된 하위 항목 수를 기반으로 정밀 스캔 예상 시간 계산
    경험적 수치: 2단계 스캔에서 발견된 항목당 실제로는 약 10~50배 더 많은
    하위 항목이 존재하므로, 항목당 약 0.001초로 추정"""
    total_items = sum(f.get("sub_count", 0) for f in folders)
    # 2단계 스캔에서 본 항목은 전체의 일부이므로 배수 적용
    estimated_deep_items = total_items * 20
    # 파일 하나당 약 0.0005초 (디스크 속도에 따라 다름)
    estimated_seconds = estimated_deep_items * 0.0005
    return max(1, estimated_seconds), total_items


def get_folder_size_deep(path):
    """폴더의 전체 크기를 재귀적으로 측정"""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass
    return total


# ─── 메인 애플리케이션 ────────────────────────────────────────────────

class DiskMonitorApp:
    """메인 애플리케이션"""

    PIE_SIZE = 220
    CHART_W = 420
    CHART_H = 200

    def __init__(self, root):
        self.root = root
        self.root.title("Disk Usage Monitor - Windows 11")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1150x800")
        self.root.minsize(950, 650)

        self._running = True
        self._selected_drive = tk.StringVar()
        self._sort_col = "size"
        self._sort_reverse = True
        self._search_var = tk.StringVar()
        self._folder_data = []
        self._scanning = False
        self._drives = []

        self._setup_styles()
        self._build_ui()
        self.root.update_idletasks()
        self._refresh_drives()
        self._start_update()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        """ttk 스타일 설정"""
        style = ttk.Style()
        available = style.theme_names()
        if "clam" in available:
            style.theme_use("clam")
        style.configure("Dark.Treeview",
                         background=BG_CARD, foreground=FG_TEXT,
                         fieldbackground=BG_CARD, rowheight=26,
                         font=("Segoe UI", 9))
        style.configure("Dark.Treeview.Heading",
                         background=BG_HEADER, foreground=FG_ACCENT,
                         font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Dark.Treeview",
                   background=[("selected", "#45475a")],
                   foreground=[("selected", "white")])

    def _build_ui(self):
        # ─── 헤더 ───
        header = tk.Frame(self.root, bg=BG_HEADER, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="  Disk Usage Monitor", bg=BG_HEADER,
                 fg=FG_ACCENT, font=("Segoe UI", 16, "bold")).pack(side="left", padx=10)
        tk.Button(header, text="새로고침", bg=BG_CARD, fg=FG_TEXT,
                  font=("Segoe UI", 9), relief="flat", padx=12, pady=2,
                  activebackground="#45475a", activeforeground="white",
                  command=self._refresh_drives).pack(side="right", padx=16)

        # ─── 상단: 드라이브 카드들 ───
        self.drives_frame = tk.Frame(self.root, bg=BG_DARK, pady=6)
        self.drives_frame.pack(fill="x", padx=12)

        # ─── 중간: 파이차트 + 비교 막대차트 + 상세 ───
        mid_frame = tk.Frame(self.root, bg=BG_DARK, pady=4)
        mid_frame.pack(fill="x", padx=12)

        # 왼쪽: 파이차트
        pie_outer = tk.Frame(mid_frame, bg=BG_CARD, padx=10, pady=8)
        pie_outer.pack(side="left", padx=4, anchor="n")
        tk.Label(pie_outer, text="드라이브별 사용량 분포", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack()
        self.pie_canvas = make_canvas(pie_outer, self.PIE_SIZE, self.PIE_SIZE)
        self.pie_canvas.pack(pady=4)
        self.pie_legend = tk.Frame(pie_outer, bg=BG_CARD)
        self.pie_legend.pack(fill="x")

        # 가운데: 막대차트
        chart_outer = tk.Frame(mid_frame, bg=BG_CARD, padx=10, pady=8)
        chart_outer.pack(side="left", fill="x", expand=True, padx=4, anchor="n")
        tk.Label(chart_outer, text="드라이브별 사용률 비교", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack()
        self.chart_canvas = make_canvas(chart_outer, self.CHART_W, self.CHART_H)
        self.chart_canvas.pack(pady=4)

        # 오른쪽: 드라이브 상세
        detail_outer = tk.Frame(mid_frame, bg=BG_CARD, padx=14, pady=8)
        detail_outer.pack(side="left", fill="x", expand=True, padx=4, anchor="n")
        tk.Label(detail_outer, text="드라이브 상세 정보", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.detail_labels = {}
        for key, name in [("drive", "드라이브"), ("fstype", "파일 시스템"),
                          ("total", "전체 용량"), ("used", "사용 중"),
                          ("free", "사용 가능"), ("percent", "사용률"),
                          ("mount", "마운트 포인트"), ("opts", "옵션")]:
            row = tk.Frame(detail_outer, bg=BG_CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{name}:", bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", 9), width=12, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="--", bg=BG_CARD, fg=FG_TEXT,
                           font=("Segoe UI", 9, "bold"), anchor="w")
            lbl.pack(side="left", fill="x")
            self.detail_labels[key] = lbl

        # ─── 하단: 폴더 목록 ───
        list_header = tk.Frame(self.root, bg=BG_DARK, pady=4)
        list_header.pack(fill="x", padx=16)

        self.folder_title = tk.Label(
            list_header, text="폴더/파일별 크기 (드라이브를 클릭하세요)",
            bg=BG_DARK, fg=FG_TEXT, font=("Segoe UI", 11, "bold"))
        self.folder_title.pack(side="left")

        search_frame = tk.Frame(list_header, bg=BG_DARK)
        search_frame.pack(side="right")
        tk.Label(search_frame, text="검색:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        tk.Entry(search_frame, textvariable=self._search_var,
                 bg=BG_CARD, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 9), width=20,
                 relief="flat", bd=4).pack(side="left")

        # 트리뷰
        tree_frame = tk.Frame(self.root, bg=BG_DARK)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        columns = ("name", "size", "bar", "path")
        self.tree = ttk.Treeview(tree_frame, columns=columns,
                                  show="headings", style="Dark.Treeview",
                                  selectmode="browse")

        col_config = [
            ("name", "이름", 200, "w"),
            ("size", "크기", 120, "e"),
            ("bar", "비율", 200, "w"),
            ("path", "경로", 350, "w"),
        ]
        for col_id, heading, width, anchor in col_config:
            self.tree.heading(col_id, text=heading,
                              command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor=anchor)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 상태바
        status_bar = tk.Frame(self.root, bg=BG_HEADER, pady=3)
        status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(status_bar, text="준비 중...",
                                      bg=BG_HEADER, fg=FG_DIM,
                                      font=("Segoe UI", 8))
        self.status_label.pack(side="left", padx=10)

    # ─── 드라이브 카드 ─────────────────────────────────────────────
    def _refresh_drives(self):
        """드라이브 목록 새로 가져오기"""
        for w in self.drives_frame.winfo_children():
            w.destroy()

        self._drives = []
        partitions = psutil.disk_partitions(all=False)
        for i, part in enumerate(partitions):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue

            drive_info = {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "opts": part.opts,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
            self._drives.append(drive_info)

            color = DRIVE_COLORS[i % len(DRIVE_COLORS)]
            card = tk.Frame(self.drives_frame, bg=BG_CARD, padx=14, pady=10,
                            cursor="hand2")
            card.pack(side="left", fill="both", expand=True, padx=4)

            drive_label = part.mountpoint.rstrip("\\") or part.device

            tk.Label(card, text=f"  {drive_label}", bg=BG_CARD, fg=color,
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(card, text=f"{part.fstype}", bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", 8)).pack(anchor="w")

            pct_color = get_color_for_percent(usage.percent)
            tk.Label(card, text=f"{usage.percent:.1f}% 사용", bg=BG_CARD,
                     fg=pct_color, font=("Segoe UI", 11, "bold")).pack(anchor="w")

            # 텍스트 기반 프로그레스 바 (Canvas 대신 Label 사용)
            pct_int = int(usage.percent)
            bar_filled = "\u2588" * (pct_int // 5)
            bar_empty = "\u2591" * (20 - pct_int // 5)
            bar_color = get_color_for_percent(usage.percent)
            tk.Label(card, text=bar_filled + bar_empty, bg=BG_CARD, fg=bar_color,
                     font=("Consolas", 9)).pack(anchor="w", pady=(2, 0))

            tk.Label(card, text=f"{format_bytes(usage.used)} / {format_bytes(usage.total)}",
                     bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w")
            tk.Label(card, text=f"{format_bytes(usage.free)} 여유",
                     bg=BG_CARD, fg=FG_GREEN, font=("Segoe UI", 8)).pack(anchor="w")

            mp = part.mountpoint
            card.bind("<Button-1>", lambda e, m=mp: self._on_drive_click(m))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, m=mp: self._on_drive_click(m))

        self._update_charts()

        if self._drives and not self._selected_drive.get():
            self._selected_drive.set(self._drives[0]["mountpoint"])
            self._on_drive_click(self._drives[0]["mountpoint"])

        self.status_label.config(
            text=f"감지된 드라이브: {len(self._drives)}개 | "
                 f"마지막 새로고침: {time.strftime('%H:%M:%S')}")

    def _update_charts(self):
        """파이차트 + 막대차트 업데이트"""
        if not self._drives:
            return

        pie_data = []
        for i, d in enumerate(self._drives):
            label = d["mountpoint"].rstrip("\\") or d["device"]
            color = DRIVE_COLORS[i % len(DRIVE_COLORS)]
            pie_data.append((label, d["used"], color))
        draw_pie(self.pie_canvas, pie_data, self.PIE_SIZE)

        # 범례
        for w in self.pie_legend.winfo_children():
            w.destroy()
        for i, d in enumerate(self._drives):
            color = DRIVE_COLORS[i % len(DRIVE_COLORS)]
            label = d["mountpoint"].rstrip("\\") or d["device"]
            row = tk.Frame(self.pie_legend, bg=BG_CARD)
            row.pack(fill="x", pady=0)
            tk.Label(row, text=" \u25a0", bg=BG_CARD, fg=color,
                     font=("Segoe UI", 9)).pack(side="left")
            tk.Label(row, text=f" {label}  {format_bytes(d['used'])} / {format_bytes(d['total'])}",
                     bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 8)).pack(side="left")

        # 막대차트
        bar_data = []
        for i, d in enumerate(self._drives):
            label = d["mountpoint"].rstrip("\\") or d["device"]
            color = DRIVE_COLORS[i % len(DRIVE_COLORS)]
            bar_data.append((label, d["percent"], color))

        chart_h = max(self.CHART_H, len(bar_data) * 36 + 20)
        self.chart_canvas.config(height=chart_h)
        draw_bar_chart(self.chart_canvas, bar_data, self.CHART_W, chart_h)

    def _on_drive_click(self, mountpoint):
        """드라이브 클릭 시 상세 표시 + 폴더 스캔"""
        self._selected_drive.set(mountpoint)

        drive = None
        for d in self._drives:
            if d["mountpoint"] == mountpoint:
                drive = d
                break
        if not drive:
            return

        label = drive["mountpoint"].rstrip("\\") or drive["device"]
        self.detail_labels["drive"].config(text=f"{label}  ({drive['device']})")
        self.detail_labels["fstype"].config(text=drive["fstype"])
        self.detail_labels["total"].config(text=format_bytes(drive["total"]))
        self.detail_labels["used"].config(
            text=format_bytes(drive["used"]),
            fg=get_color_for_percent(drive["percent"]))
        self.detail_labels["free"].config(
            text=format_bytes(drive["free"]), fg=FG_GREEN)
        self.detail_labels["percent"].config(
            text=f"{drive['percent']:.1f}%",
            fg=get_color_for_percent(drive["percent"]))
        self.detail_labels["mount"].config(text=drive["mountpoint"])
        self.detail_labels["opts"].config(text=drive["opts"])

        self.folder_title.config(
            text=f"{label} 드라이브 - 폴더/파일별 크기 (스캔 준비 중...)")
        self._scan_drive(mountpoint)

    def _scan_drive(self, mountpoint):
        """별도 스레드에서 드라이브 폴더 스캔 (진행률 + 예상 남은 시간 표시)"""
        if self._scanning:
            return
        self._scanning = True
        label = mountpoint.rstrip("\\") or mountpoint

        def format_eta(seconds):
            """초를 읽기 쉬운 시간 문자열로 변환"""
            if seconds < 0:
                return "계산 중..."
            if seconds < 60:
                return f"약 {int(seconds)}초"
            minutes = int(seconds) // 60
            secs = int(seconds) % 60
            if minutes < 60:
                return f"약 {minutes}분 {secs}초"
            hours = minutes // 60
            mins = minutes % 60
            return f"약 {hours}시간 {mins}분"

        def update_progress(current, total, folder_name, phase,
                            elapsed=0, eta_str=""):
            if phase == "list":
                self.folder_title.config(
                    text=f"{label} 드라이브 - 폴더 목록 수집 중... "
                         f"({current}개 발견)")
                self.status_label.config(
                    text=f"스캔: {label} 폴더 목록 수집 중...")
            elif phase == "estimate":
                self.folder_title.config(
                    text=f"{label} 드라이브 - 정밀 스캔 시작 "
                         f"({total}개 폴더, 하위 약 {current:,}개 항목 감지) "
                         f"| 예상 소요: {eta_str}")
                self.status_label.config(
                    text=f"사전 추정: 약 {current:,}개 항목 | "
                         f"예상 소요 시간: {eta_str}")
            elif phase == "deep":
                pct = int(current / total * 100) if total > 0 else 0
                bar = "\u2588" * (pct // 5) + "\u2591" * (20 - pct // 5)
                elapsed_str = format_eta(elapsed)
                self.folder_title.config(
                    text=f"{label} 드라이브 - 정밀 스캔 중... "
                         f"[{bar}] {current}/{total} ({pct}%) - {folder_name}"
                         f"  |  남은 시간: {eta_str}")
                self.status_label.config(
                    text=f"스캔: {folder_name} ({current}/{total}) | "
                         f"경과: {elapsed_str} | 남은 시간: {eta_str}")
            elif phase == "done":
                self.folder_title.config(
                    text=f"{label} 드라이브 - 폴더/파일별 크기 "
                         f"(스캔 완료 - 소요 시간: {eta_str})")
                self.status_label.config(
                    text=f"스캔 완료: {label} | {current}개 항목 | "
                         f"소요: {eta_str} | {time.strftime('%H:%M:%S')}")

        def do_scan():
            try:
                scan_start = time.time()
                self.root.after(0, update_progress, 0, 0, "", "list")
                folders = get_top_folders(mountpoint)
                self.root.after(0, update_progress, len(folders), 0, "", "list")

                scan_targets = [f for f in folders[:15]
                                if os.path.isdir(f["path"])]
                total = len(scan_targets)

                # 사전 추정: 정밀 스캔 전 예상 시간 표시
                est_seconds, item_count = estimate_scan_time(scan_targets)
                est_str = format_eta(est_seconds)
                self.root.after(0, update_progress, item_count, total,
                               "", "estimate", 0, est_str)
                time.sleep(1.5)  # 사용자가 예상 시간을 읽을 수 있도록 잠시 대기

                folder_times = []  # 각 폴더 스캔 소요 시간 기록

                for idx, f in enumerate(scan_targets):
                    if not self._running:
                        break

                    name = f["name"]
                    elapsed = time.time() - scan_start

                    # ETA 계산: 지금까지 평균 속도 기반
                    if folder_times:
                        avg_time = sum(folder_times) / len(folder_times)
                        remaining = (total - idx) * avg_time
                        eta_str = format_eta(remaining)
                    else:
                        eta_str = "계산 중..."

                    self.root.after(0, update_progress, idx + 1, total,
                                   name, "deep", elapsed, eta_str)

                    folder_start = time.time()
                    f["size"] = get_folder_size_deep(f["path"])
                    folder_elapsed = time.time() - folder_start
                    folder_times.append(folder_elapsed)

                    folders.sort(key=lambda x: x["size"], reverse=True)
                    self._folder_data = list(folders)
                    self.root.after(0, self._update_folder_list)

                total_elapsed = time.time() - scan_start
                total_str = format_eta(total_elapsed)

                folders.sort(key=lambda x: x["size"], reverse=True)
                self._folder_data = folders
                self._scanning = False
                self.root.after(0, self._update_folder_list)
                self.root.after(0, update_progress, len(folders), total,
                               "", "done", 0, total_str)
            except Exception as e:
                self._scanning = False
                self.root.after(0, lambda: self.status_label.config(
                    text=f"스캔 오류: {e}"))

        t = threading.Thread(target=do_scan, daemon=True)
        t.start()

    def _update_folder_list(self):
        """폴더 목록 트리뷰 업데이트"""
        folders = list(self._folder_data)
        search = self._search_var.get().lower()
        if search:
            folders = [f for f in folders if search in f["name"].lower()]

        key_map = {
            "name": lambda x: x["name"].lower(),
            "size": lambda x: x["size"],
            "path": lambda x: x["path"].lower(),
        }
        sort_fn = key_map.get(self._sort_col, key_map["size"])
        folders = sorted(folders, key=sort_fn, reverse=self._sort_reverse)

        max_size = max((f["size"] for f in folders), default=1) or 1

        self.tree.delete(*self.tree.get_children())
        for f in folders:
            pct = (f["size"] / max_size * 100) if max_size > 0 else 0
            bar_text = "\u2588" * int(pct / 5) + "\u2591" * (20 - int(pct / 5))
            self.tree.insert("", "end", values=(
                f["name"],
                format_bytes(f["size"]),
                bar_text,
                f["path"],
            ))

    def _sort_by(self, col):
        if col == "bar":
            col = "size"
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = col == "size"
        self._update_folder_list()

    def _start_update(self):
        """30초마다 드라이브 정보 갱신"""
        if not self._running:
            return
        self._refresh_drive_usage()
        self.root.after(30000, self._start_update)

    def _refresh_drive_usage(self):
        """드라이브 사용량만 빠르게 갱신"""
        for d in self._drives:
            try:
                usage = psutil.disk_usage(d["mountpoint"])
                d["total"] = usage.total
                d["used"] = usage.used
                d["free"] = usage.free
                d["percent"] = usage.percent
            except (PermissionError, OSError):
                continue
        self._update_charts()

    def _on_close(self):
        self._running = False
        self.root.destroy()


def main():
    # Windows DPI (Tk 생성 전)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    try:
        app = DiskMonitorApp(root)
        root.mainloop()
    except Exception as e:
        # GUI 실패 시 에러를 콘솔에 출력
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("오류", f"프로그램 실행 중 오류:\n{e}")
        except Exception:
            pass
        input("엔터를 눌러 종료하세요...")


if __name__ == "__main__":
    main()
