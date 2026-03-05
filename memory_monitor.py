"""
Windows 11 Memory Monitor GUI
프로세스별 메모리 사용량을 실시간으로 시각화하는 도구
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import sys

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
BAR_BG = "#45475a"


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


class GradientBar(tk.Canvas):
    """그라데이션 프로그레스 바"""

    def __init__(self, master, width=300, height=22, **kwargs):
        super().__init__(master, bg=BG_CARD, highlightthickness=0, **kwargs)
        self.configure(width=width, height=height)
        self._width = width
        self._height = height
        self._value = 0

    def set_value(self, pct):
        self._value = max(0, min(100, pct))
        self._draw()

    def _draw(self):
        self.delete("all")
        r = self._height // 2
        # 배경
        self.create_rounded_rect(0, 0, self._width, self._height, r, fill=BAR_BG)
        # 채우기
        if self._value > 0:
            fill_w = max(self._height, self._width * self._value / 100)
            color = get_color_for_percent(self._value)
            self.create_rounded_rect(0, 0, fill_w, self._height, r, fill=color)
        # 텍스트
        self.create_text(self._width // 2, self._height // 2,
                         text=f"{self._value:.1f}%", fill="white",
                         font=("Segoe UI", 9, "bold"))

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)


class PieChart(tk.Canvas):
    """메모리 분포 파이 차트"""

    def __init__(self, master, size=220, **kwargs):
        super().__init__(master, bg=BG_CARD, highlightthickness=0, **kwargs)
        self.configure(width=size, height=size)
        self._size = size
        self._data = []

    def set_data(self, data):
        """data: list of (label, value, color)"""
        self._data = data
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self._size
        pad = 10
        total = sum(v for _, v, _ in self._data)
        if total == 0:
            return
        start = 0
        for label, value, color in self._data:
            extent = (value / total) * 360
            self.create_arc(pad, pad, s - pad, s - pad,
                            start=start, extent=extent,
                            fill=color, outline=BG_CARD, width=2)
            start += extent
        # 가운데 원 (도넛 형태)
        inner = 40
        self.create_oval(pad + inner, pad + inner,
                         s - pad - inner, s - pad - inner,
                         fill=BG_CARD, outline=BG_CARD)
        self.create_text(s // 2, s // 2, text="MEM",
                         fill=FG_ACCENT, font=("Segoe UI", 11, "bold"))


class HistoryGraph(tk.Canvas):
    """메모리 사용률 히스토리 그래프"""

    def __init__(self, master, width=400, height=120, **kwargs):
        super().__init__(master, bg=BG_CARD, highlightthickness=0, **kwargs)
        self.configure(width=width, height=height)
        self._w = width
        self._h = height
        self._history = []
        self._max_points = 60

    def add_point(self, value):
        self._history.append(value)
        if len(self._history) > self._max_points:
            self._history.pop(0)
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self._w, self._h
        pad_x, pad_y = 40, 15

        # 그리드 라인
        for pct in (25, 50, 75, 100):
            y = pad_y + (h - 2 * pad_y) * (1 - pct / 100)
            self.create_line(pad_x, y, w - 10, y, fill="#3a3a50", dash=(2, 4))
            self.create_text(pad_x - 5, y, text=f"{pct}%", anchor="e",
                             fill=FG_DIM, font=("Segoe UI", 7))

        if len(self._history) < 2:
            return

        points = []
        n = len(self._history)
        dx = (w - pad_x - 10) / (self._max_points - 1)
        offset = self._max_points - n
        for i, v in enumerate(self._history):
            x = pad_x + (offset + i) * dx
            y = pad_y + (h - 2 * pad_y) * (1 - v / 100)
            points.append((x, y))

        # 영역 채우기
        fill_points = [points[0]]
        fill_points.extend(points)
        fill_points.append(points[-1])
        fill_coords = []
        fill_coords.extend([points[0][0], h - pad_y])
        for x, y in points:
            fill_coords.extend([x, y])
        fill_coords.extend([points[-1][0], h - pad_y])
        self.create_polygon(fill_coords, fill="#89b4fa20", outline="")

        # 라인
        line_coords = []
        for x, y in points:
            line_coords.extend([x, y])
        if len(line_coords) >= 4:
            self.create_line(line_coords, fill=FG_ACCENT, width=2, smooth=True)

        # 최신 값 점
        if points:
            lx, ly = points[-1]
            self.create_oval(lx - 4, ly - 4, lx + 4, ly + 4,
                             fill=FG_ACCENT, outline="white", width=1)


class MemoryMonitorApp:
    """메인 애플리케이션"""

    def __init__(self, root):
        self.root = root
        self.root.title("Memory Monitor - Windows 11")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1100x780")
        self.root.minsize(900, 650)

        self._running = True
        self._sort_col = "rss"
        self._sort_reverse = True
        self._search_var = tk.StringVar()
        self._update_interval = 2  # 초

        self._build_ui()
        self._start_update_thread()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── UI 구성 ───────────────────────────────────────────────────
    def _build_ui(self):
        # 헤더
        header = tk.Frame(self.root, bg=BG_HEADER, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="  Memory Monitor", bg=BG_HEADER,
                 fg=FG_ACCENT, font=("Segoe UI", 16, "bold")).pack(side="left", padx=10)

        # 상단: 시스템 요약 카드들
        top_frame = tk.Frame(self.root, bg=BG_DARK, pady=8)
        top_frame.pack(fill="x", padx=12)

        # 카드 1: 전체 메모리
        self.card_total = self._make_card(top_frame, "총 메모리")
        self.card_total.pack(side="left", fill="both", expand=True, padx=4)

        # 카드 2: 사용 중
        self.card_used = self._make_card(top_frame, "사용 중")
        self.card_used.pack(side="left", fill="both", expand=True, padx=4)

        # 카드 3: 사용 가능
        self.card_avail = self._make_card(top_frame, "사용 가능")
        self.card_avail.pack(side="left", fill="both", expand=True, padx=4)

        # 카드 4: 스왑
        self.card_swap = self._make_card(top_frame, "스왑 메모리")
        self.card_swap.pack(side="left", fill="both", expand=True, padx=4)

        # 중간: 바 + 파이차트 + 히스토리
        mid_frame = tk.Frame(self.root, bg=BG_DARK, pady=4)
        mid_frame.pack(fill="x", padx=12)

        # 왼쪽: 메모리 바 + 상세
        left_mid = tk.Frame(mid_frame, bg=BG_CARD, padx=12, pady=10)
        left_mid.pack(side="left", fill="both", expand=True, padx=4)

        tk.Label(left_mid, text="RAM 사용률", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.ram_bar = GradientBar(left_mid, width=320, height=24)
        self.ram_bar.pack(fill="x", pady=(5, 8))

        tk.Label(left_mid, text="스왑 사용률", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.swap_bar = GradientBar(left_mid, width=320, height=24)
        self.swap_bar.pack(fill="x", pady=(5, 8))

        # 상세 라벨들
        self.detail_labels = {}
        for key, name in [("active", "Active"), ("buffers", "Buffers/Cached"),
                          ("shared", "Shared"), ("procs", "프로세스 수")]:
            row = tk.Frame(left_mid, bg=BG_CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=f"{name}:", bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", 9), width=14, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="--", bg=BG_CARD, fg=FG_TEXT,
                           font=("Segoe UI", 9, "bold"))
            lbl.pack(side="left")
            self.detail_labels[key] = lbl

        # 가운데: 파이차트
        pie_frame = tk.Frame(mid_frame, bg=BG_CARD, padx=8, pady=8)
        pie_frame.pack(side="left", padx=4)
        tk.Label(pie_frame, text="상위 프로세스 분포", bg=BG_CARD,
                 fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack()
        self.pie = PieChart(pie_frame, size=200)
        self.pie.pack(pady=4)
        self.pie_legend = tk.Frame(pie_frame, bg=BG_CARD)
        self.pie_legend.pack(fill="x")

        # 오른쪽: 히스토리 그래프
        hist_frame = tk.Frame(mid_frame, bg=BG_CARD, padx=8, pady=8)
        hist_frame.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(hist_frame, text="메모리 사용률 추이 (최근 60초)",
                 bg=BG_CARD, fg=FG_TEXT, font=("Segoe UI", 10, "bold")).pack()
        self.history = HistoryGraph(hist_frame, width=380, height=170)
        self.history.pack(fill="both", expand=True, pady=4)

        # 검색 + 프로세스 목록
        list_header = tk.Frame(self.root, bg=BG_DARK, pady=4)
        list_header.pack(fill="x", padx=16)

        tk.Label(list_header, text="프로세스별 메모리 사용량",
                 bg=BG_DARK, fg=FG_TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")

        # 검색
        search_frame = tk.Frame(list_header, bg=BG_DARK)
        search_frame.pack(side="right")
        tk.Label(search_frame, text="검색:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
        search_entry = tk.Entry(search_frame, textvariable=self._search_var,
                                bg=BG_CARD, fg=FG_TEXT, insertbackground=FG_TEXT,
                                font=("Segoe UI", 9), width=20,
                                relief="flat", bd=4)
        search_entry.pack(side="left")

        # 트리뷰 (프로세스 목록)
        tree_frame = tk.Frame(self.root, bg=BG_DARK)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        style = ttk.Style()
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

        columns = ("pid", "name", "rss", "vms", "percent", "status", "user")
        self.tree = ttk.Treeview(tree_frame, columns=columns,
                                  show="headings", style="Dark.Treeview",
                                  selectmode="browse")

        col_config = [
            ("pid", "PID", 70, "center"),
            ("name", "프로세스 이름", 220, "w"),
            ("rss", "RSS (실제 메모리)", 130, "e"),
            ("vms", "VMS (가상 메모리)", 130, "e"),
            ("percent", "메모리 %", 90, "center"),
            ("status", "상태", 80, "center"),
            ("user", "사용자", 140, "w"),
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

        # 하단 상태바
        status_bar = tk.Frame(self.root, bg=BG_HEADER, pady=3)
        status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(status_bar, text="시작 중...",
                                      bg=BG_HEADER, fg=FG_DIM,
                                      font=("Segoe UI", 8))
        self.status_label.pack(side="left", padx=10)
        self.cpu_label = tk.Label(status_bar, text="CPU: --",
                                   bg=BG_HEADER, fg=FG_DIM,
                                   font=("Segoe UI", 8))
        self.cpu_label.pack(side="right", padx=10)

    def _make_card(self, parent, title):
        """요약 카드 위젯 생성"""
        frame = tk.Frame(parent, bg=BG_CARD, padx=14, pady=10)
        tk.Label(frame, text=title, bg=BG_CARD, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w")
        val_label = tk.Label(frame, text="--", bg=BG_CARD, fg=FG_TEXT,
                             font=("Segoe UI", 18, "bold"))
        val_label.pack(anchor="w")
        sub_label = tk.Label(frame, text="", bg=BG_CARD, fg=FG_DIM,
                             font=("Segoe UI", 8))
        sub_label.pack(anchor="w")
        frame._val = val_label
        frame._sub = sub_label
        return frame

    # ─── 데이터 업데이트 ────────────────────────────────────────────
    def _start_update_thread(self):
        t = threading.Thread(target=self._update_loop, daemon=True)
        t.start()

    def _update_loop(self):
        while self._running:
            try:
                data = self._collect_data()
                self.root.after(0, self._apply_data, data)
            except Exception as e:
                self.root.after(0, self._set_status, f"오류: {e}")
            time.sleep(self._update_interval)

    def _collect_data(self):
        """백그라운드 스레드에서 데이터 수집"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu_pct = psutil.cpu_percent(interval=0.5)

        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info",
                                       "memory_percent", "status", "username"]):
            try:
                info = p.info
                mi = info.get("memory_info")
                if mi is None:
                    continue
                procs.append({
                    "pid": info["pid"],
                    "name": info.get("name", "?"),
                    "rss": mi.rss,
                    "vms": mi.vms,
                    "percent": info.get("memory_percent", 0) or 0,
                    "status": info.get("status", "?"),
                    "user": info.get("username", "-") or "-",
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return {
            "mem": mem,
            "swap": swap,
            "cpu": cpu_pct,
            "procs": procs,
        }

    def _apply_data(self, data):
        """메인 스레드에서 UI 업데이트"""
        if not self._running:
            return
        mem = data["mem"]
        swap = data["swap"]
        procs = data["procs"]

        # 카드 업데이트
        self.card_total._val.config(text=format_bytes(mem.total))
        self.card_total._sub.config(text=f"페이지 파일 포함")

        self.card_used._val.config(text=format_bytes(mem.used),
                                    fg=get_color_for_percent(mem.percent))
        self.card_used._sub.config(text=f"{mem.percent:.1f}% 사용")

        self.card_avail._val.config(text=format_bytes(mem.available),
                                     fg=FG_GREEN)
        avail_pct = mem.available / mem.total * 100 if mem.total else 0
        self.card_avail._sub.config(text=f"{avail_pct:.1f}% 여유")

        self.card_swap._val.config(text=format_bytes(swap.used))
        self.card_swap._sub.config(
            text=f"총 {format_bytes(swap.total)} / {swap.percent:.1f}% 사용")

        # 바
        self.ram_bar.set_value(mem.percent)
        self.swap_bar.set_value(swap.percent)

        # 상세
        active = getattr(mem, "active", 0)
        buffers = getattr(mem, "buffers", 0) + getattr(mem, "cached", 0)
        shared = getattr(mem, "shared", 0)
        self.detail_labels["active"].config(text=format_bytes(active) if active else "N/A")
        self.detail_labels["buffers"].config(text=format_bytes(buffers) if buffers else "N/A")
        self.detail_labels["shared"].config(text=format_bytes(shared) if shared else "N/A")
        self.detail_labels["procs"].config(text=str(len(procs)))

        # 히스토리
        self.history.add_point(mem.percent)

        # 파이차트 - 상위 5개
        top5 = sorted(procs, key=lambda x: x["rss"], reverse=True)[:5]
        pie_colors = [FG_ACCENT, FG_GREEN, FG_YELLOW, FG_PEACH, FG_MAUVE]
        pie_data = [(p["name"], p["rss"], pie_colors[i % len(pie_colors)])
                     for i, p in enumerate(top5)]
        others_mem = sum(p["rss"] for p in procs) - sum(p["rss"] for p in top5)
        if others_mem > 0:
            pie_data.append(("기타", others_mem, FG_DIM))
        self.pie.set_data(pie_data)

        # 파이 범례
        for w in self.pie_legend.winfo_children():
            w.destroy()
        for i, p in enumerate(top5):
            color = pie_colors[i % len(pie_colors)]
            row = tk.Frame(self.pie_legend, bg=BG_CARD)
            row.pack(fill="x", pady=0)
            tk.Label(row, text="  \u25a0", bg=BG_CARD, fg=color,
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Label(row, text=f" {p['name'][:18]} ({format_bytes(p['rss'])})",
                     bg=BG_CARD, fg=FG_TEXT,
                     font=("Segoe UI", 8)).pack(side="left")

        # 프로세스 목록
        search = self._search_var.get().lower()
        if search:
            procs = [p for p in procs if search in p["name"].lower()
                     or search in str(p["pid"])]

        # 정렬
        reverse = self._sort_reverse
        key_map = {
            "pid": lambda x: x["pid"],
            "name": lambda x: x["name"].lower(),
            "rss": lambda x: x["rss"],
            "vms": lambda x: x["vms"],
            "percent": lambda x: x["percent"],
            "status": lambda x: x["status"],
            "user": lambda x: x["user"],
        }
        sort_fn = key_map.get(self._sort_col, key_map["rss"])
        procs.sort(key=sort_fn, reverse=reverse)

        # 스크롤 위치 보존
        sel = self.tree.selection()
        sel_pid = None
        if sel:
            vals = self.tree.item(sel[0], "values")
            if vals:
                sel_pid = vals[0]

        yview = self.tree.yview()

        self.tree.delete(*self.tree.get_children())
        for p in procs:
            self.tree.insert("", "end", values=(
                p["pid"],
                p["name"],
                format_bytes(p["rss"]),
                format_bytes(p["vms"]),
                f"{p['percent']:.1f}%",
                p["status"],
                p["user"],
            ))

        # 스크롤 복원
        self.tree.yview_moveto(yview[0])

        # 선택 복원
        if sel_pid:
            for item in self.tree.get_children():
                if self.tree.item(item, "values")[0] == sel_pid:
                    self.tree.selection_set(item)
                    break

        # 상태바
        self._set_status(
            f"마지막 업데이트: {time.strftime('%H:%M:%S')} | "
            f"프로세스: {len(procs)}개 | "
            f"새로고침: {self._update_interval}초마다"
        )
        self.cpu_label.config(text=f"CPU: {data['cpu']:.1f}%")

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = True if col in ("rss", "vms", "percent") else False

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _on_close(self):
        self._running = False
        self.root.destroy()


def main():
    root = tk.Tk()

    # Windows DPI 설정
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = MemoryMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
